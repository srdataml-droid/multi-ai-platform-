"""Approval housekeeping that runs on the worker's timer."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.alerts import needs_a_person
from novaxis_core.models import ActionProposal, AuditLog, Conversation
from novaxis_core.settings import get_settings


def expire_stale_proposals(session: Session, now: datetime) -> int:
    """An approval nobody decided within `proposal_expiry_hours` expires. Its conversation
    goes to a person and the team is alerted, so the customer is not left waiting on a card
    nobody will open. Needs a service session (runs across tenants)."""
    cutoff = now - timedelta(hours=get_settings().proposal_expiry_hours)
    stale = list(
        session.scalars(
            select(ActionProposal)
            .where(ActionProposal.state == "awaiting", ActionProposal.created_at < cutoff)
            .limit(500)
        )
    )
    for p in stale:
        p.state = "expired"
        session.add(
            AuditLog(
                tenant_id=p.tenant_id,
                actor="worker:approvals",
                event="proposal.expired",
                subject_table="action_proposals",
                subject_id=p.id,
                diff={"kind": p.kind},
            )
        )
        conv = session.get(Conversation, p.conversation_id) if p.conversation_id else None
        if conv is not None and conv.status not in ("closed", "waiting_human"):
            conv.status = "waiting_human"
            needs_a_person(session, p.tenant_id, conv.id)
    session.flush()
    return len(stale)
