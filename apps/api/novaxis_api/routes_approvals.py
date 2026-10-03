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
from novaxis_core.agent_webhooks import enqueue as enqueue_agent_event
from novaxis_core.approval_model import model_for, shadow_report
from novaxis_core.booking_types import sensitive_keys_for
from novaxis_core.executors import execute
from novaxis_core.gate import GateContext, decide
from novaxis_core.models import ActionProposal, Approval, AuditLog, Contact, Conversation, Tenant
from novaxis_core.sensitive import reveal
from novaxis_core.turn import ground_params
from novaxis_packs import get_pack

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
        "prediction": p.prediction,
        "created_at": p.created_at.isoformat(),
        "executed_at": p.executed_at.isoformat() if p.executed_at else None,
    }


def _serialise_with_customer(
    session: TenantDb, principal: CurrentPrincipal, p: ActionProposal
) -> dict[str, Any]:
    """Approval cards need the customer context a dispatcher actually decides from.

    Keep the action proposal as the source of truth for what will execute, and attach a
    read-only snapshot of the conversation intake. Private booking answers follow the same
    role-based reveal rule as the conversation screen.
    """
    out = _serialise(p)
    conv = session.get(Conversation, p.conversation_id) if p.conversation_id else None
    if conv is None:
        out["customer"] = None
        return out
    contact = session.get(Contact, conv.contact_id)
    tenant = session.scalar(select(Tenant))
    pack = get_pack(tenant.pack_id if tenant else "generic")
    private = sensitive_keys_for(tenant, pack) if tenant else pack.sensitive_keys
    out["customer"] = {
        "name": contact.display_name if contact else None,
        "phone": contact.phones[0] if contact and contact.phones else None,
        "email": contact.emails[0] if contact and contact.emails else None,
        "channel": conv.channel,
        "status": conv.status,
        "summary": conv.summary,
        "intake": reveal(conv.extracted, private, principal.role),
    }
    return out


@router.get("")
def list_awaiting(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(ActionProposal)
            .where(ActionProposal.state == "awaiting")
            .order_by(ActionProposal.created_at.asc())
        )
    )
    return {
        "items": [_serialise_with_customer(session, principal, p) for p in rows],
        "count": len(rows),
    }


@router.get("/learning")
def learning(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    """What the approval model has learnt, and how its advice compares with the decisions
    staff actually made (the shadow report). Nothing is ever approved by the model."""
    tenant = session.scalar(select(Tenant))
    m = model_for(tenant.slug) if tenant else None
    return {
        "model": None
        if m is None
        else {
            "data": "synthetic" if m.synthetic else "real",
            "trained_at": m.spec.get("trained_at"),
            "rows": m.spec.get("rows"),
            "metrics": m.spec.get("metrics"),
            "precision_at": m.spec.get("precision_at"),
        },
        "shadow": shadow_report(session),
    }


@router.get("/{proposal_id}")
def get_one(
    proposal_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    p = session.get(ActionProposal, proposal_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such proposal")
    return _serialise_with_customer(session, principal, p)


def _context_for(session: TenantDb, p: ActionProposal) -> GateContext:
    tenant = session.scalar(select(Tenant))
    conv = session.get(Conversation, p.conversation_id) if p.conversation_id else None
    contact = session.get(Contact, conv.contact_id) if conv else None
    return GateContext(
        tenant_settings=tenant.settings if tenant else {},
        contact_consent=contact.consent if contact else {},
        conversation_channel=conv.channel if conv else "",
    )


def _after_failure(session: TenantDb, p: ActionProposal) -> None:
    """The person who approved is looking at it, so the conversation stays with them rather
    than going back to the worker, which would carry on as if it had worked."""
    if p.state != "failed" or p.conversation_id is None:
        return
    conv = session.get(Conversation, p.conversation_id)
    if conv is not None and conv.status != "closed":
        conv.status = "waiting_human"
    session.flush()


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
        _tell_agent(session, p)
        return _serialise(p)

    if body.decision == "approve":
        p.state = "approved"
        session.flush()
        execute(session, tenant, p)
        _after_failure(session, p)
        _tell_agent(session, p)
        return _serialise(p)

    # edit
    if body.params is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "edit requires params")
    conv = session.get(Conversation, p.conversation_id) if p.conversation_id else None
    params = ground_params(session, p.kind, body.params, conv)
    d = decide(p.kind, params, _context_for(session, p))
    new = ActionProposal(
        tenant_id=p.tenant_id,
        conversation_id=p.conversation_id,
        kind=p.kind,
        params=params,
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
        _after_failure(session, new)
    session.flush()
    _tell_agent(session, p, replaced_by=new)
    return {"replaced": _serialise(p), "proposal": _serialise(new)}


def _tell_agent(
    session: TenantDb, p: ActionProposal, replaced_by: ActionProposal | None = None
) -> None:
    """If the business's own agent proposed this, push the decision to it (ids only)."""
    if not (p.reason or "").startswith("agent:"):
        return
    data: dict[str, Any] = {
        "proposal_id": str(p.id),
        "kind": p.kind,
        "state": p.state,
        "about_conversation": str(p.conversation_id) if p.conversation_id else None,
    }
    if replaced_by is not None:
        data["replaced_by"] = {"proposal_id": str(replaced_by.id), "state": replaced_by.state}
    enqueue_agent_event(session, p.tenant_id, "proposal.decided", data)
