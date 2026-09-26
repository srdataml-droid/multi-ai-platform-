"""Connect a system of record. Google Calendar first: the owner clicks connect, grants
access, and the callback stores encrypted tokens on the tenant's integrations row."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.credentials import seal
from novaxis_core.models import AuditLog, Integration, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.sor import system_of_record
from novaxis_core.sor.google_calendar import auth_url, exchange_code
from novaxis_db.session import service_session, tenant_session

router = APIRouter(prefix="/integrations", tags=["integrations"])
DECIDER_ROLES = {"owner", "operator"}


def _sign_state(tenant_id: uuid.UUID) -> str:
    sig = hmac.new(
        get_settings().jwt_secret.encode(), str(tenant_id).encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"{tenant_id}.{sig}"


def _verify_state(state: str) -> uuid.UUID | None:
    if "." not in state:
        return None
    raw, sig = state.rsplit(".", 1)
    expected = hmac.new(
        get_settings().jwt_secret.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


@router.get("")
def list_integrations(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    rows = list(session.scalars(select(Integration).order_by(Integration.created_at)))
    tenant = session.scalar(select(Tenant))
    sor = system_of_record(session, tenant) if tenant else None
    return {
        "items": [
            {
                "id": str(r.id),
                "provider": r.provider,
                "health": r.health,
                "config": r.config,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "system_of_record": sor.provider if sor else None,
    }


@router.get("/google/connect")
def google_connect(principal: CurrentPrincipal) -> dict[str, str]:
    if principal.role not in DECIDER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can connect a calendar")
    if not get_settings().google_client_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Google OAuth is not configured on this deployment"
        )
    return {"url": auth_url(_sign_state(principal.tenant_id))}


@router.get("/google/callback")
def google_callback(code: str, state: str, transport: Any = None) -> RedirectResponse:
    tenant_id = _verify_state(state)
    if tenant_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad state")
    try:
        tokens = exchange_code(code, transport=_callback_transport)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"token exchange failed: {type(exc).__name__}"
        ) from exc
    with tenant_session(tenant_id) as s:
        integ = s.scalar(select(Integration).where(Integration.provider == "google_calendar"))
        if integ is None:
            integ = Integration(tenant_id=tenant_id, provider="google_calendar")
            s.add(integ)
        integ.encrypted_credentials = seal(tokens)
        integ.health = "connected"
        integ.config = {"scope": tokens.get("scope", "")}
        s.flush()
        s.add(
            AuditLog(
                tenant_id=tenant_id,
                actor="user:oauth",
                event="integration.connected",
                subject_table="integrations",
                subject_id=integ.id,
                diff={"provider": "google_calendar"},
            )
        )
    return RedirectResponse(url="/settings/integrations?connected=google_calendar", status_code=302)


@router.post("/{integration_id}/disconnect")
def disconnect(
    integration_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    if principal.role not in DECIDER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can disconnect")
    integ = session.get(Integration, integration_id)
    if integ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such integration")
    integ.health = "disconnected"
    integ.encrypted_credentials = None
    session.add(
        AuditLog(
            tenant_id=integ.tenant_id,
            actor=f"user:{principal.user_id}",
            event="integration.disconnected",
            subject_table="integrations",
            subject_id=integ.id,
            diff={"provider": integ.provider},
        )
    )
    return {"id": str(integ.id), "health": integ.health}


# Tests inject a mock transport for the OAuth token exchange.
_callback_transport: httpx.BaseTransport | None = None


def set_callback_transport(t: httpx.BaseTransport | None) -> None:
    global _callback_transport
    _callback_transport = t


def _unused(s: Any = service_session) -> None:  # keep import for type checkers
    return None
