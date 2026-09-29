"""Slots, holds and bookings.

- `parse_window` turns the customer's words ("tomorrow morning", "Tuesday afternoon",
  "asap") into a search window in the location's time zone. Deterministic, no model.
- `availability` lists free slots: business hours, minus the system of record's busy
  times, minus our own held or confirmed appointments.
- `hold` writes an appointment in `held` state that expires after ten minutes, so two
  conversations cannot be offered the same slot. Expiry is lazy: an expired hold is
  ignored by availability and by confirm.
- `confirm` writes the external booking first (idempotent on the proposal id), then the
  local row, then enqueues the confirmation message and the pack's reminder steps.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.models import (
    ActionProposal,
    Appointment,
    AuditLog,
    Contact,
    Conversation,
    Job,
    Location,
    Tenant,
)
from novaxis_core.settings import get_settings
from novaxis_core.sor import Slot, SystemOfRecord, overlaps

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DAY_WORDS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
ACTIVE_STATUSES = ("held", "confirmed")


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    label: str


def location_for(session: Session, tenant: Tenant) -> Location | None:
    return session.scalar(select(Location).order_by(Location.created_at).limit(1))


def tz_for(tenant: Tenant, location: Location | None) -> ZoneInfo:
    name = (location.timezone if location else None) or str(
        tenant.settings.get("timezone") or "Europe/London"
    )
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - bad tz name falls back rather than breaking bookings
        return ZoneInfo("Europe/London")


def parse_window(text: str, tz: ZoneInfo, now: datetime | None = None) -> Window:
    """Best-effort: a day (or range) and a part of day. Unknown words widen, never narrow."""
    s = get_settings()
    now_local = (now or datetime.now(UTC)).astimezone(tz)
    t = text.lower()
    day: date | None = None
    span_days = s.availability_days
    if "tomorrow" in t:
        day, span_days = now_local.date() + timedelta(days=1), 1
    elif "today" in t or "asap" in t or "as soon as" in t or "now" in t or "urgent" in t:
        day, span_days = now_local.date(), 2
    else:
        for word, idx in _DAY_WORDS.items():
            if re.search(rf"\b{word}\b", t):
                delta = (idx - now_local.weekday()) % 7
                if delta == 0 and "next" in t:
                    delta = 7
                day, span_days = now_local.date() + timedelta(days=delta), 1
                break
        if day is None and ("this week" in t or "week" in t):
            day, span_days = now_local.date(), 7
    if day is None:
        day = now_local.date()
    start_t, end_t = time(0, 0), time(23, 59)
    if "morning" in t or re.search(r"\bam\b", t):
        start_t, end_t = time(6, 0), time(12, 0)
    elif "afternoon" in t or re.search(r"\bpm\b", t):
        start_t, end_t = time(12, 0), time(18, 0)
    elif "evening" in t:
        start_t, end_t = time(17, 0), time(21, 0)
    start = datetime.combine(day, start_t, tz)
    end = datetime.combine(day + timedelta(days=span_days - 1), end_t, tz)
    if end < now_local:
        end = now_local + timedelta(days=span_days)
    return Window(start.astimezone(UTC), end.astimezone(UTC), text.strip()[:80])


def _service(tenant: Tenant, service_code: str) -> dict[str, Any]:
    for svc in tenant.settings.get("services") or []:
        if svc.get("code") == service_code:
            return dict(svc)
    return {"code": service_code, "name": service_code, "duration_minutes": 60}


def _hours_blocks(tenant: Tenant, tz: ZoneInfo, day: date) -> list[tuple[datetime, datetime]]:
    hours = tenant.settings.get("business_hours") or {}
    h = hours.get(WEEKDAYS[day.weekday()])
    if not h:
        return []
    oh, om = (int(x) for x in h["open"].split(":"))
    ch, cm = (int(x) for x in h["close"].split(":"))
    return [(datetime.combine(day, time(oh, om), tz), datetime.combine(day, time(ch, cm), tz))]


def _local_busy(session: Session, window: Window) -> list[tuple[datetime, datetime]]:
    now = datetime.now(UTC)
    rows = session.scalars(
        select(Appointment).where(
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.ends_at > window.start,
            Appointment.starts_at < window.end,
        )
    )
    out: list[tuple[datetime, datetime]] = []
    for a in rows:
        if a.status == "held" and a.hold_expires_at and a.hold_expires_at < now:
            continue  # lazy expiry
        out.append((a.starts_at, a.ends_at))
    return out


def availability(
    session: Session,
    tenant: Tenant,
    sor: SystemOfRecord,
    service_code: str,
    window: Window,
    limit: int | None = None,
) -> list[Slot]:
    location = location_for(session, tenant)
    tz = tz_for(tenant, location)
    minutes = int(_service(tenant, service_code).get("duration_minutes", 60))
    step = timedelta(minutes=minutes)
    rules = tenant.settings.get("booking_rules") or {}
    gap = timedelta(minutes=int(rules.get("buffer_minutes") or 0))
    most = rules.get("max_per_day")
    busy = [
        (b.starts_at, b.ends_at)
        for b in sor.busy(location.calendar_ref if location else None, window.start, window.end)
    ]
    busy += _local_busy(session, window)
    booked = _booked_per_day(session, window, tz) if most else {}
    now = datetime.now(UTC) + timedelta(minutes=int(rules.get("min_notice_minutes", 30)))
    slots: list[Slot] = []
    day = window.start.astimezone(tz).date()
    last = window.end.astimezone(tz).date()
    limit = limit or get_settings().slots_offered
    while day <= last and len(slots) < limit:
        if most and booked.get(day, 0) >= int(most):
            day += timedelta(days=1)
            continue
        blocked = busy + _protected(rules, tz, day)
        for open_at, close_at in _hours_blocks(tenant, tz, day):
            cursor = open_at
            while cursor + step <= close_at and len(slots) < limit:
                s_start, s_end = cursor.astimezone(UTC), (cursor + step).astimezone(UTC)
                cursor += step
                if s_start < now or s_start < window.start or s_end > window.end:
                    continue
                if any(overlaps(s_start - gap, s_end + gap, b0, b1) for b0, b1 in blocked):
                    continue
                slots.append(Slot(s_start, s_end))
        day += timedelta(days=1)
    return slots


def _protected(rules: dict[str, Any], tz: ZoneInfo, day: date) -> list[tuple[datetime, datetime]]:
    """The business's protected times on this day (lunch, school run...), as busy time."""
    out: list[tuple[datetime, datetime]] = []
    for p in rules.get("protected") or []:
        if WEEKDAYS[day.weekday()] not in p["days"]:
            continue
        sh, sm = (int(x) for x in p["start"].split(":"))
        eh, em = (int(x) for x in p["end"].split(":"))
        out.append(
            (
                datetime.combine(day, time(sh, sm), tz).astimezone(UTC),
                datetime.combine(day, time(eh, em), tz).astimezone(UTC),
            )
        )
    return out


def _booked_per_day(session: Session, window: Window, tz: ZoneInfo) -> dict[date, int]:
    """Confirmed bookings per local day, for the daily limit. Offers still on hold do not
    count: only one of them will be booked."""
    counts: dict[date, int] = {}
    rows = session.scalars(
        select(Appointment.starts_at).where(
            Appointment.status == "confirmed",
            Appointment.starts_at >= window.start - timedelta(days=1),
            Appointment.starts_at < window.end + timedelta(days=1),
        )
    )
    for starts_at in rows:
        d = starts_at.astimezone(tz).date()
        counts[d] = counts.get(d, 0) + 1
    return counts


def fmt(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    return local.strftime("%a %d %b, %H:%M")


def hold(
    session: Session,
    tenant: Tenant,
    contact: Contact,
    conv: Conversation,
    service_code: str,
    slots: list[Slot],
    proposal_id: uuid.UUID,
) -> list[Appointment]:
    location = location_for(session, tenant)
    expires = datetime.now(UTC) + timedelta(minutes=get_settings().hold_minutes)
    out: list[Appointment] = []
    for slot in slots:
        if any(
            overlaps(slot.starts_at, slot.ends_at, b0, b1)
            for b0, b1 in _local_busy(session, Window(slot.starts_at, slot.ends_at, ""))
        ):
            continue
        a = Appointment(
            tenant_id=tenant.id,
            location_id=location.id if location else None,
            contact_id=contact.id,
            conversation_id=conv.id,
            proposal_id=proposal_id,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            service_code=service_code,
            status="held",
            hold_expires_at=expires,
        )
        session.add(a)
        out.append(a)
    session.flush()
    return out


def offered_for(session: Session, conv: Conversation) -> list[Appointment]:
    now = datetime.now(UTC)
    rows = session.scalars(
        select(Appointment)
        .where(Appointment.conversation_id == conv.id, Appointment.status == "held")
        .order_by(Appointment.starts_at)
    )
    return [a for a in rows if not a.hold_expires_at or a.hold_expires_at >= now]


def last_offer(session: Session, conv: Conversation) -> list[Appointment]:
    """The slots of the latest offer to this conversation, numbered as the customer saw
    them, even after their hold ran out: `confirm` still books an expired hold whose slot
    is free, and refuses one that has since been taken."""
    rows = list(
        session.scalars(
            select(Appointment)
            .where(Appointment.conversation_id == conv.id, Appointment.status == "held")
            .order_by(Appointment.starts_at)
        )
    )
    if not rows:
        return []
    never = datetime.min.replace(tzinfo=UTC)
    latest = max(rows, key=lambda a: a.hold_expires_at or never).proposal_id
    return [a for a in rows if a.proposal_id == latest]


def widen(window: Window) -> Window:
    """When the asked-for window has nothing, look ahead from its start instead of giving up."""
    return Window(
        window.start,
        window.start + timedelta(days=get_settings().availability_days),
        f"{window.label} (next available)",
    )


def offer_text(
    tenant: Tenant, tz: ZoneInfo, held: list[Appointment], service_name: str, widened: bool = False
) -> str:
    if not held:
        return (
            "I couldn't find a free time in the next couple of weeks. "
            "A member of the team will look at the diary and come back to you."
        )
    lines = [f"{i + 1}. {fmt(a.starts_at, tz)}" for i, a in enumerate(held)]
    lead = (
        "There's nothing free at the time you asked for; the next available times for "
        f"{service_name} are:\n"
        if widened
        else f"Here are the times the team can offer for {service_name}:\n"
    )
    return (
        lead
        + "\n".join(lines)
        + "\nReply with the number that suits and I'll pass it to the team to confirm."
    )


def appointments_block(session: Session, tenant: Tenant, conv: Conversation) -> str:
    """What the model is told about slots and bookings for this conversation."""
    location = location_for(session, tenant)
    tz = tz_for(tenant, location)
    held = offered_for(session, conv)
    confirmed = list(
        session.scalars(
            select(Appointment)
            .where(Appointment.conversation_id == conv.id, Appointment.status == "confirmed")
            .order_by(Appointment.starts_at)
        )
    )
    lines: list[str] = []
    if held:
        lines.append("Offered slots (number: time, appointment_id):")
        lines += [
            f"{i + 1}: {fmt(a.starts_at, tz)}, appointment_id={a.id}" for i, a in enumerate(held)
        ]
        moving = replaced_by_hold(session, held[0])
        if moving is not None:
            lines.append(
                f"These would move the booking at {fmt(moving.starts_at, tz)} "
                f"(appointment_id={moving.id}); confirming one moves it, nothing is added."
            )
        lines.append("If the customer picks one, call confirm_appointment with its appointment_id.")
    if confirmed:
        lines.append("Confirmed appointments (time, appointment_id):")
        lines += [
            f"{fmt(a.starts_at, tz)} {a.service_code}, appointment_id={a.id}" for a in confirmed
        ]
    return "\n".join(lines)


def _audit(session: Session, tenant: Tenant, event: str, appt: Appointment, **diff: Any) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor="worker:scheduling",
            event=event,
            subject_table="appointments",
            subject_id=appt.id,
            diff={
                k: (str(v) if isinstance(v, uuid.UUID | datetime) else v) for k, v in diff.items()
            },
        )
    )


def _enqueue_send(session: Session, tenant: Tenant, conv: Conversation, text: str) -> Job:
    from novaxis_core.models import Message

    msg = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="outbound",
        channel=conv.channel,
        author="worker",
        body=text,
    )
    session.add(msg)
    session.flush()
    job = Job(tenant_id=tenant.id, kind="send_message", payload={"message_id": str(msg.id)})
    session.add(job)
    session.flush()
    return job


def schedule_appointment_steps(
    session: Session, tenant: Tenant, pack: Any, appt: Appointment, conv: Conversation
) -> int:
    from novaxis_core.quiet_hours import before_if_quiet, later_if_quiet
    from novaxis_core.workflows import parse_delay

    now = datetime.now(UTC)
    tz = tz_for(tenant, location_for(session, tenant))
    n = 0
    for step in pack.workflows:
        if step.trigger == "appointment_confirmed":
            run_after = later_if_quiet(now + parse_delay(step.after), tz)
        elif step.trigger == "before_appointment":
            run_after = before_if_quiet(
                appt.starts_at - parse_delay(step.after), tz, appt.starts_at
            )
            if run_after < now:
                continue
        else:
            continue
        session.add(
            Job(
                tenant_id=tenant.id,
                kind="workflow_step",
                payload={
                    "conversation_id": str(conv.id),
                    "step_id": step.id,
                    "appointment_id": str(appt.id),
                    "anchor": now.isoformat(),
                },
                run_after=run_after,
            )
        )
        n += 1
    session.flush()
    return n


def cancel_appointment_steps(session: Session, appt: Appointment) -> int:
    n = 0
    for job in session.scalars(
        select(Job).where(
            Job.kind == "workflow_step",
            Job.state == "queued",
            Job.payload["appointment_id"].astext == str(appt.id),
        )
    ):
        job.state = "done"
        job.last_error = "appointment cancelled or moved"
        n += 1
    return n


def confirm(
    session: Session,
    tenant: Tenant,
    sor: SystemOfRecord,
    pack: Any,
    appt: Appointment,
    proposal_id: uuid.UUID,
) -> Appointment:
    """Idempotent on the proposal id. Calendar first, then the row, then the message job."""
    if appt.status == "confirmed" and appt.external_ref:
        return appt
    now = datetime.now(UTC)
    if appt.status == "held" and appt.hold_expires_at and appt.hold_expires_at < now:
        busy = _local_busy(session, Window(appt.starts_at, appt.ends_at, ""))
        if any(
            overlaps(appt.starts_at, appt.ends_at, b0, b1)
            for b0, b1 in busy
            if (b0, b1) != (appt.starts_at, appt.ends_at)
        ):
            raise RuntimeError("hold expired and the slot has since been taken")
    if appt.status not in ("held", "proposed"):
        raise RuntimeError(f"cannot confirm an appointment in state {appt.status}")
    moving = replaced_by_hold(session, appt)
    if moving is not None:
        return _move_to_hold(session, tenant, sor, pack, moving, appt)
    location = session.get(Location, appt.location_id) if appt.location_id else None
    contact = session.get(Contact, appt.contact_id)
    conv = session.get(Conversation, appt.conversation_id) if appt.conversation_id else None
    svc = _service(tenant, appt.service_code)
    who = contact.display_name if contact and contact.display_name else "customer"
    summary = f"{svc.get('name', appt.service_code)}: {who}"
    description = f"Booked by the Novaxis worker. Conversation {appt.conversation_id}."
    ref = sor.create_booking(
        location.calendar_ref if location else None,
        Slot(appt.starts_at, appt.ends_at),
        summary,
        description,
        f"confirm:{proposal_id}",
        details={
            "service_code": appt.service_code,
            "service_name": str(svc.get("name", appt.service_code)),
            "customer_name": who,
            "customer_phone": contact.phones[0] if contact and contact.phones else "",
            "customer_email": contact.emails[0] if contact and contact.emails else "",
            "appointment_id": str(appt.id),
        },
    )
    appt.external_ref = f"{ref.provider}:{ref.ref}"
    appt.status = "confirmed"
    appt.hold_expires_at = None
    # Release the other holds this proposal offered.
    for other in session.scalars(
        select(Appointment).where(
            Appointment.proposal_id == appt.proposal_id,
            Appointment.id != appt.id,
            Appointment.status == "held",
        )
    ):
        other.status = "cancelled"
    session.flush()
    _audit(
        session,
        tenant,
        "appointment.confirmed",
        appt,
        external_ref=appt.external_ref,
        starts_at=appt.starts_at,
    )
    if conv is not None:
        tz = tz_for(tenant, location)
        text = (
            f"Confirmed: {svc.get('name', appt.service_code)} on {fmt(appt.starts_at, tz)} "
            f"with {tenant.name}. Reply CHANGE if you need a different time."
        )
        _enqueue_send(session, tenant, conv, text)
        schedule_appointment_steps(session, tenant, pack, appt, conv)
    return appt


def cancel(
    session: Session, tenant: Tenant, sor: SystemOfRecord, appt: Appointment, reason: str
) -> Appointment:
    if appt.status == "cancelled":
        return appt
    if appt.external_ref and appt.status == "confirmed":
        provider, _, ref = appt.external_ref.partition(":")
        from novaxis_core.sor import ExternalRef

        sor.cancel_booking(ExternalRef(provider, ref))
    appt.status = "cancelled"
    cancel_appointment_steps(session, appt)
    session.flush()
    _audit(session, tenant, "appointment.cancelled", appt, reason=reason[:200])
    conv = session.get(Conversation, appt.conversation_id) if appt.conversation_id else None
    if conv is not None:
        _enqueue_send(
            session,
            tenant,
            conv,
            f"Your appointment with {tenant.name} has been cancelled. "
            "Reply here if you'd like to rebook.",
        )
    return appt


def replaced_by_hold(session: Session, hold_row: Appointment) -> Appointment | None:
    """The confirmed booking a held time was offered to replace, if it was offered by a
    reschedule and that booking is still confirmed."""
    if hold_row.proposal_id is None:
        return None
    prop = session.get(ActionProposal, hold_row.proposal_id)
    if prop is None or prop.kind != "reschedule_appointment":
        return None
    try:
        old = session.get(Appointment, uuid.UUID(str(prop.params.get("appointment_id"))))
    except ValueError:
        return None
    return old if old is not None and old.status == "confirmed" else None


def offer_moves(
    session: Session,
    tenant: Tenant,
    sor: SystemOfRecord,
    appt: Appointment,
    conv: Conversation,
    new_window_text: str,
    proposal_id: uuid.UUID,
) -> list[Appointment]:
    """Hold a few times in the asked-for window (or the next free ones) and offer them. The
    booking moves only when the customer picks one and that choice is confirmed; until then
    the original time stands."""
    if appt.status != "confirmed":
        raise RuntimeError(f"cannot reschedule an appointment in state {appt.status}")
    contact = session.get(Contact, appt.contact_id)
    if contact is None:
        raise RuntimeError("contact not found")
    location = session.get(Location, appt.location_id) if appt.location_id else None
    tz = tz_for(tenant, location)
    window = parse_window(new_window_text, tz)
    slots = availability(session, tenant, sor, appt.service_code, window)
    widened = False
    if not slots:
        window = widen(window)
        slots = availability(session, tenant, sor, appt.service_code, window)
        widened = True
    held = hold(session, tenant, contact, conv, appt.service_code, slots, proposal_id)
    name = str(_service(tenant, appt.service_code).get("name", appt.service_code))
    if held:
        text = (
            offer_text(tenant, tz, held, name, widened).replace(
                "Here are the times the team can offer",
                f"Your current booking is {fmt(appt.starts_at, tz)}. Here are the times the team "
                "can offer instead",
            )
            + " Your current booking stands until then."
        )
    else:
        text = offer_text(tenant, tz, held, name, widened) + (
            f" Your current booking for {fmt(appt.starts_at, tz)} still stands."
        )
    _enqueue_send(session, tenant, conv, text)
    return held


def _move_to_hold(
    session: Session,
    tenant: Tenant,
    sor: SystemOfRecord,
    pack: Any,
    appt: Appointment,
    chosen: Appointment,
) -> Appointment:
    """Move a confirmed booking to the time the customer picked, in the system of record
    too, and release every hold offered with it. Returns the moved booking."""
    if appt.external_ref:
        provider, _, ref = appt.external_ref.partition(":")
        from novaxis_core.sor import ExternalRef

        sor.update_booking(ExternalRef(provider, ref), Slot(chosen.starts_at, chosen.ends_at))
    old = appt.starts_at
    for h in session.scalars(
        select(Appointment).where(
            Appointment.proposal_id == chosen.proposal_id, Appointment.status == "held"
        )
    ):
        h.status = "cancelled"
    session.flush()
    appt.starts_at, appt.ends_at = chosen.starts_at, chosen.ends_at
    appt.customer_confirmed_at = None
    cancel_appointment_steps(session, appt)
    session.flush()
    _audit(session, tenant, "appointment.rescheduled", appt, from_=old, to=appt.starts_at)
    conv_id = chosen.conversation_id or appt.conversation_id
    conv = session.get(Conversation, conv_id) if conv_id else None
    if conv is not None:
        location = session.get(Location, appt.location_id) if appt.location_id else None
        tz = tz_for(tenant, location)
        svc = _service(tenant, appt.service_code)
        _enqueue_send(
            session,
            tenant,
            conv,
            f"Moved: {svc.get('name', appt.service_code)} is now {fmt(appt.starts_at, tz)} "
            f"with {tenant.name}.",
        )
        schedule_appointment_steps(session, tenant, pack, appt, conv)
    return appt
