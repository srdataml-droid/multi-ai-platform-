"""Slots, holds and bookings against real rows with a fake calendar."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from novaxis_core import scheduling
from novaxis_core.channels import NormalisedInbound
from novaxis_core.executors import execute
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM, ToolCall
from novaxis_core.models import (
    ActionProposal,
    Appointment,
    Contact,
    Conversation,
    Job,
    Message,
    Tenant,
)
from novaxis_core.sor import set_sor_override
from novaxis_core.sor.fake import FakeCalendar
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

TZ = ZoneInfo("Europe/London")


@pytest.fixture
def cal():
    fake = FakeCalendar()
    set_sor_override(lambda tenant: fake)
    yield fake
    set_sor_override(None)


@pytest.fixture
def dental(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t is not None
        s.expunge(t)
        return t


def _conv(tenant: Tenant, body: str = "hi") -> tuple[uuid.UUID, uuid.UUID]:
    v = uuid.uuid4().hex[:10]
    with tenant_session(tenant.id) as s:
        r = ingest(
            s,
            tenant,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref=tenant.slug,
                sender_visitor_id=v,
                body=body,
            ),
        )
        return r.conversation_id, r.contact_id


def _next_weekday_9am() -> datetime:
    d = datetime.now(TZ) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.replace(hour=9, minute=0, second=0, microsecond=0)


def test_parse_window_words() -> None:
    now = datetime(2026, 9, 28, 10, 0, tzinfo=TZ)  # a Monday
    w = scheduling.parse_window("tomorrow morning", TZ, now)
    assert (
        w.start.astimezone(TZ).date() == now.date() + timedelta(days=1)
        and w.start.astimezone(TZ).hour == 6
    )
    assert w.end.astimezone(TZ).hour == 12
    w = scheduling.parse_window("Tuesday afternoon", TZ, now)
    assert w.start.astimezone(TZ).weekday() == 1 and w.start.astimezone(TZ).hour == 12
    w = scheduling.parse_window("asap", TZ, now)
    assert w.start.astimezone(TZ).date() == now.date()
    w = scheduling.parse_window("whenever", TZ, now)
    assert (w.end - w.start).days >= 13, "unknown words widen the window"


def test_availability_respects_hours_service_length_and_busy(
    dental: Tenant, cal: FakeCalendar
) -> None:
    day = _next_weekday_9am()
    window = scheduling.Window(
        day.astimezone(UTC), (day + timedelta(hours=9)).astimezone(UTC), "test"
    )
    with tenant_session(dental.id) as s:
        slots = scheduling.availability(s, dental, cal, "hygiene", window, limit=50)
        assert slots and all((x.ends_at - x.starts_at) == timedelta(minutes=30) for x in slots)
        assert (
            slots[0].starts_at.astimezone(TZ).hour >= 8
            and slots[-1].ends_at.astimezone(TZ).hour <= 18
        )
        first = slots[0]
        cal.events["x"] = (scheduling.Slot(first.starts_at, first.ends_at), "busy")
        again = scheduling.availability(s, dental, cal, "hygiene", window, limit=50)
        assert first.starts_at not in {x.starts_at for x in again}


def test_two_conversations_offered_the_same_slot_only_one_confirms(
    dental: Tenant, cal: FakeCalendar
) -> None:
    conv_a, contact_a = _conv(dental)
    conv_b, contact_b = _conv(dental)
    day = _next_weekday_9am()
    window = scheduling.Window(day.astimezone(UTC), (day + timedelta(hours=3)).astimezone(UTC), "t")
    with tenant_session(dental.id) as s:
        pa = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_a,
            kind="propose_appointment",
            params={},
            risk="low",
            state="auto_approved",
        )
        pb = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_b,
            kind="propose_appointment",
            params={},
            risk="low",
            state="auto_approved",
        )
        s.add_all([pa, pb])
        s.flush()
        slots = scheduling.availability(s, dental, cal, "checkup", window, limit=1)
        held_a = scheduling.hold(
            s,
            dental,
            s.get(Contact, contact_a),
            s.get(Conversation, conv_a),
            "checkup",
            slots,
            pa.id,
        )  # type: ignore[arg-type]
        held_b = scheduling.hold(
            s,
            dental,
            s.get(Contact, contact_b),
            s.get(Conversation, conv_b),
            "checkup",
            slots,
            pb.id,
        )  # type: ignore[arg-type]
        assert len(held_a) == 1 and held_b == [], "the second hold on the same slot is refused"
        again = scheduling.availability(s, dental, cal, "checkup", window, limit=1)
        assert again and again[0].starts_at != held_a[0].starts_at, (
            "B is re-offered a different slot"
        )


def test_confirm_is_idempotent_and_writes_calendar_once(dental: Tenant, cal: FakeCalendar) -> None:
    conv_id, contact_id = _conv(dental)
    day = _next_weekday_9am()
    with tenant_session(dental.id) as s:
        p = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_id,
            kind="confirm_appointment",
            params={},
            risk="low",
            state="auto_approved",
        )
        s.add(p)
        s.flush()
        appt = Appointment(
            tenant_id=dental.id,
            contact_id=contact_id,
            conversation_id=conv_id,
            proposal_id=p.id,
            starts_at=day.astimezone(UTC),
            ends_at=(day + timedelta(minutes=20)).astimezone(UTC),
            service_code="checkup",
            status="held",
            hold_expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        s.add(appt)
        s.flush()
        pid, aid = p.id, appt.id
    pack = get_pack("dental")
    for _ in range(2):
        with tenant_session(dental.id) as s:
            appt = s.get(Appointment, aid)
            assert appt is not None
            scheduling.confirm(s, dental, cal, pack, appt, pid)
            assert appt.status == "confirmed" and appt.external_ref == "fake:evt-1"
    assert cal.calls.count("create") == 1 and len(cal.events) == 1
    with tenant_session(dental.id) as s:
        sends = list(s.scalars(select(Job).where(Job.kind == "send_message")))
        msgs = list(
            s.scalars(
                select(Message).where(
                    Message.conversation_id == conv_id, Message.direction == "outbound"
                )
            )
        )
        assert (
            len(msgs) == 1 and msgs[0].body.startswith("Confirmed: Check-up on") and len(sends) >= 1
        )
        steps = {
            j.payload["step_id"]
            for j in s.scalars(
                select(Job).where(
                    Job.kind == "workflow_step",
                    Job.state == "queued",
                    Job.payload["appointment_id"].astext == str(aid),
                )
            )
        }
        assert steps == {"confirm_on_booking", "remind_48h", "remind_2h"} - (
            {"remind_48h"} if day - datetime.now(TZ) < timedelta(hours=48) else set()
        )


def test_cancel_releases_calendar_and_reminders(dental: Tenant, cal: FakeCalendar) -> None:
    conv_id, contact_id = _conv(dental)
    day = _next_weekday_9am() + timedelta(days=7)
    with tenant_session(dental.id) as s:
        p = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_id,
            kind="confirm_appointment",
            params={},
            risk="low",
            state="auto_approved",
        )
        s.add(p)
        s.flush()
        appt = Appointment(
            tenant_id=dental.id,
            contact_id=contact_id,
            conversation_id=conv_id,
            proposal_id=p.id,
            starts_at=day.astimezone(UTC),
            ends_at=(day + timedelta(minutes=20)).astimezone(UTC),
            service_code="checkup",
            status="held",
        )
        s.add(appt)
        s.flush()
        scheduling.confirm(s, dental, cal, get_pack("dental"), appt, p.id)
        aid = appt.id
    with tenant_session(dental.id) as s:
        appt = s.get(Appointment, aid)
        assert appt is not None
        scheduling.cancel(s, dental, cal, appt, "customer asked")
        assert appt.status == "cancelled" and not cal.events
        queued = list(
            s.scalars(
                select(Job).where(
                    Job.kind == "workflow_step",
                    Job.state == "queued",
                    Job.payload["appointment_id"].astext == str(aid),
                )
            )
        )
        assert queued == []


def test_full_flow_offer_pick_confirm_through_executors(dental: Tenant, cal: FakeCalendar) -> None:
    conv_id, _ = _conv(dental, "I'd like a check-up tomorrow morning")
    with tenant_session(dental.id) as s:
        p = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_id,
            kind="propose_appointment",
            params={"service_code": "checkup", "preferred_window": "next week", "notes": ""},
            risk="low",
            state="auto_approved",
        )
        s.add(p)
        s.flush()
        res = execute(s, dental, p)
        assert res.ok and res.result["offered"] == 3, res.error
        held = scheduling.offered_for(s, s.get(Conversation, conv_id))  # type: ignore[arg-type]
        assert len(held) == 3
        offer = s.scalar(
            select(Message).where(
                Message.conversation_id == conv_id, Message.direction == "outbound"
            )
        )
        assert offer is not None and "1. " in offer.body and "Reply with the number" in offer.body
        chosen = held[1].id
    fake = FakeLLM(
        script=[
            (
                "Great, I've passed that to the team to confirm.",
                [
                    ToolCall(
                        "confirm_appointment",
                        {"appointment_id": str(chosen), "service_code": "checkup"},
                        "t",
                    )
                ],
            )
        ]
    )
    with tenant_session(dental.id) as s:
        s.add(
            Message(
                tenant_id=dental.id,
                conversation_id=conv_id,
                direction="inbound",
                channel="webchat",
                author="customer",
                body="2 please",
            )
        )
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        conv.status = "open"
    with tenant_session(dental.id) as s:
        r = run_turn(s, dental, get_pack("dental"), fake, conv_id)
    assert "appointment_id=" in fake.calls[0]["system_volatile"], "the model saw the offered slots"
    assert r.decisions["confirm_appointment"] == "awaiting", (
        "checkup is not auto-confirm: staff approve"
    )
    with tenant_session(dental.id) as s:
        cp = s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id,
                ActionProposal.kind == "confirm_appointment",
            )
        )
        assert cp is not None
        cp.state = "approved"
        s.flush()
        execute(s, dental, cp)
        appt = s.get(Appointment, chosen)
        assert appt is not None and appt.status == "confirmed" and appt.external_ref == "fake:evt-1"
        others = [
            a.status
            for a in s.scalars(
                select(Appointment).where(
                    Appointment.conversation_id == conv_id, Appointment.id != chosen
                )
            )
        ]
        assert others == ["cancelled", "cancelled"], "the other two holds are released"


def test_empty_window_is_widened_to_next_available(dental: Tenant, cal: FakeCalendar) -> None:
    conv_id, _ = _conv(dental, "sunday please")
    with tenant_session(dental.id) as s:
        p = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_id,
            kind="propose_appointment",
            params={"service_code": "checkup", "preferred_window": "sunday", "notes": ""},
            risk="low",
            state="auto_approved",
        )
        s.add(p)
        s.flush()
        res = execute(s, dental, p)
        assert res.ok and res.result["offered"] == 3, (
            "no Sunday hours, so the next weekdays are offered"
        )
        assert "next available" in res.result["window"]
        offer = s.scalar(
            select(Message).where(
                Message.conversation_id == conv_id, Message.direction == "outbound"
            )
        )
        assert offer is not None and offer.body.startswith(
            "There's nothing free at the time you asked for"
        )


def test_reschedule_offers_choices_and_moves_the_booking_the_customer_picks(
    dental: Tenant, cal: FakeCalendar
) -> None:
    conv_id, contact_id = _conv(dental)
    day = _next_weekday_9am() + timedelta(days=7)
    with tenant_session(dental.id) as s:
        p = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_id,
            kind="confirm_appointment",
            params={},
            risk="low",
            state="auto_approved",
        )
        s.add(p)
        s.flush()
        appt = Appointment(
            tenant_id=dental.id,
            contact_id=contact_id,
            conversation_id=conv_id,
            proposal_id=p.id,
            starts_at=day.astimezone(UTC),
            ends_at=(day + timedelta(minutes=20)).astimezone(UTC),
            service_code="checkup",
            status="held",
        )
        s.add(appt)
        s.flush()
        scheduling.confirm(s, dental, cal, get_pack("dental"), appt, p.id)
        aid, ref, original = appt.id, appt.external_ref, appt.starts_at
    with tenant_session(dental.id) as s:
        rp = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_id,
            kind="reschedule_appointment",
            params={"appointment_id": str(aid), "new_window": "next week"},
            risk="medium",
            state="approved",
        )
        s.add(rp)
        s.flush()
        res = execute(s, dental, rp)
        assert res.ok and res.result["offered"] == 3, res.error
        appt = s.get(Appointment, aid)
        assert appt is not None and appt.starts_at == original, "nothing moves until they pick"
        offer = s.scalars(
            select(Message)
            .where(Message.conversation_id == conv_id, Message.direction == "outbound")
            .order_by(Message.created_at.desc())
        ).first()
        assert offer is not None and "1. " in offer.body and "current booking" in offer.body
        held = scheduling.offered_for(s, s.get(Conversation, conv_id))  # type: ignore[arg-type]
        assert len(held) == 3
        assert f"appointment_id={aid}" in scheduling.appointments_block(
            s,
            dental,
            s.get(Conversation, conv_id),  # type: ignore[arg-type]
        ), "the model is told these times would move the booking"
        chosen, chosen_at = held[1].id, held[1].starts_at
        cp = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_id,
            kind="confirm_appointment",
            params={"appointment_id": str(chosen), "service_code": "checkup"},
            risk="medium",
            state="approved",
        )
        s.add(cp)
        s.flush()
        res = execute(s, dental, cp)
        assert res.ok, res.error
    with tenant_session(dental.id) as s:
        appt = s.get(Appointment, aid)
        assert appt is not None and appt.status == "confirmed"
        assert appt.starts_at == chosen_at and appt.external_ref == ref
        assert cal.calls.count("create") == 1 and cal.calls.count("update") == 1
        assert len(cal.events) == 1, "one booking in the diary, at the new time"
        live = list(
            s.scalars(
                select(Appointment).where(
                    Appointment.conversation_id == conv_id,
                    Appointment.status.in_(("held", "confirmed")),
                )
            )
        )
        assert [a.id for a in live] == [aid], "every offered time is released"
        bodies = [
            m.body
            for m in s.scalars(
                select(Message).where(
                    Message.conversation_id == conv_id, Message.direction == "outbound"
                )
            )
        ]
        assert any(b.startswith("Moved: Check-up is now") for b in bodies)


@pytest.mark.parametrize(
    "model_calls",
    [
        [ToolCall("confirm_appointment", {"appointment_id": "2"}, "t")],  # the number, not the id
        [],  # no tool call at all
    ],
    ids=["model-passes-the-option-number", "model-calls-no-tool"],
)
def test_a_bare_number_picks_that_offered_slot(
    dental: Tenant, cal: FakeCalendar, model_calls: list[ToolCall]
) -> None:
    """Live on gpt-oss:120b the customer replied "1" and the model proposed
    confirm_appointment with appointment_id "1", which no approval could carry out."""
    conv_id, _ = _conv(dental, "A check-up next week please")
    with tenant_session(dental.id) as s:
        p = ActionProposal(
            tenant_id=dental.id,
            conversation_id=conv_id,
            kind="propose_appointment",
            params={"service_code": "checkup", "preferred_window": "next week", "notes": ""},
            risk="low",
            state="auto_approved",
        )
        s.add(p)
        s.flush()
        assert execute(s, dental, p).ok
        chosen = scheduling.offered_for(s, s.get(Conversation, conv_id))[1].id  # type: ignore[arg-type]
        s.add(
            Message(
                tenant_id=dental.id,
                conversation_id=conv_id,
                direction="inbound",
                channel="webchat",
                author="customer",
                body="2",
            )
        )
    with tenant_session(dental.id) as s:
        run_turn(s, dental, get_pack("dental"), FakeLLM(script=[("Lovely.", model_calls)]), conv_id)
        confirms = list(
            s.scalars(
                select(ActionProposal).where(
                    ActionProposal.conversation_id == conv_id,
                    ActionProposal.kind == "confirm_appointment",
                )
            )
        )
        assert [c.params["appointment_id"] for c in confirms] == [str(chosen)], "one, slot 2"
        assert confirms[0].state != "rejected"
