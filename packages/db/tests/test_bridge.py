"""The booking bridge against real rows: hand-off tickets, the email job, diary imports and
the vendor-wins conflict rule. Each test gets its own tenant so a connected bridge never
leaks into another test's scheduling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from novaxis_core import scheduling
from novaxis_core.bridge import (
    EMAIL_JOB,
    PROVIDER,
    BookingBridge,
    bridge_health,
    import_export,
    mark_entered,
    send_ticket_email,
)
from novaxis_core.channels import NormalisedInbound, get_adapter, register_adapter
from novaxis_core.channels.base import ProviderRef
from novaxis_core.inbound import ingest
from novaxis_core.models import (
    ActionProposal,
    Appointment,
    AuditLog,
    BridgeTicket,
    Contact,
    Conversation,
    Integration,
    Job,
    Location,
    Message,
    Tenant,
)
from novaxis_core.settings import get_settings
from novaxis_core.sor import Slot, set_sor_override, system_of_record
from novaxis_core.sor.business_hours import BusinessHoursCalendar
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

TZ = ZoneInfo("Europe/London")


@pytest.fixture
def shop(migrated: str) -> uuid.UUID:
    """A fresh HVAC tenant (demo settings) with the bridge connected."""
    set_sor_override(None)
    with service_session(migrated) as s:
        seed(s)
        demo = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert demo is not None
        t = Tenant(
            name="Bridge Heating",
            slug=f"bridge-{uuid.uuid4().hex[:8]}",
            pack_id="hvac",
            status="active",
            settings=dict(demo.settings),
        )
        s.add(t)
        s.flush()
        s.add(Location(tenant_id=t.id, name="Main"))
        s.add(
            Integration(
                tenant_id=t.id,
                provider=PROVIDER,
                health="connected",
                config={
                    "settings": {
                        "vendor_name": "Acme Jobs",
                        "email_to": "office@x.test",
                        "date_order": "dmy",
                        "service_map": {"repair_visit": "Callout"},
                    }
                },
            )
        )
        return t.id


def _tenant(s: Any, tid: uuid.UUID) -> Tenant:
    t = s.get(Tenant, tid)
    assert t is not None
    return t


def _next_weekday(hour: int) -> datetime:
    d = datetime.now(TZ) + timedelta(days=2)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


def _held(tid: uuid.UUID, start: datetime, minutes: int = 90) -> tuple[uuid.UUID, uuid.UUID]:
    """A conversation with one held slot for a repair visit; returns (appointment, proposal)."""
    v = uuid.uuid4().hex[:10]
    with tenant_session(tid) as s:
        t = _tenant(s, tid)
        r = ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:x",
                tenant_ref=t.slug,
                sender_visitor_id=v,
                body="boiler broken",
                sender_name="Sam",
            ),
        )
        contact = s.get(Contact, r.contact_id)
        assert contact is not None
        contact.display_name = "Sam Jones"
        contact.phones = ["+447700900123"]
        conv = s.get(Conversation, r.conversation_id)
        p = ActionProposal(
            tenant_id=tid,
            conversation_id=conv.id,
            kind="propose_appointment",
            params={},
            risk="low",
            state="executed",
        )
        s.add(p)
        s.flush()
        slot = Slot(start.astimezone(UTC), (start + timedelta(minutes=minutes)).astimezone(UTC))
        [a] = scheduling.hold(s, t, contact, conv, "repair_visit", [slot], p.id)
        return a.id, p.id


def _confirm(tid: uuid.UUID, appt_id: uuid.UUID, proposal_id: uuid.UUID) -> str:
    with tenant_session(tid) as s:
        t = _tenant(s, tid)
        a = s.get(Appointment, appt_id)
        scheduling.confirm(s, t, system_of_record(s, t), get_pack("hvac"), a, proposal_id)
        return str(a.external_ref)


def test_bridge_is_the_system_of_record_while_connected(shop: uuid.UUID) -> None:
    with tenant_session(shop) as s:
        t = _tenant(s, shop)
        assert isinstance(system_of_record(s, t), BookingBridge)
        integ = s.scalar(select(Integration).where(Integration.provider == PROVIDER))
        integ.health = "disconnected"
        s.flush()
        assert isinstance(system_of_record(s, t), BusinessHoursCalendar)


def test_confirm_writes_one_ticket_with_what_the_office_needs(shop: uuid.UUID) -> None:
    appt_id, prop_id = _held(shop, _next_weekday(10))
    ref = _confirm(shop, appt_id, prop_id)
    assert ref.startswith("booking_bridge:NX-")
    _confirm(shop, appt_id, prop_id)  # a retried job
    with tenant_session(shop) as s:
        [ticket] = s.scalars(select(BridgeTicket))
        assert ticket.ref == ref.partition(":")[2] and ticket.action == "create"
        assert ticket.status == "queued"
        assert ticket.details["service_code"] == "repair_visit"
        assert ticket.details["customer_name"] == "Sam Jones"
        assert ticket.details["customer_phone"] == "+447700900123"
        jobs = s.scalar(select(func.count()).where(Job.kind == EMAIL_JOB))
        assert jobs == 1


class _Outbox:
    channel = "email"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        self.sent.append({"to": to, "body": body, "subject": tenant_channel_config["subject"]})
        return ProviderRef(provider_ref="fake")


def test_approved_booking_reaches_the_office_within_one_job_cycle(
    shop: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    from novaxis_core.llm import FakeLLM
    from novaxis_worker.loop import Picked, build_handlers, run_job

    appt_id, prop_id = _held(shop, _next_weekday(13))
    _confirm(shop, appt_id, prop_id)
    real = get_adapter("email")
    outbox = _Outbox()
    register_adapter(outbox)  # type: ignore[arg-type]
    try:
        # The env patch must end before the cache is cleared, or the fake token outlives it.
        with monkeypatch.context() as m:
            m.setenv("NOVAXIS_POSTMARK_SERVER_TOKEN", "pm-test")
            get_settings.cache_clear()
            with tenant_session(shop) as s:
                job = s.scalar(select(Job).where(Job.kind == EMAIL_JOB))
                assert job is not None
                picked = Picked(job.id, shop, EMAIL_JOB, 0)
            assert run_job(picked, build_handlers(get_pack, FakeLLM()))
    finally:
        register_adapter(real)
        get_settings.cache_clear()
    [mail] = outbox.sent
    assert mail["to"] == "office@x.test"
    assert "NEW booking NX-" in mail["subject"] and "Callout" in mail["subject"]
    assert "Please enter this booking in Acme Jobs." in mail["body"]
    with tenant_session(shop) as s:
        ticket = s.scalar(select(BridgeTicket))
        assert ticket is not None and ticket.status == "emailed" and ticket.emailed_at
        mark_entered(s, _tenant(s, shop), ticket, uuid.uuid4())
    with tenant_session(shop) as s:
        assert s.scalar(select(BridgeTicket.status)) == "entered"
        assert s.scalar(select(func.count()).where(AuditLog.event == "bridge.entered")) == 1


def test_without_email_the_hand_off_waits_in_the_dashboard(shop: uuid.UUID) -> None:
    appt_id, prop_id = _held(shop, _next_weekday(15))
    _confirm(shop, appt_id, prop_id)
    with tenant_session(shop) as s:
        t = _tenant(s, shop)
        ticket = s.scalar(select(BridgeTicket))
        assert send_ticket_email(s, t, ticket.id) == "not emailed: email not configured"
        assert ticket.status == "not_emailed"


def test_vendor_busy_times_are_never_offered(shop: uuid.UUID) -> None:
    day = _next_weekday(8)
    export = f"Start,End,Title\n{day:%d/%m/%Y} 08:00,{day:%d/%m/%Y} 12:00,Someone else\n"
    with tenant_session(shop) as s:
        t = _tenant(s, shop)
        integ = s.scalar(select(Integration).where(Integration.provider == PROVIDER))
        r = import_export(s, t, integ, export)
        assert (r.imported, r.conflicts) == (1, 0)
        window = scheduling.Window(
            day.astimezone(UTC), (day + timedelta(hours=10)).astimezone(UTC), ""
        )
        slots = scheduling.availability(s, t, system_of_record(s, t), "repair_visit", window)
    assert slots and all(sl.starts_at >= (day + timedelta(hours=4)).astimezone(UTC) for sl in slots)


def test_vendor_wins_a_clash_and_the_customer_is_re_offered(shop: uuid.UUID) -> None:
    start = _next_weekday(9)
    appt_id, prop_id = _held(shop, start)
    ref = _confirm(shop, appt_id, prop_id).partition(":")[2]
    ours = f"{start:%d/%m/%Y %H:%M},{start + timedelta(minutes=90):%d/%m/%Y %H:%M}"
    t0, t1 = start + timedelta(minutes=30), start + timedelta(hours=2)
    theirs = f"{t0:%d/%m/%Y %H:%M},{t1:%d/%m/%Y %H:%M}"

    with tenant_session(shop) as s:
        t = _tenant(s, shop)
        integ = s.scalar(select(Integration).where(Integration.provider == PROVIDER))
        # Our own booking, keyed in with the reference: not a clash.
        assert import_export(s, t, integ, f"Start,End,Notes\n{ours},Novaxis {ref}\n").conflicts == 0
        # Our own booking, keyed in without the reference but at exactly our time: not a clash.
        assert import_export(s, t, integ, f"Start,End,Notes\n{ours},typed by hand\n").conflicts == 0
        assert s.get(Appointment, appt_id).status == "confirmed"
        # Someone else in an overlapping slot: the vendor diary wins.
        assert import_export(s, t, integ, f"Start,End,Notes\n{theirs},Mrs Patel\n").conflicts == 1

    with tenant_session(shop) as s:
        a = s.get(Appointment, appt_id)
        assert a is not None and a.status == "cancelled"
        cancel = s.scalar(select(BridgeTicket).where(BridgeTicket.action == "cancel"))
        assert cancel is not None and cancel.ref == ref
        offers = list(
            s.scalars(
                select(Appointment).where(
                    Appointment.conversation_id == a.conversation_id, Appointment.status == "held"
                )
            )
        )
        assert offers, "new times were held for the customer"
        for o in offers:
            assert not scheduling.overlaps(
                o.starts_at,
                o.ends_at,
                (start + timedelta(minutes=30)).astimezone(UTC),
                (start + timedelta(hours=2)).astimezone(UTC),
            )
        text = s.scalar(
            select(Message.body)
            .where(Message.conversation_id == a.conversation_id, Message.direction == "outbound")
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        assert text is not None and "has just been taken in our diary" in text
        assert "Here are the times" in text
        assert (
            s.scalar(select(func.count()).where(AuditLog.event == "appointment.vendor_conflict"))
            == 1
        )


def test_a_held_offer_under_a_vendor_booking_is_withdrawn(shop: uuid.UUID) -> None:
    start = _next_weekday(11)
    appt_id, _ = _held(shop, start)
    with tenant_session(shop) as s:
        t = _tenant(s, shop)
        integ = s.scalar(select(Integration).where(Integration.provider == PROVIDER))
        export = f"Start,End\n{start:%d/%m/%Y %H:%M},{start + timedelta(hours=1):%d/%m/%Y %H:%M}\n"
        assert import_export(s, t, integ, export).conflicts == 1
    with tenant_session(shop) as s:
        assert s.get(Appointment, appt_id).status == "cancelled"
        assert s.scalar(select(func.count()).select_from(BridgeTicket)) == 0


def test_a_broken_export_keeps_yesterdays_diary_and_staleness_shows(shop: uuid.UUID) -> None:
    day = _next_weekday(8)
    with tenant_session(shop) as s:
        t = _tenant(s, shop)
        integ = s.scalar(select(Integration).where(Integration.provider == PROVIDER))
        assert not bridge_health(integ).ok, "no export yet"
        import_export(s, t, integ, f"Start,End\n{day:%d/%m/%Y %H:%M},{day:%d/%m/%Y} 09:00\n")
        assert bridge_health(integ).ok
        r = import_export(s, t, integ, "Title,Notes\nx,y\n")
        assert r.imported == 0 and r.errors
        assert len(integ.config["busy"]) == 1, "yesterday's diary is still there"
        later = datetime.now(UTC) + timedelta(hours=40)
        h = bridge_health(integ, later)
        assert not h.ok and "hours old" in h.detail
