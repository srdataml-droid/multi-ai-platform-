"""The booking bridge from the dashboard: connect it, upload the vendor's diary export,
and tick off hand-offs once they are keyed into the vendor tool. See novaxis_core.bridge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_api.routes_onboarding import readable
from novaxis_core.bridge import (
    PROVIDER,
    BridgeConfig,
    bridge_health,
    bridge_integration,
    import_export,
    mark_entered,
)
from novaxis_core.models import AuditLog, BridgeTicket, Integration, Tenant

router = APIRouter(prefix="/integrations/bridge", tags=["integrations"])
OWNERS = {"owner", "operator"}
OFFICE = {"owner", "staff", "operator"}
MAX_EXPORT_CHARS = 2_000_000


def _need(principal: CurrentPrincipal, roles: set[str]) -> None:
    if principal.role not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed for your role")


def _ticket(t: BridgeTicket) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "ref": t.ref,
        "action": t.action,
        "starts_at": t.starts_at.isoformat(),
        "ends_at": t.ends_at.isoformat(),
        "summary": t.summary,
        "status": t.status,
        "service_name": t.details.get("service_name", ""),
        "customer_name": t.details.get("customer_name", ""),
        "customer_phone": t.details.get("customer_phone", ""),
        "created_at": t.created_at.isoformat(),
        "entered_at": t.entered_at.isoformat() if t.entered_at else None,
    }


@router.get("")
def read(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    integ = bridge_integration(session)
    tenant = session.scalar(select(Tenant))
    assert tenant is not None
    services = [
        {"code": s["code"], "name": s["name"]} for s in tenant.settings.get("services") or []
    ]
    tickets = list(
        session.scalars(select(BridgeTicket).order_by(BridgeTicket.created_at.desc()).limit(50))
    )
    if integ is None:
        return {"connected": False, "services": services, "tickets": [_ticket(t) for t in tickets]}
    health = bridge_health(integ)
    now = datetime.now(UTC)
    upcoming = sum(1 for b in integ.config.get("busy") or [] if b["e"] > now.isoformat())
    return {
        "connected": True,
        "settings": integ.config.get("settings"),
        "health": {"ok": health.ok, "detail": health.detail},
        "last_import_at": integ.config.get("last_import_at"),
        "last_import_report": integ.config.get("last_import_report"),
        "vendor_busy_upcoming": upcoming,
        "services": services,
        "tickets": [_ticket(t) for t in tickets],
    }


@router.put("")
def connect(body: dict[str, Any], principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    _need(principal, OWNERS)
    try:
        cfg = BridgeConfig.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, readable(exc)) from exc
    integ = session.scalar(select(Integration).where(Integration.provider == PROVIDER))
    if integ is None:
        integ = Integration(tenant_id=principal.tenant_id, provider=PROVIDER, config={})
        session.add(integ)
    integ.config = {**(integ.config or {}), "settings": cfg.model_dump()}
    if integ.health in ("disconnected", "unknown", None):
        integ.health = "connected"
    session.flush()
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="bridge.configured",
            subject_table="integrations",
            subject_id=integ.id,
            diff={"vendor_name": cfg.vendor_name, "email_set": cfg.email_to is not None},
        )
    )
    session.flush()
    return read(principal, session)


@router.delete("")
def disconnect(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    _need(principal, OWNERS)
    integ = bridge_integration(session)
    if integ is not None:
        integ.health = "disconnected"
        session.add(
            AuditLog(
                tenant_id=principal.tenant_id,
                actor=f"user:{principal.user_id}",
                event="bridge.disconnected",
                subject_table="integrations",
                subject_id=integ.id,
                diff={},
            )
        )
        session.flush()
    return read(principal, session)


class ExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv: str = Field(max_length=MAX_EXPORT_CHARS)


@router.post("/import")
def upload(body: ExportIn, principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    _need(principal, OFFICE)
    integ = bridge_integration(session)
    tenant = session.scalar(select(Tenant))
    if integ is None or tenant is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "connect your booking software first")
    report = import_export(session, tenant, integ, body.csv)
    if report.imported == 0 and report.errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(report.errors))
    return {
        "rows": report.rows,
        "imported": report.imported,
        "skipped": report.skipped,
        "errors": report.errors,
        "conflicts": report.conflicts,
    }


@router.post("/tickets/{ticket_id}/entered")
def entered(ticket_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    _need(principal, OFFICE)
    ticket = session.get(BridgeTicket, ticket_id)
    tenant = session.scalar(select(Tenant))
    if ticket is None or tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such hand-off")
    return _ticket(mark_entered(session, tenant, ticket, principal.user_id))
