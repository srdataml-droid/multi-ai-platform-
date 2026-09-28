"""Intake extraction: before each reply, a small JSON call records the facts the customer
just gave, so intake completes and the booking is proposed even when the reply model
never calls a tool (as seen live with an open model). Only answers the intake engine
would accept are recorded; a bad reply records nothing and the turn goes on."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.intake import parse_extraction
from novaxis_core.llm import FakeLLM
from novaxis_core.models import ActionProposal, Conversation, Tenant
from novaxis_core.sensitive import decrypt_fields
from novaxis_core.settings import get_settings
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

HVAC = get_pack("hvac")
EVERYTHING = {
    "name": "Sam",
    "problem_type": "noise",
    "symptom": "loud bang when the boiler fires up, since yesterday",
    "equipment_age": "about 10 years",
    "urgency": "no",
    "postcode": "SW1A 1AA",
    "phone": "07700 900123",
    "preferred_window": "tomorrow morning",
}


@pytest.fixture
def hvac(migrated: str, monkeypatch: pytest.MonkeyPatch) -> Tenant:
    monkeypatch.setenv("NOVAXIS_INTAKE_EXTRACTION", "true")
    get_settings.cache_clear()
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
    yield t
    get_settings.cache_clear()


def _customer_says(t: Tenant, text: str) -> uuid.UUID:
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


def test_only_answers_the_intake_engine_accepts_are_kept() -> None:
    reply = (
        'Sure! Here you go: {"name": "Sam", "problem_type": "NOISE", "urgency": "N", '
        '"postcode": "not a postcode", "favourite_colour": "blue", "phone": null, '
        '"equipment_age": ["x"]}'
    )
    assert parse_extraction(reply, HVAC.intake) == {
        "name": "Sam",
        "problem_type": "noise",
        "urgency": "no",
    }
    assert parse_extraction("I could not find anything.", HVAC.intake) == {}
    assert parse_extraction("{not json", HVAC.intake) == {}
    assert parse_extraction('{"problem_type": "exploded"}', HVAC.intake) == {}


def test_a_model_that_never_calls_tools_still_completes_intake_and_proposes_the_job(
    hvac: Tenant,
) -> None:
    conv_id = _customer_says(
        hvac,
        "I'm Sam. Loud bang every time the boiler fires up since yesterday, it's about 10 "
        "years old. Nobody vulnerable. SW1A 1AA, 07700 900123. Tomorrow morning suits me.",
    )
    llm = FakeLLM(
        script=[
            (json.dumps(EVERYTHING), []),  # the extraction call
            ("Thanks Sam, I've passed this to the team to confirm a time.", []),  # no tools
        ]
    )
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, HVAC, llm, conv_id)
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        got = decrypt_fields(conv.extracted, HVAC.sensitive_keys)
        assert {k: got.get(k) for k in EVERYTHING} == EVERYTHING
        kinds = {
            p.kind: p.state
            for p in s.scalars(
                select(ActionProposal).where(ActionProposal.conversation_id == conv_id)
            )
        }
    assert kinds["extract_fields"] == "executed"
    assert kinds["propose_appointment"] == "awaiting", "the booking reaches staff"
    assert llm.calls[0]["task"] == "classify" and not llm.calls[0]["tools"]
    assert "Intake is complete." in llm.calls[1]["system_volatile"], "the reply knows"


def test_a_bad_extraction_reply_records_nothing_and_the_turn_goes_on(hvac: Tenant) -> None:
    conv_id = _customer_says(hvac, "Hi, my boiler is banging")
    llm = FakeLLM(script=[("I am not sure what you mean.", []), ("What's your name?", [])])
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, HVAC, llm, conv_id)
        assert r.reply_message_id is not None
        assert not s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id,
                ActionProposal.kind == "extract_fields",
            )
        )


def test_off_unless_switched_on(hvac: Tenant, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVAXIS_INTAKE_EXTRACTION", "false")
    get_settings.cache_clear()
    conv_id = _customer_says(hvac, "Hi, my boiler is banging")
    llm = FakeLLM()
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, HVAC, llm, conv_id)
    assert [c["task"] for c in llm.calls] == ["worker_turn"]
