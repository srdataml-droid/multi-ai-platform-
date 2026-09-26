"""run_turn against real rows with a scripted model."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM, ToolCall
from novaxis_core.models import ActionProposal, Conversation, Message, Tenant, UsageEvent
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
        proposals = list(
            s.scalars(select(ActionProposal).where(ActionProposal.conversation_id == conv_id))
        )
        assert [p.kind for p in proposals] == ["propose_appointment"]
        assert proposals[0].risk == "low" and proposals[0].state == "proposed"
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
        kinds = [
            p.kind
            for p in s.scalars(
                select(ActionProposal).where(ActionProposal.conversation_id == conv_id)
            )
        ]
        assert kinds == ["escalate_emergency"]


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
