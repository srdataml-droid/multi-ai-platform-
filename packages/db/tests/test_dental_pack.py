"""Dental pack: evals, sensitive fields at rest, logs, role reveal, advice refusal."""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM, ToolCall
from novaxis_core.models import ActionProposal, Conversation, Message, Tenant
from novaxis_core.sensitive import is_encrypted, reveal
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))

SYMPTOM = "throbbing pain lower left molar"


@pytest.fixture
def dental(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t is not None
        s.expunge(t)
        return t


def _conv(tenant: Tenant, body: str) -> uuid.UUID:
    v = uuid.uuid4().hex[:10]
    with tenant_session(tenant.id) as s:
        return ingest(
            s,
            tenant,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref="demo-dental",
                sender_visitor_id=v,
                body=body,
            ),
        ).conversation_id


def test_dental_evals_all_pass_with_scripted_model(dental: Tenant) -> None:
    from run import run_pack

    outcomes = run_pack("dental", real=False)
    assert len(outcomes) == 5
    failed = {o.name: o.failures for o in outcomes if not o.passed}
    assert not failed, failed


def test_symptom_is_encrypted_at_rest_and_readable_by_staff(dental: Tenant) -> None:
    conv_id = _conv(dental, "toothache")
    fake = FakeLLM(
        script=[
            (
                "Sorry to hear that. Your name?",
                [
                    ToolCall(
                        "extract_fields",
                        {"fields": {"reason": "pain", "symptom": SYMPTOM, "pain_level": "7"}},
                        "t",
                    )
                ],
            )
        ]
    )
    with tenant_session(dental.id) as s:
        run_turn(s, dental, get_pack("dental"), fake, conv_id)
    with service_session() as s:
        raw = s.execute(
            text("select extracted::text from conversations where id = :id"), {"id": conv_id}
        ).scalar()
        assert (
            raw is not None
            and SYMPTOM not in raw
            and "enc:v1:" in raw
            and '"reason": "pain"' in raw
        )
    with tenant_session(dental.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        assert is_encrypted(conv.extracted["symptom"]) and is_encrypted(
            conv.extracted["pain_level"]
        )
        keys = get_pack("dental").sensitive_keys
        assert reveal(conv.extracted, keys, "staff")["symptom"] == SYMPTOM
        assert reveal(conv.extracted, keys, "viewer")["symptom"] == "[redacted]"


def test_symptom_text_never_reaches_logs(dental: Tenant, caplog: pytest.LogCaptureFixture) -> None:
    conv_id = _conv(dental, f"I have {SYMPTOM} since Monday")
    fake = FakeLLM(
        script=[
            (
                "Sorry to hear that. Your name?",
                [
                    ToolCall(
                        "extract_fields", {"fields": {"reason": "pain", "symptom": SYMPTOM}}, "t"
                    )
                ],
            )
        ]
    )
    with caplog.at_level(logging.DEBUG):
        with tenant_session(dental.id) as s:
            run_turn(s, dental, get_pack("dental"), fake, conv_id)
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert SYMPTOM not in joined and "molar" not in joined


def test_engine_still_validates_encrypted_answers(dental: Tenant) -> None:
    conv_id = _conv(dental, "pain")
    fake = FakeLLM(
        script=[
            (
                "ok",
                [
                    ToolCall(
                        "extract_fields",
                        {"fields": {"reason": "pain", "symptom": "x", "pain_level": "eleven"}},
                        "t",
                    )
                ],
            ),
            ("ok", []),
        ]
    )
    with tenant_session(dental.id) as s:
        run_turn(s, dental, get_pack("dental"), fake, conv_id)
    with tenant_session(dental.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        s.add(
            Message(
                tenant_id=dental.id,
                conversation_id=conv_id,
                direction="inbound",
                channel="webchat",
                author="customer",
                body="again",
            )
        )
        conv.status = "open"
    with tenant_session(dental.id) as s:
        run_turn(s, dental, get_pack("dental"), fake, conv_id)
    vol = fake.calls[1]["system_volatile"]
    assert "- pain_level: invalid, ask again" in vol, "the engine decrypted and re-validated"
    assert "- symptom: answered" in vol and "molar" not in vol


def test_advice_reply_is_refused_and_person_notified(dental: Tenant) -> None:
    conv_id = _conv(dental, "tooth hurts with cold drinks")
    fake = FakeLLM(
        script=[("Probably nothing serious, try rinsing with salt water and take ibuprofen.", [])]
    )
    with tenant_session(dental.id) as s:
        r = run_turn(s, dental, get_pack("dental"), fake, conv_id)
    assert r.decisions["reply"] == "rejected" and r.decisions["handoff_notice"] == "auto_approved"
    with tenant_session(dental.id) as s:
        bodies = [
            m.body
            for m in s.scalars(
                select(Message).where(
                    Message.conversation_id == conv_id, Message.direction == "outbound"
                )
            )
        ]
        assert (
            len(bodies) == 1
            and "ibuprofen" not in bodies[0]
            and "practice team will be in touch" in bodies[0]
        )
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"
        rejected = s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id, ActionProposal.kind == "reply"
            )
        )
        assert (
            rejected is not None
            and rejected.state == "rejected"
            and "pack rule" in (rejected.reason or "")
        )


def test_emergency_precheck_for_swelling_and_bleeding(dental: Tenant) -> None:
    pack = get_pack("dental")
    assert pack.emergency_check is not None
    assert pack.emergency_check("my cheek is swollen and I can barely swallow")
    assert pack.emergency_check("bleeding after extraction won't stop, been hours")
    assert pack.emergency_check("fell off my bike and knocked a tooth out")
    assert not pack.emergency_check("gum is a bit swollen around one tooth")
    assert not pack.emergency_check("a little bleeding when I brush")
