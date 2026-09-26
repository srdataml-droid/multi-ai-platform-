"""Executors run only for cleared proposals, and every one leaves an audit row."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound, ProviderRef, register_adapter
from novaxis_core.channels.email_postmark import PostmarkEmailAdapter
from novaxis_core.channels.twilio_sms import TwilioSmsAdapter
from novaxis_core.executors import GateBypassError, execute
from novaxis_core.inbound import ingest
from novaxis_core.models import ActionProposal, AuditLog, Conversation, Message, Tenant
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session


class Fake:
    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.sent: list[tuple[str, str]] = []

    def verify_signature(self, request: Any) -> bool:
        return True

    def parse_inbound(self, request: Any) -> NormalisedInbound:
        raise NotImplementedError

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        self.sent.append((to, body))
        return ProviderRef(provider_ref=f"fake-{uuid.uuid4().hex[:6]}")


@pytest.fixture
def fakes():
    sms, email = Fake("twilio_sms"), Fake("email")
    register_adapter(sms)  # type: ignore[arg-type]
    register_adapter(email)  # type: ignore[arg-type]
    yield sms, email
    register_adapter(TwilioSmsAdapter())
    register_adapter(PostmarkEmailAdapter())


@pytest.fixture
def hvac(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        return t


def _conversation(tenant: Tenant) -> uuid.UUID:
    v = uuid.uuid4().hex[:10]
    with tenant_session(tenant.id) as s:
        return ingest(
            s,
            tenant,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref="demo-hvac",
                sender_visitor_id=v,
                body="hello",
            ),
        ).conversation_id


def _proposal(
    session, tenant: Tenant, conv_id: uuid.UUID, kind: str, params: dict[str, Any], state: str
) -> ActionProposal:  # type: ignore[no-untyped-def]
    p = ActionProposal(
        tenant_id=tenant.id,
        conversation_id=conv_id,
        kind=kind,
        params=params,
        risk="low",
        state=state,
    )
    session.add(p)
    session.flush()
    return p


def test_execute_refuses_awaiting_and_audits(hvac: Tenant) -> None:
    conv_id = _conversation(hvac)
    with tenant_session(hvac.id) as s:
        p = _proposal(s, hvac, conv_id, "reply", {"text": "hi"}, "awaiting")
        with pytest.raises(GateBypassError):
            execute(s, hvac, p)
        pid = p.id
    with tenant_session(hvac.id) as s:
        row = s.scalar(
            select(AuditLog).where(
                AuditLog.event == "proposal.execute_refused", AuditLog.subject_id == pid
            )
        )
        assert row is not None
        assert (
            s.scalar(
                select(Message).where(
                    Message.conversation_id == conv_id, Message.direction == "outbound"
                )
            )
            is None
        )


@pytest.mark.parametrize("state", ["proposed", "rejected", "executed", "failed"])
def test_execute_refuses_every_non_cleared_state(hvac: Tenant, state: str) -> None:
    conv_id = _conversation(hvac)
    with tenant_session(hvac.id) as s:
        p = _proposal(s, hvac, conv_id, "hand_to_human", {"reason": "x"}, state)
        with pytest.raises(GateBypassError):
            execute(s, hvac, p)


def test_every_executor_writes_an_audit_row(hvac: Tenant, fakes) -> None:  # type: ignore[no-untyped-def]
    conv_id = _conversation(hvac)
    cases = [
        ("reply", {"text": "Hello there"}),
        ("handoff_notice", {"text": "A person will be in touch."}),
        ("ask_intake_question", {"question_key": "name", "text": "Your name?"}),
        ("extract_fields", {"fields": {"name": "Al"}}),
        ("send_reminder", {"appointment_id": "a1", "text": "See you tomorrow"}),
        ("hand_to_human", {"reason": "asked"}),
        ("escalate_emergency", {"summary": "gas smell"}),
        ("verify_claim", {"text": "booked"}),
        (
            "propose_appointment",
            {"service_code": "repair_visit"},
        ),  # not implemented yet: fails, still audited
    ]
    for kind, params in cases:
        with tenant_session(hvac.id) as s:
            p = _proposal(s, hvac, conv_id, kind, params, "auto_approved")
            execute(s, hvac, p)
            pid, state = p.id, p.state
        with tenant_session(hvac.id) as s:
            events = {
                a.event for a in s.scalars(select(AuditLog).where(AuditLog.subject_id == pid))
            }
            assert events & {"proposal.executed", "proposal.failed"}, kind
            assert state in ("executed", "failed"), kind
            assert state == "executed", kind


def test_escalation_alerts_every_contact_channel(hvac: Tenant, fakes) -> None:  # type: ignore[no-untyped-def]
    sms, email = fakes
    conv_id = _conversation(hvac)
    with tenant_session(hvac.id) as s:
        p = _proposal(
            s, hvac, conv_id, "escalate_emergency", {"summary": "I smell gas"}, "auto_approved"
        )
        res = execute(s, hvac, p)
        assert res.ok and p.state == "executed"
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"
    assert sms.sent and sms.sent[0][0] == "+447700900000" and "EMERGENCY" in sms.sent[0][1]
    assert email.sent and email.sent[0][0] == "oncall@example.test"


def test_extract_merges_into_conversation(hvac: Tenant) -> None:
    conv_id = _conversation(hvac)
    with tenant_session(hvac.id) as s:
        execute(
            s,
            hvac,
            _proposal(
                s, hvac, conv_id, "extract_fields", {"fields": {"name": "Al"}}, "auto_approved"
            ),
        )
        execute(
            s,
            hvac,
            _proposal(
                s, hvac, conv_id, "extract_fields", {"fields": {"postcode": "SW1"}}, "auto_approved"
            ),
        )
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.extracted == {"name": "Al", "postcode": "SW1"}
