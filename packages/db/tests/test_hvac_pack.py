"""HVAC pack through the real ingest and turn code."""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM, ToolCall
from novaxis_core.models import ActionProposal, Conversation, Job, Message, Tenant
from novaxis_core.turn import run_turn
from novaxis_core.workflows import parse_delay, run_step
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

EVALS = Path(__file__).resolve().parents[3] / "evals"
sys.path.insert(0, str(EVALS))


@pytest.fixture
def hvac(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        return t


def _conv(tenant: Tenant, body: str) -> tuple[uuid.UUID, str]:
    v = uuid.uuid4().hex[:10]
    with tenant_session(tenant.id) as s:
        r = ingest(
            s,
            tenant,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref="demo-hvac",
                sender_visitor_id=v,
                body=body,
            ),
        )
        return r.conversation_id, v


def test_hvac_evals_all_pass_with_scripted_model(hvac: Tenant) -> None:
    from run import run_pack  # evals/run.py

    outcomes = run_pack("hvac", real=False)
    assert len(outcomes) == 5
    failed = {o.name: o.failures for o in outcomes if not o.passed}
    assert not failed, failed


def test_emergency_precheck_runs_before_any_llm_call(hvac: Tenant) -> None:
    conv_id, _ = _conv(hvac, "Think there's a gas smell coming from the kitchen")
    fake = FakeLLM()
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    assert r.emergency and fake.calls == []


def test_pack_rule_emergency_no_heat_plus_vulnerable(hvac: Tenant) -> None:
    conv_id, _ = _conv(hvac, "heating has stopped and we have a newborn at home")
    fake = FakeLLM()
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    assert r.emergency and fake.calls == []
    conv_id2, _ = _conv(hvac, "heating has stopped, can someone come this week")
    with tenant_session(hvac.id) as s:
        r2 = run_turn(s, hvac, get_pack("hvac"), fake, conv_id2)
    assert not r2.emergency and len(fake.calls) == 1


def test_out_of_area_declines_and_hands_off(hvac: Tenant) -> None:
    conv_id, _ = _conv(hvac, "no hot water, I'm in M1 1AE")
    fake = FakeLLM(
        script=[
            (
                "Sorry to hear that. What's your name?",
                [
                    ToolCall(
                        "extract_fields",
                        {"fields": {"postcode": "M1 1AE", "problem_type": "no hot water"}},
                        "t",
                    )
                ],
            )
        ]
    )
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    assert r.decisions.get("hand_to_human") == "auto_approved"
    with tenant_session(hvac.id) as s:
        reply = s.get(Message, r.reply_message_id)
        assert reply is not None and "outside the area we cover" in reply.body
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"


def test_intake_prompt_block_reaches_the_model(hvac: Tenant) -> None:
    conv_id, _ = _conv(hvac, "hello")
    fake = FakeLLM()
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    vol = fake.calls[0]["system_volatile"]
    assert (
        "Intake keys" in vol
        and "- name: missing" in vol
        and "Ask next, in your own words: What's your name?" in vol
    )
    assert fake.calls[0]["system_stable"].startswith(
        "You are the front-desk assistant for a heating"
    )


def test_idle_workflow_steps_are_scheduled_and_superseded(hvac: Tenant) -> None:
    conv_id, v = _conv(hvac, "no heating")
    fake = FakeLLM(script=[("What's your name?", []), ("Thanks. Which is closest?", [])])
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        steps = list(
            s.scalars(
                select(Job).where(
                    Job.kind == "workflow_step",
                    Job.state == "queued",
                    Job.payload["conversation_id"].astext == str(conv_id),
                )
            )
        )
        assert {j.payload["step_id"] for j in steps} == {"chase_24h", "chase_72h", "close_7d"}
        now = datetime.now(UTC)
        by = {j.payload["step_id"]: j.run_after for j in steps}
        # 24 hours on, or the next 08:00 if that lands in quiet hours (at most 12 h later).
        assert timedelta(hours=23) < by["chase_24h"] - now < timedelta(hours=25 + 12)
        from zoneinfo import ZoneInfo

        from novaxis_core.quiet_hours import is_quiet

        assert not is_quiet(by["chase_24h"], ZoneInfo("Europe/London"))
        assert timedelta(days=6) < by["close_7d"] - now < timedelta(days=8)
    # Customer replies, worker replies again: old steps superseded, new ones queued.
    with tenant_session(hvac.id) as s:
        ingest(
            s,
            hvac,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref="demo-hvac",
                sender_visitor_id=v,
                body="Priya",
            ),
        )
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        queued = list(
            s.scalars(
                select(Job).where(
                    Job.kind == "workflow_step",
                    Job.state == "queued",
                    Job.payload["conversation_id"].astext == str(conv_id),
                )
            )
        )
        done = list(
            s.scalars(
                select(Job).where(
                    Job.kind == "workflow_step",
                    Job.state == "done",
                    Job.payload["conversation_id"].astext == str(conv_id),
                )
            )
        )
        assert len(queued) == 3 and len(done) == 3


def test_workflow_step_sends_only_if_still_idle(hvac: Tenant) -> None:
    conv_id, v = _conv(hvac, "no heating")
    fake = FakeLLM(
        script=[
            (
                "What's your name?",
                [
                    ToolCall(
                        "extract_fields",
                        {"fields": {"name": "Priya", "problem_type": "no heating"}},
                        "t",
                    )
                ],
            )
        ]
    )
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        job = s.scalar(
            select(Job).where(
                Job.kind == "workflow_step",
                Job.state == "queued",
                Job.payload["step_id"].astext == "chase_24h",
                Job.payload["conversation_id"].astext == str(conv_id),
            )
        )
        assert job is not None
        outcome = run_step(s, hvac, get_pack("hvac"), job)
        assert outcome == "auto_approved:executed"
        bodies = [
            m.body
            for m in s.scalars(
                select(Message)
                .where(Message.conversation_id == conv_id, Message.direction == "outbound")
                .order_by(Message.created_at)
            )
        ]
        assert bodies[-1].startswith(
            "Hi Priya, just checking whether you'd still like us to come out for the no heating"
        )
    # A second fire of the same step is a no-op because there is newer activity (the chase itself).
    with tenant_session(hvac.id) as s:
        job = s.scalar(
            select(Job).where(
                Job.kind == "workflow_step",
                Job.payload["step_id"].astext == "chase_72h",
                Job.payload["conversation_id"].astext == str(conv_id),
            )
        )
        assert job is not None
        assert run_step(s, hvac, get_pack("hvac"), job) == "skipped:activity"


def test_parse_delay() -> None:
    assert parse_delay("30m") == timedelta(minutes=30)
    assert parse_delay("24h") == timedelta(hours=24)
    assert parse_delay("7d") == timedelta(days=7)
    with pytest.raises(ValueError):
        parse_delay("soon")


def test_pack_rule_raises_vulnerable_job_to_medium(hvac: Tenant) -> None:
    conv_id, _ = _conv(hvac, "hi")
    fake = FakeLLM(
        script=[
            (
                "Passed to the team.",
                [
                    ToolCall(
                        "propose_appointment",
                        {
                            "service_code": "repair_visit",
                            "preferred_window": "asap",
                            "notes": "vulnerable occupant, urgent",
                        },
                        "t",
                    )
                ],
            )
        ]
    )
    with tenant_session(hvac.id) as s:
        r = run_turn(s, hvac, get_pack("hvac"), fake, conv_id)
    with tenant_session(hvac.id) as s:
        p = s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id,
                ActionProposal.kind == "propose_appointment",
            )
        )
        assert p is not None and p.risk == "medium" and "pack rule" in (p.reason or "")
    assert r.decisions["propose_appointment"] == "awaiting"
