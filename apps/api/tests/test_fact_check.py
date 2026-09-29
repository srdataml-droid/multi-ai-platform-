"""No invented facts: a reply's statements about the business are checked against what the
business has given (settings and its own question-and-answer list) before it is sent.

Live, before this: asked "Are your engineers Gas Safe registered?", gpt-oss answered "Yes,
all of our engineers are Gas Safe registered", and asked about past jobs, "We've done plenty
of work in the SW1 area". Neither was anything the business had said."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM
from novaxis_core.models import ActionProposal, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

HVAC = get_pack("hvac")
INVENTED = "Yes, all of our engineers are Gas Safe registered. Could I have your name?"


@pytest.fixture
def hvac(migrated: str, monkeypatch: pytest.MonkeyPatch) -> Tenant:
    monkeypatch.setenv("NOVAXIS_REPLY_FACT_CHECK", "true")
    get_settings.cache_clear()
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
    yield t
    get_settings.cache_clear()


def _ask(t: Tenant, text: str) -> uuid.UUID:
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        return ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref=t.slug,
                sender_visitor_id=v,
                body=text,
            ),
        ).conversation_id


def _sent(t: Tenant, conv_id: uuid.UUID) -> str:
    with tenant_session(t.id) as s:
        m = s.scalar(
            select(Message)
            .where(Message.conversation_id == conv_id, Message.direction == "outbound")
            .order_by(Message.created_at.desc())
        )
        assert m is not None
        return m.body


def _staff_items(t: Tenant, conv_id: uuid.UUID) -> list[ActionProposal]:
    with tenant_session(t.id) as s:
        rows = list(
            s.scalars(
                select(ActionProposal).where(
                    ActionProposal.conversation_id == conv_id,
                    ActionProposal.kind == "verify_claim",
                )
            )
        )
        for r in rows:
            s.expunge(r)
        return rows


def test_an_invented_fact_is_held_back_and_the_question_goes_to_staff(hvac: Tenant) -> None:
    conv_id = _ask(hvac, "Are your engineers Gas Safe registered?")
    llm = FakeLLM(
        script=[
            (INVENTED, []),
            (
                json.dumps(
                    {
                        "statements": [
                            {"text": "All engineers are Gas Safe registered", "supported": False}
                        ]
                    }
                ),
                [],
            ),
        ]
    )
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, HVAC, llm, conv_id)
    sent = _sent(hvac, conv_id)
    assert "Gas Safe" not in sent, "the invented fact never reaches the customer"
    assert HVAC.unconfirmed_reply in sent
    assert sent.rstrip().endswith("?"), "intake carries on with the next question"
    held = _staff_items(hvac, conv_id)
    assert len(held) == 1 and held[0].state == "awaiting"
    assert "Gas Safe" in held[0].params["text"], "staff see the question and what was held"
    check = llm.calls[1]
    assert check["task"] == "classify" and "Business facts:" in check["system_volatile"]
    assert "Gas Safe registered?" in check["messages"][0]["content"]


def test_a_fact_the_business_gave_is_sent(hvac: Tenant) -> None:
    faq = {"question": "Gas Safe registered?", "answer": "Yes, registration number 123456."}
    with service_session() as s:
        row = s.get(Tenant, hvac.id)
        assert row is not None
        row.settings = {**row.settings, "faqs": [faq]}
    hvac.settings = {**hvac.settings, "faqs": [faq]}
    conv_id = _ask(hvac, "Are your engineers Gas Safe registered?")
    reply = "Yes, we're Gas Safe registered, number 123456. Could I have your name?"
    verdict = {"statements": [{"text": "Gas Safe registered, number 123456", "supported": True}]}
    llm = FakeLLM(script=[(reply, []), (json.dumps(verdict), [])])
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, HVAC, llm, conv_id)
    assert _sent(hvac, conv_id).endswith(reply)
    assert not _staff_items(hvac, conv_id)
    assert "A: Yes, registration number 123456." in llm.calls[0]["system_volatile"]
    assert "A: Yes, registration number 123456." in llm.calls[1]["system_volatile"]
    with service_session() as s:
        row = s.get(Tenant, hvac.id)
        assert row is not None
        row.settings = {k: v for k, v in row.settings.items() if k != "faqs"}


def test_a_check_that_cannot_run_lets_the_reply_through(hvac: Tenant) -> None:
    """A broken check must not silence the assistant: the reply goes as written, logged."""
    conv_id = _ask(hvac, "Hi, my radiator is cold")
    llm = FakeLLM(script=[("Sorry to hear that. Could I have your name?", []), ("no idea", [])])
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, HVAC, llm, conv_id)
    assert _sent(hvac, conv_id).endswith("Could I have your name?")


def test_off_unless_switched_on(hvac: Tenant, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVAXIS_REPLY_FACT_CHECK", "false")
    get_settings.cache_clear()
    conv_id = _ask(hvac, "Hello")
    llm = FakeLLM(script=[("Hi! What's your name?", [])])
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, HVAC, llm, conv_id)
    assert [c["task"] for c in llm.calls] == ["worker_turn"]


def test_anything_not_marked_supported_is_held_back(hvac: Tenant) -> None:
    """Only an explicit true passes: "supported": "maybe" or a missing flag holds it back."""
    conv_id = _ask(hvac, "Have you done jobs on my street before? I am in SW1A.")
    verdict = {
        "statements": [
            {"text": "We cover SW1", "supported": True},
            {"text": "We have helped homes in SW1", "supported": "maybe"},
        ]
    }
    llm = FakeLLM(
        script=[
            ("We cover SW1 and have helped homes there. Your name?", []),
            (json.dumps(verdict), []),
        ]
    )
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, HVAC, llm, conv_id)
    assert "helped" not in _sent(hvac, conv_id)
    held = _staff_items(hvac, conv_id)
    assert len(held) == 1 and "We have helped homes in SW1" in held[0].params["text"]
    assert "We cover SW1" not in held[0].params["text"].split("Draft reply")[0]
