"""Follow-ups that run later: chase an idle customer, close a stale conversation.

A workflow step is scheduled as a `workflow_step` job with `run_after`. When it
fires, the handler re-checks the conversation: if the customer has replied since,
or the status no longer matches, the step is a no-op. Messages go through the
gate as `reply` proposals, so consent and safeguarding rules apply to follow-ups
exactly as to live replies.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.models import AuditLog, Contact, Conversation, Job, Message, Tenant
from novaxis_core.packspec import PackSpec

_DURATION = re.compile(r"^(\d+)([mhd])$")


def parse_delay(text: str) -> timedelta:
    m = _DURATION.match(text)
    if not m:
        raise ValueError(f"bad delay {text!r}")
    n, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    return timedelta(days=n)


def schedule_idle_steps(
    session: Session, tenant: Tenant, pack: PackSpec, conv: Conversation
) -> list[Job]:
    """Called after every worker reply. Cancels earlier idle steps for this conversation
    and schedules the pack's idle steps fresh, keyed to the latest reply."""
    now = datetime.now(UTC)
    for old in session.scalars(
        select(Job).where(
            Job.kind == "workflow_step",
            Job.state == "queued",
            Job.payload["conversation_id"].astext == str(conv.id),
        )
    ):
        old.state = "done"
        old.last_error = "superseded by a newer reply"
    jobs: list[Job] = []
    for step in pack.workflows:
        if step.trigger != "conversation_idle":
            continue
        job = Job(
            tenant_id=tenant.id,
            kind="workflow_step",
            payload={
                "conversation_id": str(conv.id),
                "step_id": step.id,
                "anchor": now.isoformat(),
            },
            run_after=now + parse_delay(step.after),
        )
        session.add(job)
        jobs.append(job)
    session.flush()
    return jobs


def render(template: str, conv: Conversation, contact: Contact | None) -> str:
    values: dict[str, Any] = {k: str(v) for k, v in conv.extracted.items()}
    values.setdefault(
        "name", (contact.display_name if contact and contact.display_name else "there")
    )

    class _Safe(dict[str, str]):
        def __missing__(self, key: str) -> str:
            return ""

    return template.format_map(_Safe(values)).replace("  ", " ").strip()


def run_step(session: Session, tenant: Tenant, pack: PackSpec, job: Job) -> str:
    """Execute one fired step. Returns a short outcome word for the job log."""
    from novaxis_core.gate import GateContext
    from novaxis_core.turn import propose

    conv = session.get(Conversation, uuid.UUID(job.payload["conversation_id"]))
    step = next((s for s in pack.workflows if s.id == job.payload.get("step_id")), None)
    if conv is None or step is None:
        return "skipped:missing"
    if conv.status not in step.only_if_status:
        return f"skipped:status={conv.status}"
    anchor = datetime.fromisoformat(job.payload["anchor"])
    newer = session.scalar(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.created_at > anchor)
        .limit(1)
    )
    if newer is not None:
        return "skipped:activity"
    contact = session.get(Contact, conv.contact_id)
    if step.action == "close_conversation":
        conv.status = "closed"
        session.add(
            AuditLog(
                tenant_id=tenant.id,
                actor="worker:workflow",
                event="conversation.closed",
                subject_table="conversations",
                subject_id=conv.id,
                diff={"step": step.id},
            )
        )
        return "closed"
    ctx = GateContext(
        tenant_settings=tenant.settings,
        contact_consent=contact.consent if contact else {},
        conversation_channel=conv.channel,
        pack_rule=pack.rule,
    )
    text = render(step.template, conv, contact)
    p, d = propose(session, tenant, conv, "reply", {"text": text}, ctx, f"workflow:{step.id}")
    return f"{d.state}:{p.state}"
