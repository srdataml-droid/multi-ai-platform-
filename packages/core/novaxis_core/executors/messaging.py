"""Executors that send something to the customer: reply, intake question, reminder."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from novaxis_core.executors import ExecResult, conversation_id_of, executor
from novaxis_core.models import ActionProposal, Conversation, Job, Message, Tenant
from novaxis_core.outbound import send_message


def _send_text(session: Session, tenant: Tenant, proposal: ActionProposal, text: str) -> ExecResult:
    conv = session.get(Conversation, conversation_id_of(proposal))
    if conv is None:
        return ExecResult(False, {}, "conversation not found")
    msg = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="outbound",
        channel=conv.channel,
        author="worker",
        body=text,
    )
    session.add(msg)
    session.flush()
    try:
        sent = send_message(session, tenant, msg.id)
    except PermissionError as exc:  # opted out: never retry
        return ExecResult(False, {"message_id": str(msg.id)}, str(exc))
    except Exception as exc:  # noqa: BLE001 - a provider hiccup must not silently drop a reply
        # The message row stays; a send job retries it with backoff, and after the last
        # attempt the job loop hands the conversation to a person (it carries the id).
        session.add(
            Job(
                tenant_id=tenant.id,
                kind="send_message",
                payload={"message_id": str(msg.id), "conversation_id": str(conv.id)},
            )
        )
        session.flush()
        return ExecResult(
            True,
            {"message_id": str(msg.id), "queued_retry": True, "error": type(exc).__name__},
        )
    return ExecResult(True, {"message_id": str(msg.id), "provider_ref": sent.provider_ref or ""})


@executor("reply")
def reply(session: Session, tenant: Tenant, proposal: ActionProposal, params: Any) -> ExecResult:
    return _send_text(session, tenant, proposal, params.text)


@executor("handoff_notice")
def handoff_notice(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    return _send_text(session, tenant, proposal, params.text)


@executor("ask_intake_question")
def ask_intake_question(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    res = _send_text(session, tenant, proposal, params.text)
    return ExecResult(res.ok, {**res.result, "question_key": params.question_key}, res.error)


@executor("send_reminder")
def send_reminder(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    res = _send_text(session, tenant, proposal, params.text)
    return ExecResult(res.ok, {**res.result, "appointment_id": params.appointment_id}, res.error)
