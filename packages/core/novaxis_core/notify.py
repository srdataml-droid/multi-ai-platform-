"""Tell staff something needs them. Email to owners and staff, plus the dashboard
badge that reads the same `awaiting` rows (Chunk 9). Runs as a job so a slow
mail provider never delays a customer reply."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.alerts import alert_staff
from novaxis_core.channels import get_adapter
from novaxis_core.models import ActionProposal, AuditLog, Job, Tenant, User
from novaxis_core.settings import get_settings

log = logging.getLogger("novaxis.notify")


def enqueue_staff_notification(session: Session, tenant: Tenant, proposal_id: uuid.UUID) -> Job:
    job = Job(tenant_id=tenant.id, kind="notify_staff", payload={"proposal_id": str(proposal_id)})
    session.add(job)
    session.flush()
    return job


def notify_staff(session: Session, tenant: Tenant, proposal_id: uuid.UUID) -> int:
    """Push to staff devices and email every owner and staff user. Returns how many alerts
    were attempted."""
    proposal = session.get(ActionProposal, proposal_id)
    if proposal is None or proposal.state != "awaiting":
        return 0
    pushed = alert_staff(
        session,
        tenant,
        "Approval needed",
        f"{proposal.kind.replace('_', ' ').capitalize()} is waiting for your decision.",
        "/approvals",
    )
    recipients = list(session.scalars(select(User).where(User.role.in_(["owner", "staff"]))))
    if not recipients:
        return pushed
    s = get_settings()
    cfg = ((tenant.settings.get("channels") or {}).get("email") or {}).get("config") or {}
    body = (
        f"A proposal is waiting for your decision.\n\n"
        f"Kind: {proposal.kind}\nReason: {proposal.reason}\n"
        f"Conversation: {proposal.conversation_id}\n\n"
        f"Open the dashboard to approve, edit or reject it."
    )
    if not s.postmark_server_token or not cfg.get("from_address"):
        log.info(
            "notify_staff: no email configured, would notify %d user(s) about %s",
            len(recipients),
            proposal_id,
        )
        session.add(
            AuditLog(
                tenant_id=tenant.id,
                actor="worker:notify",
                event="staff.notified",
                subject_table="action_proposals",
                subject_id=proposal_id,
                diff={
                    "recipients": len(recipients),
                    "delivered": False,
                    "why": "email not configured",
                },
            )
        )
        return pushed
    adapter = get_adapter("email")
    n = 0
    for u in recipients:
        adapter.send(
            to=u.email, body=body, tenant_channel_config={**cfg, "subject": "Approval needed"}
        )
        n += 1
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor="worker:notify",
            event="staff.notified",
            subject_table="action_proposals",
            subject_id=proposal_id,
            diff={"recipients": n, "delivered": True},
        )
    )
    return n + pushed
