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
