"""The approval queue. Staff see what is waiting, and decide.

approve  -> approvals row, state approved, executed now.
reject   -> approvals row, state rejected.
edit     -> approvals row on the old proposal (decision edit), old proposal rejected and
            linked via superseded_by; a new proposal with the replacement params runs
            through the gate again. If the gate says medium, the human's edit counts as
            the approval and it executes; if the gate says high, it stays rejected.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.executors import execute
from novaxis_core.gate import GateContext, decide
from novaxis_core.models import ActionProposal, Approval, AuditLog, Contact, Conversation, Tenant

router = APIRouter(prefix="/approvals", tags=["approvals"])

DECIDER_ROLES = {"owner", "staff", "operator"}


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject", "edit"]
    note: str | None = Field(default=None, max_length=2000)
    params: dict[str, Any] | None = None


def _serialise(p: ActionProposal) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "conversation_id": str(p.conversation_id) if p.conversation_id else None,
        "kind": p.kind,
        "params": p.params,
        "risk": p.risk,
        "reason": p.reason,
        "state": p.state,
        "error": p.error,
        "result": p.result,
        "superseded_by": str(p.superseded_by) if p.superseded_by else None,
        "created_at": p.created_at.isoformat(),
        "executed_at": p.executed_at.isoformat() if p.executed_at else None,
    }


@router.get("")
def list_awaiting(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(ActionProposal)
            .where(ActionProposal.state == "awaiting")
            .order_by(ActionProposal.created_at.asc())
        )
    )
    return {"items": [_serialise(p) for p in rows], "count": len(rows)}


@router.get("/{proposal_id}")
def get_one(
    proposal_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    p = session.get(ActionProposal, proposal_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such proposal")
    return _serialise(p)


def _context_for(session: TenantDb, p: ActionProposal) -> GateContext:
    tenant = session.scalar(select(Tenant))
    conv = session.get(Conversation, p.conversation_id) if p.conversation_id else None
    contact = session.get(Contact, conv.contact_id) if conv else None
    return GateContext(
        tenant_settings=tenant.settings if tenant else {},
        contact_consent=contact.consent if contact else {},
        conversation_channel=conv.channel if conv else "",
    )


@router.post("/{proposal_id}")
def decide_one(
    proposal_id: uuid.UUID, body: DecisionIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    if principal.role not in DECIDER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "viewers cannot decide proposals")
    p = session.get(ActionProposal, proposal_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such proposal")
    if p.state != "awaiting":
        raise HTTPException(status.HTTP_409_CONFLICT, f"proposal is {p.state}, not awaiting")
    tenant = session.scalar(select(Tenant))
    assert tenant is not None

    session.add(
        Approval(
            tenant_id=p.tenant_id,
            proposal_id=p.id,
            decided_by=principal.user_id,
            decision=body.decision,
            note=body.note,
        )
    )
    session.add(
        AuditLog(
            tenant_id=p.tenant_id,
            actor=f"user:{principal.user_id}",
            event=f"proposal.{body.decision}",
            subject_table="action_proposals",
            subject_id=p.id,
            diff={"kind": p.kind, "note": body.note or ""},
        )
    )

    if body.decision == "reject":
        p.state = "rejected"
        session.flush()
        return _serialise(p)

    if body.decision == "approve":
        p.state = "approved"
        session.flush()
        execute(session, tenant, p)
        return _serialise(p)

    # edit
    if body.params is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "edit requires params")
    d = decide(p.kind, body.params, _context_for(session, p))
    new = ActionProposal(
        tenant_id=p.tenant_id,
        conversation_id=p.conversation_id,
        kind=p.kind,
        params=body.params,
        risk=d.risk,
        reason=f"edited by staff: {d.reason}",
        state="rejected" if d.state == "rejected" else "approved",
    )
    session.add(new)
    session.flush()
    p.state = "rejected"
    p.superseded_by = new.id
    if new.state == "approved":
        execute(session, tenant, new)
    session.flush()
    return {"replaced": _serialise(p), "proposal": _serialise(new)}
