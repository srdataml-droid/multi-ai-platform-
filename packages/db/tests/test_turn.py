"""run_turn against real rows with a scripted model."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM, ToolCall
from novaxis_core.models import ActionProposal, Conversation, Job, Message, Tenant, UsageEvent
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack


@pytest.fixture
def hvac(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        return t


def _webchat(body: str, visitor: str) -> NormalisedInbound:
    return NormalisedInbound(
        channel="webchat",
        provider_ref=f"webchat:{visitor}:{uuid.uuid4().hex[:8]}",
        tenant_ref="demo-hvac",
        sender_visitor_id=visitor,
        body=body,
    )


def _new_conversation(tenant: Tenant, body: str = "hi, boiler is making a noise") -> uuid.UUID:
    visitor = uuid.uuid4().hex[:12]
    with tenant_session(tenant.id) as s:
        return ingest(s, tenant, _webchat(body, visitor)).conversation_id


def test_turn_stores_reply_proposals_extracts_and_usage(hvac: Tenant) -> None:
    conv_id = _new_conversation(hvac)
    fake = FakeLLM(
        script=[
            (
                "Sorry to hear that. What's your name and postcode?",
                [
                    ToolCall("extract_fields", {"fields": {"problem": "boiler noise"}}, "t1"),
                    ToolCall(
                        "propose_appointment",
                        {"service_code": "repair_visit", "preferred_window": "asap", "notes": ""},
                        "t2",
                    ),
                ],
            )
        ]
    )
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        reply = s.get(Message, r.reply_message_id)
        assert reply is not None and reply.direction == "outbound" and reply.author == "worker"
        assert reply.provider_ref, "reply was sent through the channel adapter"
        assert reply.body.startswith("Hi, I'm the AI assistant for Demo Heating & Cooling"), (
            "disclosure on first reply"
        )
        assert "What's your name and postcode?" in reply.body
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.extracted == {"problem": "boiler noise"}
        assert conv.status == "waiting_customer"
        by_kind = {
            p.kind: p
            for p in s.scalars(
                select(ActionProposal).where(ActionProposal.conversation_id == conv_id)
            )
        }
        assert set(by_kind) == {"extract_fields", "propose_appointment", "reply"}
        assert by_kind["extract_fields"].state == "executed"
        assert by_kind["propose_appointment"].risk == "medium"
        assert by_kind["propose_appointment"].state == "awaiting"
        assert by_kind["reply"].state == "executed"
        notify = s.scalar(select(Job).where(Job.kind == "notify_staff"))
        assert notify is not None
        assert notify.payload["proposal_id"] == str(by_kind["propose_appointment"].id)
        usage = list(s.scalars(select(UsageEvent)))
        assert any(u.kind == "llm.worker_turn" and u.quantity == 15 for u in usage)
    call = fake.calls[0]
    assert call["task"] == "worker_turn" and "extract_fields" in call["tools"]
    assert "Business name: Demo Heating & Cooling" in call["system_volatile"]
    assert call["messages"][-1]["role"] == "user"


def test_disclosure_only_on_first_reply(hvac: Tenant) -> None:
    conv_id = _new_conversation(hvac)
    fake = FakeLLM(script=[("first", []), ("second", [])])
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        ingest(s, hvac, _webchat("more details", "x"))  # unrelated visitor; keep simple
        s.add(
            Message(
                tenant_id=hvac.id,
                conversation_id=conv_id,
                direction="inbound",
                channel="webchat",
                author="customer",
                body="ok",
            )
        )
        conv.status = "open"
    with tenant_session(hvac.id) as s:
        r2 = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        bodies = [
            m.body
            for m in s.scalars(
                select(Message)
                .where(Message.conversation_id == conv_id, Message.direction == "outbound")
                .order_by(Message.created_at)
            )
        ]
        assert bodies[0].startswith("Hi, I'm the AI assistant") and bodies[1] == "second"
        assert r2.reply_message_id is not None


def test_waiting_human_skips_the_model(hvac: Tenant) -> None:
    conv_id = _new_conversation(hvac)
    with tenant_session(hvac.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        conv.status = "waiting_human"
    fake = FakeLLM()
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    assert r.skipped_reason == "waiting_human" and r.reply_message_id is None
    assert fake.calls == []


def test_hand_to_human_flips_status(hvac: Tenant) -> None:
    conv_id = _new_conversation(hvac, "I want to speak to a real person")
    fake = FakeLLM(
        script=[
            (
                "Of course, a colleague will follow up shortly.",
                [ToolCall("hand_to_human", {"reason": "asked for a person"}, "t")],
            )
        ]
    )
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"


def test_emergency_keyword_bypasses_the_model(hvac: Tenant) -> None:
    conv_id = _new_conversation(hvac, "I can smell gas in the kitchen")
    fake = FakeLLM()
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    assert r.emergency and fake.calls == [], "no LLM call on the emergency branch"
    with tenant_session(hvac.id) as s:
        reply = s.get(Message, r.reply_message_id)
        assert reply is not None and "emergency services" in reply.body
        states = {
            p.kind: p.state
            for p in s.scalars(
                select(ActionProposal).where(ActionProposal.conversation_id == conv_id)
            )
        }
        assert states["escalate_emergency"] in ("executed", "failed"), "auto-approved, attempted"
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"


def test_booking_claim_without_proposal_is_flagged(hvac: Tenant) -> None:
    conv_id = _new_conversation(hvac)
    fake = FakeLLM(script=[("Great, I've booked you in for Tuesday at 9.", [])])
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        p = s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id, ActionProposal.kind == "verify_claim"
            )
        )
        assert p is not None and p.risk == "medium" and p.state == "awaiting"


def test_summary_regenerates_every_ten_messages(hvac: Tenant) -> None:
    conv_id = _new_conversation(hvac)
    fake = FakeLLM()
    with tenant_session(hvac.id) as s:
        for i in range(8):
            s.add(
                Message(
                    tenant_id=hvac.id,
                    conversation_id=conv_id,
                    direction="inbound" if i % 2 else "outbound",
                    channel="webchat",
                    author="customer" if i % 2 else "worker",
                    body=f"m{i}",
                )
            )
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, conv_id)  # 9 in history + this reply = 10
    with tenant_session(hvac.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.summary and conv.summary.startswith("Summary:")
    assert [c["task"] for c in fake.calls] == ["worker_turn", "summarise"]


def test_high_risk_proposal_is_rejected_and_reply_says_a_person_will_follow_up(
    hvac: Tenant,
) -> None:
    conv_id = _new_conversation(hvac, "can you charge my card now")
    fake = FakeLLM(
        script=[
            (
                "Sure, let me take payment.",
                [ToolCall("collect_payment", {"amount_minor": 5000, "currency": "GBP"}, "t")],
            )
        ]
    )
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    assert r.decisions["collect_payment"] == "rejected" and r.decisions["reply"] == "auto_approved"
    with tenant_session(hvac.id) as s:
        reply = s.get(Message, r.reply_message_id)
        assert reply is not None and "A member of the team will follow up" in reply.body


def test_safeguarding_message_stops_the_reply_and_hands_to_human(hvac: Tenant) -> None:
    conv_id = _new_conversation(hvac, "my daughter is 8 years old and home alone with the leak")
    fake = FakeLLM(script=[("I can help with that.", [])])
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    assert r.decisions["reply"] == "rejected"
    assert r.decisions["handoff_notice"] == "auto_approved"
    with tenant_session(hvac.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"
        out = list(
            s.scalars(
                select(Message).where(
                    Message.conversation_id == conv_id, Message.direction == "outbound"
                )
            )
        )
        assert len(out) == 1 and "I can help with that" not in out[0].body
        assert "member of the team will be in touch" in out[0].body


def test_owner_braces_in_the_disclosure_do_not_break_replies(hvac: Tenant) -> None:
    with service_session() as s:
        t = Tenant(
            name="Brace & Sons",
            slug=f"brace-{uuid.uuid4().hex[:8]}",
            pack_id="hvac",
            status="active",
            settings={**hvac.settings, "disclosure_text": "Hi {first name}, {business_name} AI."},
        )
        s.add(t)
        s.flush()
        s.expunge(t)
    with tenant_session(t.id) as s:
        conv_id = ingest(s, t, _webchat("hello", uuid.uuid4().hex[:12])).conversation_id
    with tenant_session(t.id) as s:
        r = run_turn(s, t, get_pack("hvac"), FakeLLM(script=[("How can I help?", [])]), conv_id)
        reply = s.get(Message, r.reply_message_id)
        assert reply is not None
        assert reply.body.startswith("Hi {first name}, Brace & Sons AI.")


class _Delivers:
    """A channel adapter whose sends always succeed (stands in for a working Twilio)."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.sent: list[str] = []

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, object]) -> object:
        from novaxis_core.channels.base import ProviderRef

        self.sent.append(to)
        return ProviderRef(provider_ref=f"fake-{len(self.sent)}")


def _emergency_reply(tenant: Tenant) -> tuple[str, str]:
    conv_id = _new_conversation(tenant, "I can smell gas in the kitchen")
    with tenant_session(tenant.id) as s:
        r = run_turn(s, tenant, get_pack("hvac"), FakeLLM(script=[]), conv_id)
        reply = s.get(Message, r.reply_message_id)
        esc = s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id,
                ActionProposal.kind == "escalate_emergency",
            )
        )
        assert reply is not None and esc is not None
        return reply.body, esc.state


def test_emergency_reply_never_claims_an_alert_that_failed(hvac: Tenant) -> None:
    body, state = _emergency_reply(hvac)  # no SMS or email provider in tests: the alert fails
    assert state == "failed"
    assert "leave the property" in body
    assert "I have alerted" not in body
    assert "could not reach anyone directly" in body


def test_emergency_reply_confirms_an_alert_that_was_delivered(hvac: Tenant) -> None:
    from novaxis_core.channels import get_adapter, register_adapter

    real = get_adapter("twilio_sms")
    fake = _Delivers("twilio_sms")
    register_adapter(fake)  # type: ignore[arg-type]
    try:
        body, state = _emergency_reply(hvac)
    finally:
        register_adapter(real)
    assert state == "executed" and fake.sent
    assert "I have alerted our on-call engineer" in body
    assert "could not reach" not in body


def test_auto_confirm_follows_the_booked_service_not_the_models_word(hvac: Tenant) -> None:
    from datetime import UTC, datetime, timedelta

    from novaxis_core import scheduling
    from novaxis_core.gate import GateContext
    from novaxis_core.models import Contact
    from novaxis_core.sor import Slot
    from novaxis_core.turn import propose

    settings = dict(hvac.settings)
    settings["services"] = [
        {**sv, "auto_confirm": sv["code"] == "boiler_service"} for sv in settings["services"]
    ]
    with service_session() as s:
        t = Tenant(
            name="Auto Co",
            slug=f"auto-{uuid.uuid4().hex[:8]}",
            pack_id="hvac",
            status="active",
            settings=settings,
        )
        s.add(t)
        s.flush()
        s.expunge(t)
    with tenant_session(t.id) as s:
        conv_id = ingest(s, t, _webchat("broken boiler", uuid.uuid4().hex[:12])).conversation_id
        conv = s.get(Conversation, conv_id)
        contact = s.get(Contact, conv.contact_id)
        p0 = ActionProposal(
            tenant_id=t.id,
            conversation_id=conv_id,
            kind="propose_appointment",
            params={},
            risk="low",
            state="executed",
        )
        s.add(p0)
        s.flush()
        start = datetime.now(UTC) + timedelta(days=3)
        [appt] = scheduling.hold(
            s, t, contact, conv, "repair_visit", [Slot(start, start + timedelta(minutes=90))], p0.id
        )
        # The model names the auto-confirm service; the appointment is a repair visit.
        p, d = propose(
            s,
            t,
            conv,
            "confirm_appointment",
            {"appointment_id": str(appt.id), "service_code": "boiler_service"},
            GateContext(tenant_settings=t.settings),
            "model proposal",
        )
        grounded = p.params["service_code"]
    assert d.state == "awaiting", "a repair visit waits for staff"
    assert grounded == "repair_visit"


class _Down:
    """An SMS provider that is down."""

    channel = "twilio_sms"

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, object]) -> object:
        raise ConnectionError("provider unavailable")


def test_a_reply_that_fails_to_send_is_retried_then_handed_to_a_person(hvac: Tenant) -> None:
    from novaxis_core.channels import get_adapter, register_adapter
    from novaxis_worker.loop import Picked, build_handlers, run_job

    phone = f"+4477007{uuid.uuid4().int % 100000:05d}"
    with tenant_session(hvac.id) as s:
        conv_id = ingest(
            s,
            hvac,
            NormalisedInbound(
                channel="twilio_sms",
                provider_ref=f"SM-{uuid.uuid4().hex[:8]}",
                tenant_ref="+15005550006",
                sender_phone=phone,
                body="radiator is cold",
            ),
        ).conversation_id
    real = get_adapter("twilio_sms")
    register_adapter(_Down())  # type: ignore[arg-type]
    try:
        with tenant_session(hvac.id) as s:
            run_turn(s, hvac, get_pack("hvac"), FakeLLM(script=[("On it.", [])]), conv_id)
        with tenant_session(hvac.id) as s:
            retry = s.scalar(
                select(Job).where(
                    Job.kind == "send_message",
                    Job.payload["conversation_id"].astext == str(conv_id),
                )
            )
            assert retry is not None, "a failed send is queued for retry, not dropped"
            retry_id = retry.id
        handlers = build_handlers(get_pack, FakeLLM())
        for attempt in range(3):
            with service_session() as s:
                s.execute(Job.__table__.update().where(Job.id == retry_id).values(state="running"))
            run_job(Picked(retry_id, hvac.id, "send_message", attempt), handlers)
    finally:
        register_adapter(real)
    with tenant_session(hvac.id) as s:
        job = s.get(Job, retry_id)
        conv = s.get(Conversation, conv_id)
        assert job is not None and job.state == "failed"
        assert conv is not None and conv.status == "waiting_human", "a person takes over"
