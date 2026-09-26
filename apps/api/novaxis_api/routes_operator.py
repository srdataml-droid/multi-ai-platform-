"""The operator console: Novaxis staff see every tenant's health and usage, and can enter a
tenant to help. Entering is audited in the tenant's own log, so the business can see who
looked. The entry token lasts an hour and carries the operator role, never the owner's.

Cross-tenant reads use the service session; this router is one of the places ADR 0003
allows it, and every route here first checks the caller is an operator acting as
themselves.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select

from novaxis_api.auth import CurrentPrincipal, Principal
from novaxis_api.devtoken import mint
from novaxis_core.billing import HANDLERS, apply_event, demo_event, month_start, provider
from novaxis_core.models import AuditLog, Conversation, Integration, Job, Message, Tenant, User
from novaxis_db.session import service_session

router = APIRouter(prefix="/operator", tags=["operator"])
ENTRY_SECONDS = 3600


def _require_operator(principal: Principal) -> None:
    if principal.role != "operator" or principal.acting:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operators only")


@router.get("/tenants")
def list_tenants(principal: CurrentPrincipal) -> dict[str, Any]:
    _require_operator(principal)
    now = datetime.now(UTC)
    day_ago = now - timedelta(days=1)
    with service_session() as s:
        tenants = list(
            s.scalars(select(Tenant).where(Tenant.plan != "internal").order_by(Tenant.created_at))
        )
        ids = [t.id for t in tenants]

        def per_tenant(stmt: Any) -> dict[uuid.UUID, Any]:
            return {r[0]: r[1] for r in s.execute(stmt)}

        replies = per_tenant(
            select(Message.tenant_id, func.count())
            .where(
                Message.tenant_id.in_(ids),
                Message.author == "worker",
                Message.direction == "outbound",
                Message.created_at >= month_start(now),
            )
            .group_by(Message.tenant_id)
        )
        last_inbound = per_tenant(
            select(Message.tenant_id, func.max(Message.created_at))
            .where(Message.tenant_id.in_(ids), Message.direction == "inbound")
            .group_by(Message.tenant_id)
        )
        waiting = per_tenant(
            select(Conversation.tenant_id, func.count())
            .where(Conversation.tenant_id.in_(ids), Conversation.status == "waiting_human")
            .group_by(Conversation.tenant_id)
        )
        failed = per_tenant(
            select(Job.tenant_id, func.count())
            .where(Job.tenant_id.in_(ids), Job.state == "failed", Job.created_at >= day_ago)
            .group_by(Job.tenant_id)
        )
        stuck = per_tenant(
            select(Job.tenant_id, func.count())
            .where(
                Job.tenant_id.in_(ids),
                and_(Job.state == "queued", Job.run_after < now - timedelta(minutes=10)),
            )
            .group_by(Job.tenant_id)
        )
        bad_integrations = per_tenant(
            select(Integration.tenant_id, func.count())
            .where(Integration.tenant_id.in_(ids), Integration.health == "disconnected")
            .group_by(Integration.tenant_id)
        )
        items = []
        for t in tenants:
            problems = []
            if failed.get(t.id):
                problems.append(f"{failed[t.id]} failed jobs (24h)")
            if stuck.get(t.id):
                problems.append(f"{stuck[t.id]} jobs waiting over 10 min")
            if bad_integrations.get(t.id):
                problems.append("calendar integration disconnected")
            if t.status in ("paused", "closed"):
                problems.append(f"billing: {t.status}")
            if not t.worker_enabled:
                problems.append("worker switched off by owner")
            if t.onboarded_at is None:
                problems.append("onboarding not finished")
            items.append(
                {
                    "id": str(t.id),
                    "name": t.name,
                    "slug": t.slug,
                    "pack_id": t.pack_id,
                    "status": t.status,
                    "plan": t.plan,
                    "created_at": t.created_at.isoformat(),
                    "trial_ends_at": t.trial_ends_at.isoformat() if t.trial_ends_at else None,
                    "ai_replies_this_month": int(replies.get(t.id, 0)),
                    "waiting_human": int(waiting.get(t.id, 0)),
                    "last_inbound_at": last_inbound[t.id].isoformat()
                    if last_inbound.get(t.id)
                    else None,
                    "health": "ok" if not problems else "attention",
                    "problems": problems,
                }
            )
    return {"items": items, "billing_provider": provider()}


def _customer_tenant(s: Any, tenant_id: uuid.UUID) -> Tenant:
    t = s.get(Tenant, tenant_id)
    if t is None or t.plan == "internal":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such tenant")
    return t


@router.post("/tenants/{tenant_id}/enter")
def enter(tenant_id: uuid.UUID, principal: CurrentPrincipal) -> dict[str, Any]:
    _require_operator(principal)
    with service_session() as s:
        t = _customer_tenant(s, tenant_id)
        op = s.get(User, principal.user_id)
        assert op is not None
        s.add(
            AuditLog(
                tenant_id=t.id,
                actor=f"operator:{op.id}",
                event="operator.entered",
                subject_table="tenants",
                subject_id=t.id,
                diff={"operator_email": op.email, "expires_in_seconds": ENTRY_SECONDS},
            )
        )
        token = mint(op.auth_subject, ttl_seconds=ENTRY_SECONDS, act_tenant=str(t.id))
        return {"token": token, "tenant": {"id": str(t.id), "name": t.name, "slug": t.slug}}


class SimulateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: str


@router.post("/tenants/{tenant_id}/billing-event")
def simulate(tenant_id: uuid.UUID, body: SimulateIn, principal: CurrentPrincipal) -> dict[str, str]:
    """Demo provider only: show what a failed payment or a cancellation does."""
    _require_operator(principal)
    if provider() != "demo":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "only with the demo billing provider")
    if body.event not in HANDLERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown event")
    with service_session() as s:
        t = _customer_tenant(s, tenant_id)
        plan = t.plan if t.plan in ("pilot", "standard") else "standard"
        return {"outcome": apply_event(s, demo_event(t, body.event, plan), "demo")}
