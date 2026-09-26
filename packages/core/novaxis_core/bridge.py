"""The booking bridge: a system of record for vendor tools that have no API we can use.

Many small businesses keep their real diary in software we cannot write to (no public
API, or a partner programme we have not joined yet). The bridge works with any of them:

- Writes: every booking change becomes a ticket with a short reference (NX-1A2B3C). The
  ticket is emailed to the office as a plain, structured message and listed in the
  dashboard. A person keys it into the vendor tool and clicks "Entered".
- Reads: the office uploads the vendor's diary export (CSV) once a day. Its busy times
  feed availability, so we never offer a slot the vendor diary already has.
- Conflicts: the vendor diary wins. If an export shows someone else in a slot we
  confirmed, our appointment is cancelled, the office gets a cancel ticket, and the
  customer is offered new times in the same conversation.

A vendor with a real API gets its own `SystemOfRecord` adapter later; the scheduler does
not change. See ADR 0015.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from novaxis_core.models import (
    Appointment,
    AuditLog,
    BridgeTicket,
    Contact,
    Conversation,
    Integration,
    Job,
    Tenant,
)
from novaxis_core.settings import get_settings
from novaxis_core.sor.base import Busy, ExternalRef, Health, Slot, overlaps

PROVIDER = "booking_bridge"
EMAIL_JOB = "bridge_email"
REF_RE = re.compile(r"\bNX-[0-9A-F]{6}\b", re.IGNORECASE)
STALE_AFTER = timedelta(hours=36)
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=120)
MAX_BLOCKS = 5000


class BridgeConfig(BaseModel):
    """What the owner sets on the integration."""

    model_config = ConfigDict(extra="forbid")
    vendor_name: str = Field(min_length=1, max_length=80)
    email_to: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    date_order: Literal["dmy", "mdy"] = "dmy"
    # Our service code -> the job or appointment type the office picks in the vendor tool.
    service_map: dict[str, str] = Field(default_factory=dict)


def ref_for(idempotency_key: str) -> str:
    """Short, stable, easy to read aloud. The same booking always gets the same reference."""
    return "NX-" + hashlib.sha1(idempotency_key.encode()).hexdigest()[:6].upper()


# --- Reading the vendor's diary export --------------------------------------------------


@dataclass(frozen=True)
class VendorBlock:
    starts_at: datetime
    ends_at: datetime
    ref: str | None
    label: str


@dataclass
class ImportReport:
    rows: int = 0
    imported: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    conflicts: int = 0


COLUMNS: dict[str, tuple[str, ...]] = {
    "start": (
        "start",
        "starts at",
        "starts_at",
        "start date/time",
        "start datetime",
        "appointment start",
        "scheduled start",
        "date/time",
        "datetime",
        "start time",
    ),
    "end": (
        "end",
        "ends at",
        "ends_at",
        "end date/time",
        "appointment end",
        "scheduled end",
        "finish",
        "end time",
    ),
    "date": ("date", "appointment date", "job date", "scheduled date"),
    "duration": (
        "duration",
        "duration (mins)",
        "duration (minutes)",
        "duration minutes",
        "minutes",
        "length",
    ),
    "status": ("status", "appointment status", "job status"),
}
TEXT_COLUMNS = (
    "reference",
    "ref",
    "notes",
    "description",
    "title",
    "summary",
    "job",
    "job name",
    "job type",
    "type",
    "details",
)

_DMY = re.compile(
    r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?:[ T,]+(\d{1,2}):(\d{2})(?::\d{2})?\s*([ap]m)?)?$",
    re.IGNORECASE,
)
_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*([ap]m)?$", re.IGNORECASE)


def _hour(h: int, ampm: str | None) -> int:
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and h < 12:
            return h + 12
        if ampm == "am" and h == 12:
            return 0
    return h


def parse_when(value: str, tz: ZoneInfo, order: str, on: datetime | None = None) -> datetime:
    """Accept ISO, UK or US numeric dates with optional time, or a bare time on date `on`."""
    v = value.strip()
    if not v:
        raise ValueError("empty date")
    try:
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo else dt.replace(tzinfo=tz)
    except ValueError:
        pass
    m = _DMY.match(v)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        day, month = (a, b) if order == "dmy" else (b, a)
        year = y + 2000 if y < 100 else y
        h = _hour(int(m[4]), m[6]) if m[4] else 0
        mi = int(m[5]) if m[5] else 0
        return datetime(year, month, day, h, mi, tzinfo=tz)
    t = _TIME.match(v)
    if t and on is not None:
        return on.replace(hour=_hour(int(t[1]), t[3]), minute=int(t[2]))
    raise ValueError(f"cannot read {value!r} as a date or time")


def _column(headers: dict[str, str], key: str) -> str | None:
    for name in COLUMNS[key]:
        if name in headers:
            return headers[name]
    return None


def parse_export(
    text: str, tz: ZoneInfo, order: str = "dmy"
) -> tuple[list[VendorBlock], ImportReport]:
    """Read a vendor diary export. Unknown columns are ignored; each bad row is reported."""
    report = ImportReport()
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        report.errors.append("the file has no header row")
        return [], report
    headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    start_col = _column(headers, "start")
    date_col = _column(headers, "date")
    end_col = _column(headers, "end")
    dur_col = _column(headers, "duration")
    status_col = _column(headers, "status")
    text_cols = [headers[h] for h in TEXT_COLUMNS if h in headers]
    if start_col is None and date_col is None:
        report.errors.append("no start or date column found")
        return [], report
    if end_col is None and dur_col is None:
        report.errors.append("no end time or duration column found")
        return [], report

    blocks: list[VendorBlock] = []
    for n, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        report.rows += 1
        if status_col and "cancel" in (row.get(status_col) or "").lower():
            report.skipped += 1
            continue
        try:
            day = parse_when(row[date_col], tz, order) if date_col else None
            if start_col and (row.get(start_col) or "").strip():
                start = parse_when(row[start_col], tz, order, on=day)
            elif day is not None:
                raise ValueError("no start time")
            else:
                raise ValueError("no start")
            if end_col and (row.get(end_col) or "").strip():
                end = parse_when(row[end_col], tz, order, on=start)
            elif dur_col and (row.get(dur_col) or "").strip():
                end = start + timedelta(minutes=int(float(row[dur_col])))
            else:
                raise ValueError("no end time or duration")
            if end <= start:
                raise ValueError("ends before it starts")
        except (ValueError, KeyError) as exc:
            report.skipped += 1
            if len(report.errors) < 10:
                report.errors.append(f"row {n}: {exc}")
            continue
        joined = " ".join((row.get(c) or "") for c in text_cols)
        found = REF_RE.search(joined)
        blocks.append(
            VendorBlock(
                starts_at=start.astimezone(UTC),
                ends_at=end.astimezone(UTC),
                ref=found[0].upper() if found else None,
                label=joined.strip()[:80],
            )
        )
    report.imported = len(blocks)
    return blocks, report


def _stored(blocks: list[VendorBlock], now: datetime) -> list[dict[str, Any]]:
    keep = [b for b in blocks if b.ends_at > now - KEEP_BEHIND and b.starts_at < now + KEEP_AHEAD]
    keep.sort(key=lambda b: b.starts_at)
    return [
        {"s": b.starts_at.isoformat(), "e": b.ends_at.isoformat(), "ref": b.ref, "label": b.label}
        for b in keep[:MAX_BLOCKS]
    ]


def _loaded(integ: Integration) -> list[VendorBlock]:
    return [
        VendorBlock(
            datetime.fromisoformat(b["s"]),
            datetime.fromisoformat(b["e"]),
            b.get("ref"),
            b.get("label", ""),
        )
        for b in integ.config.get("busy") or []
    ]


def bridge_integration(session: Session) -> Integration | None:
    return session.scalar(
        select(Integration).where(
            Integration.provider == PROVIDER, Integration.health != "disconnected"
        )
    )


def tenant_tz(tenant: Tenant) -> ZoneInfo:
    return ZoneInfo(str(tenant.settings.get("timezone") or "Europe/London"))


def import_export(
    session: Session, tenant: Tenant, integ: Integration, text: str, now: datetime | None = None
) -> ImportReport:
    """Replace the stored vendor diary with this export, then let the vendor win conflicts."""
    now = now or datetime.now(UTC)
    cfg = BridgeConfig.model_validate(integ.config.get("settings") or {"vendor_name": "vendor"})
    blocks, report = parse_export(text, tenant_tz(tenant), cfg.date_order)
    if report.imported == 0 and report.errors:
        return report  # a broken file must not wipe yesterday's good diary
    integ.config = {
        **integ.config,
        "busy": _stored(blocks, now),
        "last_import_at": now.isoformat(),
        "last_import_report": {k: v for k, v in asdict(report).items() if k != "conflicts"},
    }
    flag_modified(integ, "config")
    integ.health = "connected"
    session.flush()
    report.conflicts = resolve_conflicts(session, tenant, blocks, now)
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor="bridge:import",
            event="bridge.imported",
            subject_table="integrations",
            subject_id=integ.id,
            diff={
                "rows": report.rows,
                "imported": report.imported,
                "skipped": report.skipped,
                "conflicts": report.conflicts,
            },
        )
    )
    session.flush()
    return report


def _ours(block: VendorBlock, appt: Appointment) -> bool:
    ref = (appt.external_ref or "").partition(":")[2].upper()
    if block.ref and ref and block.ref == ref:
        return True
    return block.starts_at == appt.starts_at and block.ends_at == appt.ends_at


def resolve_conflicts(
    session: Session, tenant: Tenant, blocks: list[VendorBlock], now: datetime
) -> int:
    """The vendor diary wins. Held offers under a vendor booking are withdrawn silently;
    a confirmed appointment under someone else's booking is cancelled and re-offered."""
    from novaxis_core import scheduling

    appts = list(
        session.scalars(
            select(Appointment).where(
                Appointment.status.in_(["held", "confirmed"]), Appointment.ends_at > now
            )
        )
    )
    n = 0
    for a in appts:
        clash = [
            b
            for b in blocks
            if overlaps(a.starts_at, a.ends_at, b.starts_at, b.ends_at) and not _ours(b, a)
        ]
        if not clash:
            continue
        n += 1
        if a.status == "held":
            a.status = "cancelled"
            scheduling._audit(
                session, tenant, "appointment.hold_withdrawn", a, reason="vendor diary"
            )
            continue
        _vendor_wins(session, tenant, a, now)
    session.flush()
    return n


def _vendor_wins(session: Session, tenant: Tenant, a: Appointment, now: datetime) -> None:
    from novaxis_core import scheduling

    old_start = a.starts_at
    a.status = "cancelled"
    scheduling.cancel_appointment_steps(session, a)
    bridge = system_for(session, tenant)
    if a.external_ref and a.external_ref.startswith(f"{PROVIDER}:"):
        bridge.cancel_booking(ExternalRef(PROVIDER, a.external_ref.partition(":")[2]))
    scheduling._audit(session, tenant, "appointment.vendor_conflict", a, starts_at=old_start)
    session.flush()
    conv = session.get(Conversation, a.conversation_id) if a.conversation_id else None
    contact = session.get(Contact, a.contact_id)
    if conv is None or contact is None or a.proposal_id is None:
        return
    location = scheduling.location_for(session, tenant)
    tz = scheduling.tz_for(tenant, location)
    window = scheduling.Window(
        now, now + timedelta(days=get_settings().availability_days), "next available"
    )
    slots = scheduling.availability(session, tenant, bridge, a.service_code, window)
    held = scheduling.hold(session, tenant, contact, conv, a.service_code, slots, a.proposal_id)
    name = str(scheduling._service(tenant, a.service_code).get("name", a.service_code))
    text = (
        f"Sorry, the {name} time we confirmed for {scheduling.fmt(old_start, tz)} has just "
        "been taken in our diary, so it is cancelled. "
        + scheduling.offer_text(tenant, tz, held, name)
    )
    scheduling._enqueue_send(session, tenant, conv, text)


# --- Tickets: writing to the vendor tool through a person --------------------------------


def create_ticket(
    session: Session,
    tenant: Tenant,
    ref: str,
    action: str,
    slot: Slot,
    summary: str,
    details: dict[str, str],
) -> BridgeTicket:
    """Idempotent: the same change to the same booking is one ticket and one email."""
    existing = session.scalar(
        select(BridgeTicket).where(
            BridgeTicket.ref == ref,
            BridgeTicket.action == action,
            BridgeTicket.starts_at == slot.starts_at,
        )
    )
    if existing is not None:
        return existing
    t = BridgeTicket(
        tenant_id=tenant.id,
        ref=ref,
        action=action,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        summary=summary[:300],
        details=details,
        status="queued",
    )
    session.add(t)
    session.flush()
    session.add(Job(tenant_id=tenant.id, kind=EMAIL_JOB, payload={"ticket_id": str(t.id)}))
    session.flush()
    return t


def _last_ticket(session: Session, ref: str) -> BridgeTicket | None:
    return session.scalar(
        select(BridgeTicket)
        .where(BridgeTicket.ref == ref, BridgeTicket.action != "cancel")
        .order_by(BridgeTicket.created_at.desc())
        .limit(1)
    )


ACTION_WORDS = {"create": "NEW booking", "update": "CHANGED booking", "cancel": "CANCELLED booking"}


def render_email(ticket: BridgeTicket, cfg: BridgeConfig, tz: ZoneInfo) -> tuple[str, str]:
    d = ticket.details
    start = ticket.starts_at.astimezone(tz)
    end = ticket.ends_at.astimezone(tz)
    when = f"{start:%a %d %b %Y, %H:%M}–{end:%H:%M} ({tz.key})"
    job_type = cfg.service_map.get(d.get("service_code", "")) or d.get("service_name", "")
    what = ACTION_WORDS[ticket.action]
    subject = f"[Novaxis] {what} {ticket.ref}: {job_type or ticket.summary} {start:%a %d %b %H:%M}"
    instruction = {
        "create": f"Please enter this booking in {cfg.vendor_name}.",
        "update": f"Please move this booking in {cfg.vendor_name} to the new time below.",
        "cancel": f"Please remove this booking from {cfg.vendor_name} if it was entered.",
    }[ticket.action]
    lines = [
        instruction,
        "",
        f"Reference: {ticket.ref}   (put this in the job notes so tomorrow's export matches it)",
        f"When: {when}",
        f"Job type in {cfg.vendor_name}: {job_type}",
        f"Customer: {d.get('customer_name', '')}",
        f"Phone: {d.get('customer_phone', '')}",
        f"Email: {d.get('customer_email', '')}",
        "",
        f"When done, click Entered on the Schedule page: {get_settings().public_web_url}/schedule",
    ]
    return subject, "\n".join(lines)


def send_ticket_email(session: Session, tenant: Tenant, ticket_id: uuid.UUID) -> str:
    """The job handler. Without email configured the ticket still shows in the dashboard."""
    from novaxis_core.channels import get_adapter

    ticket = session.get(BridgeTicket, ticket_id)
    if ticket is None or ticket.status in ("emailed", "entered"):
        return "nothing to do"
    integ = bridge_integration(session)
    cfg = BridgeConfig.model_validate(
        (integ.config.get("settings") if integ else None) or {"vendor_name": "the booking system"}
    )
    email_cfg = ((tenant.settings.get("channels") or {}).get("email") or {}).get("config") or {}
    if (
        not cfg.email_to
        or not get_settings().postmark_server_token
        or not email_cfg.get("from_address")
    ):
        ticket.status = "not_emailed"
        return "not emailed: email not configured"
    subject, body = render_email(ticket, cfg, tenant_tz(tenant))
    get_adapter("email").send(
        to=cfg.email_to,
        body=body,
        # The adapter formats the subject; braces in a vendor or service name must survive.
        tenant_channel_config={
            **email_cfg,
            "subject": subject.replace("{", "{{").replace("}", "}}"),
        },
    )
    ticket.status = "emailed"
    ticket.emailed_at = datetime.now(UTC)
    return "emailed"


def mark_entered(
    session: Session, tenant: Tenant, ticket: BridgeTicket, user_id: uuid.UUID
) -> BridgeTicket:
    if ticket.status != "entered":
        ticket.status = "entered"
        ticket.entered_at = datetime.now(UTC)
        ticket.entered_by = user_id
        session.add(
            AuditLog(
                tenant_id=tenant.id,
                actor=f"user:{user_id}",
                event="bridge.entered",
                subject_table="bridge_tickets",
                subject_id=ticket.id,
                diff={"ref": ticket.ref, "action": ticket.action},
            )
        )
        session.flush()
    return ticket


def bridge_health(integ: Integration, now: datetime | None = None) -> Health:
    now = now or datetime.now(UTC)
    cfg = integ.config.get("settings") or {}
    last = integ.config.get("last_import_at")
    if not last:
        return Health(False, f"no diary export from {cfg.get('vendor_name', 'the vendor')} yet")
    age = now - datetime.fromisoformat(last)
    if age > STALE_AFTER:
        return Health(False, f"diary export is {int(age.total_seconds() // 3600)} hours old")
    if not cfg.get("email_to"):
        return Health(True, "diary current; hand-offs show in the dashboard only (no office email)")
    return Health(True, "diary current")


# --- The system of record ----------------------------------------------------------------


class BookingBridge:
    provider = PROVIDER

    def __init__(self, session: Session, tenant: Tenant, integ: Integration) -> None:
        self.session, self.tenant, self.integ = session, tenant, integ

    def busy(
        self, calendar_ref: str | None, window_start: datetime, window_end: datetime
    ) -> list[Busy]:
        return [
            Busy(b.starts_at, b.ends_at)
            for b in _loaded(self.integ)
            if overlaps(b.starts_at, b.ends_at, window_start, window_end)
        ]

    def create_booking(
        self,
        calendar_ref: str | None,
        slot: Slot,
        summary: str,
        description: str,
        idempotency_key: str,
        details: dict[str, str] | None = None,
    ) -> ExternalRef:
        ref = ref_for(idempotency_key)
        create_ticket(self.session, self.tenant, ref, "create", slot, summary, details or {})
        return ExternalRef(PROVIDER, ref)

    def update_booking(self, ref: ExternalRef, slot: Slot) -> None:
        last = _last_ticket(self.session, ref.ref)
        create_ticket(
            self.session,
            self.tenant,
            ref.ref,
            "update",
            slot,
            last.summary if last else "booking",
            last.details if last else {},
        )

    def cancel_booking(self, ref: ExternalRef) -> None:
        last = _last_ticket(self.session, ref.ref)
        if last is None:
            return
        create_ticket(
            self.session,
            self.tenant,
            ref.ref,
            "cancel",
            Slot(last.starts_at, last.ends_at),
            last.summary,
            last.details,
        )

    def health(self) -> Health:
        return bridge_health(self.integ)


def system_for(session: Session, tenant: Tenant) -> BookingBridge:
    integ = bridge_integration(session)
    if integ is None:
        raise LookupError("no booking bridge connected")
    return BookingBridge(session, tenant, integ)
