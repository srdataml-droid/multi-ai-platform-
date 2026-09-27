"""ingest(): one inbound -> one message and one job; replays, opt-outs and matching."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from novaxis_core.channels import NormalisedInbound, ProviderRef, get_adapter, register_adapter
from novaxis_core.channels.twilio_sms import TwilioSmsAdapter
from novaxis_core.inbound import OPT_OUT_CONFIRMATION, ingest
from novaxis_core.models import Contact, Conversation, Job, Message, Tenant
from novaxis_core.outbound import send_message
from novaxis_core.routing import resolve_tenant
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session


class FakeSms:
    channel = "twilio_sms"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def verify_signature(self, request: Any) -> bool:
        return True

    def parse_inbound(self, request: Any) -> NormalisedInbound:
        raise NotImplementedError

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        self.sent.append((to, body))
        return ProviderRef(provider_ref=f"fake-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def hvac(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        return t


@pytest.fixture
def fake_sms() -> FakeSms:
    fake = FakeSms()
    register_adapter(fake)  # type: ignore[arg-type]
    yield fake  # type: ignore[misc]
    register_adapter(TwilioSmsAdapter())


def _sms(body: str, ref: str, phone: str = "+447700900123") -> NormalisedInbound:
    return NormalisedInbound(
        channel="twilio_sms",
        provider_ref=ref,
        tenant_ref="+15005550006",
        sender_phone=phone,
        body=body,
    )


def _counts(tenant_id: uuid.UUID) -> tuple[int, int, int]:
    with tenant_session(tenant_id) as s:
        m = s.scalar(select(func.count()).select_from(Message)) or 0
        j = s.scalar(select(func.count()).select_from(Job)) or 0
        c = s.scalar(select(func.count()).select_from(Contact)) or 0
        return m, j, c


def test_one_inbound_creates_one_message_and_one_job(hvac: Tenant) -> None:
    ref = f"SM-{uuid.uuid4().hex[:8]}"
    before = _counts(hvac.id)
    with tenant_session(hvac.id) as s:
        r = ingest(s, hvac, _sms("boiler broken", ref))
        assert r.job_id is not None and not r.duplicate
        job = s.get(Job, r.job_id)
        assert job is not None and job.kind == "worker_turn"
        assert job.payload["conversation_id"] == str(r.conversation_id)
    after = _counts(hvac.id)
    assert after[0] - before[0] == 1 and after[1] - before[1] == 1


def test_replayed_webhook_is_a_noop(hvac: Tenant) -> None:
    ref = f"SM-{uuid.uuid4().hex[:8]}"
    with tenant_session(hvac.id) as s:
        first = ingest(s, hvac, _sms("hello", ref))
    before = _counts(hvac.id)
    with tenant_session(hvac.id) as s:
        again = ingest(s, hvac, _sms("hello", ref))
    assert again.duplicate and again.message_id == first.message_id and again.job_id is None
    assert _counts(hvac.id) == before


def test_same_phone_threads_into_same_contact_and_conversation(hvac: Tenant) -> None:
    phone = f"+4477009{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        a = ingest(s, hvac, _sms("first", f"SM-{uuid.uuid4().hex[:8]}", phone))
        b = ingest(s, hvac, _sms("second", f"SM-{uuid.uuid4().hex[:8]}", phone))
    assert a.contact_id == b.contact_id and a.conversation_id == b.conversation_id


def test_email_matches_case_insensitively_never_by_name(hvac: Tenant) -> None:
    addr = f"person-{uuid.uuid4().hex[:6]}@example.com"

    def em(body: str, sender: str, name: str) -> NormalisedInbound:
        return NormalisedInbound(
            channel="email",
            provider_ref=f"pm-{uuid.uuid4().hex[:8]}",
            tenant_ref="demo-hvac@inbound.novaxis.test",
            sender_email=sender,
            sender_name=name,
            body=body,
        )

    with tenant_session(hvac.id) as s:
        a = ingest(s, hvac, em("hi", addr, "Alice"))
        b = ingest(s, hvac, em("hi again", addr.upper(), "Alice"))
        c = ingest(s, hvac, em("hi", f"other-{uuid.uuid4().hex[:6]}@example.com", "Alice"))
    assert a.contact_id == b.contact_id
    assert c.contact_id != a.contact_id


def test_stop_flips_consent_sends_confirmation_and_creates_no_job(
    hvac: Tenant, fake_sms: FakeSms
) -> None:
    phone = f"+4477008{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        ingest(s, hvac, _sms("hello", f"SM-{uuid.uuid4().hex[:8]}", phone))
    before = _counts(hvac.id)
    with tenant_session(hvac.id) as s:
        r = ingest(s, hvac, _sms("STOP", f"SM-{uuid.uuid4().hex[:8]}", phone))
        assert r.opted_out and r.job_id is None
        contact = s.get(Contact, r.contact_id)
        assert contact is not None and contact.consent["status"] == "opted_out"
        conv = s.get(Conversation, r.conversation_id)
        assert conv is not None and conv.status == "closed"
    after = _counts(hvac.id)
    assert after[1] == before[1], "no job for STOP"
    assert after[0] - before[0] == 2, "the STOP itself plus the confirmation"
    assert fake_sms.sent == [(phone, OPT_OUT_CONFIRMATION)]


def test_opted_out_contact_is_not_answered_until_start(hvac: Tenant, fake_sms: FakeSms) -> None:
    phone = f"+4477007{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        ingest(s, hvac, _sms("stop", f"SM-{uuid.uuid4().hex[:8]}", phone))
        r = ingest(s, hvac, _sms("are you there?", f"SM-{uuid.uuid4().hex[:8]}", phone))
        assert r.opted_out and r.job_id is None
        r2 = ingest(s, hvac, _sms("START", f"SM-{uuid.uuid4().hex[:8]}", phone))
        assert not r2.opted_out
        r3 = ingest(s, hvac, _sms("hello again", f"SM-{uuid.uuid4().hex[:8]}", phone))
        assert r3.job_id is not None
    assert len(fake_sms.sent) == 2  # opt-out confirmation, opt-in confirmation


def test_send_message_fills_delivery_columns_once(hvac: Tenant, fake_sms: FakeSms) -> None:
    phone = f"+4477006{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        r = ingest(s, hvac, _sms("hello", f"SM-{uuid.uuid4().hex[:8]}", phone))
        out = Message(
            tenant_id=hvac.id,
            conversation_id=r.conversation_id,
            direction="outbound",
            channel="twilio_sms",
            author="worker",
            body="Hi there",
        )
        s.add(out)
        s.flush()
        out_id = out.id
    with tenant_session(hvac.id) as s:
        sent = send_message(s, hvac, out_id)
        assert sent.provider_ref and sent.provider_ref.startswith("fake-")
        assert sent.delivered_at is not None
        first_ref = sent.provider_ref
    with tenant_session(hvac.id) as s:
        again = send_message(s, hvac, out_id)
        assert again.provider_ref == first_ref
    assert fake_sms.sent == [(phone, "Hi there")]


def test_send_refuses_opted_out_contact(hvac: Tenant, fake_sms: FakeSms) -> None:
    phone = f"+4477005{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        r = ingest(s, hvac, _sms("stop", f"SM-{uuid.uuid4().hex[:8]}", phone))
        out = Message(
            tenant_id=hvac.id,
            conversation_id=r.conversation_id,
            direction="outbound",
            channel="twilio_sms",
            author="worker",
            body="Marketing!",
        )
        s.add(out)
        s.flush()
        out_id = out.id
    with pytest.raises(PermissionError):
        with tenant_session(hvac.id) as s:
            send_message(s, hvac, out_id)


def test_routing_by_number_email_and_slug(hvac: Tenant, migrated: str) -> None:
    with service_session(migrated) as s:
        assert resolve_tenant(s, "twilio_sms", "+15005550006").slug == "demo-hvac"  # type: ignore[union-attr]
        assert resolve_tenant(s, "twilio_sms", "+15005550007").slug == "demo-dental"  # type: ignore[union-attr]
        assert resolve_tenant(s, "email", "DEMO-HVAC@inbound.novaxis.test").slug == "demo-hvac"  # type: ignore[union-attr]
        assert resolve_tenant(s, "webchat", "demo-dental").slug == "demo-dental"  # type: ignore[union-attr]
        assert resolve_tenant(s, "twilio_sms", "+10000000000") is None
        assert get_adapter("webchat").channel == "webchat"


def _job_for(tid: uuid.UUID, conv_id: uuid.UUID) -> bool:
    with tenant_session(tid) as s:
        return (
            s.scalar(
                select(func.count()).where(
                    Job.kind == "worker_turn",
                    Job.payload["conversation_id"].astext == str(conv_id),
                )
            )
            or 0
        ) > 0


def test_stop_on_web_chat_is_just_a_message(hvac: Tenant) -> None:
    v = uuid.uuid4().hex[:10]
    with tenant_session(hvac.id) as s:
        r = ingest(
            s,
            hvac,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:1",
                tenant_ref="demo-hvac",
                sender_visitor_id=v,
                body="stop",
            ),
        )
        assert not r.opted_out
        contact = s.get(Contact, r.contact_id)
        assert contact is not None and contact.consent.get("status") != "opted_out"
    assert _job_for(hvac.id, r.conversation_id), "the assistant still answers"


def test_cancel_by_text_cancels_the_booking_not_the_customer(
    hvac: Tenant, fake_sms: FakeSms
) -> None:
    from datetime import UTC, datetime, timedelta

    from novaxis_core.models import Appointment

    phone = f"+4477009{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        first = ingest(s, hvac, _sms("boiler is broken", f"SM-{uuid.uuid4().hex[:8]}", phone))
        start = datetime.now(UTC) + timedelta(days=2)
        s.add(
            Appointment(
                tenant_id=hvac.id,
                contact_id=first.contact_id,
                conversation_id=first.conversation_id,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                service_code="repair_visit",
                status="confirmed",
            )
        )
    with tenant_session(hvac.id) as s:
        r = ingest(s, hvac, _sms("Cancel", f"SM-{uuid.uuid4().hex[:8]}", phone))
        assert not r.opted_out
        contact = s.get(Contact, r.contact_id)
        assert contact is not None and contact.consent.get("status") != "opted_out"
    assert _job_for(hvac.id, r.conversation_id), "the assistant handles the cancellation"
    assert not any(OPT_OUT_CONFIRMATION in body for _, body in fake_sms.sent)


def test_cancel_by_text_with_nothing_booked_still_opts_out(hvac: Tenant, fake_sms: FakeSms) -> None:
    phone = f"+4477008{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        r = ingest(s, hvac, _sms("CANCEL", f"SM-{uuid.uuid4().hex[:8]}", phone))
        assert r.opted_out


def test_reply_c_confirms_the_next_appointment(hvac: Tenant, fake_sms: FakeSms) -> None:
    from datetime import UTC, datetime, timedelta

    from novaxis_core.models import Appointment

    phone = f"+4477006{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        first = ingest(s, hvac, _sms("boiler service please", f"SM-{uuid.uuid4().hex[:8]}", phone))
        start = datetime.now(UTC) + timedelta(days=2)
        a = Appointment(
            tenant_id=hvac.id,
            contact_id=first.contact_id,
            conversation_id=first.conversation_id,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            service_code="boiler_service",
            status="confirmed",
        )
        s.add(a)
        s.flush()
        appt_id = a.id
    with tenant_session(hvac.id) as s:
        r = ingest(s, hvac, _sms("C", f"SM-{uuid.uuid4().hex[:8]}", phone))
        job = s.get(Job, r.job_id)
        assert job is not None and job.kind == "send_message", "a fixed thank-you, no model turn"
        appt = s.get(Appointment, appt_id)
        assert appt is not None and appt.customer_confirmed_at is not None
