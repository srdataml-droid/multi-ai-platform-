"""The onboarding wizard's two calls: what to show, and save.

The wizard collects plain answers; `novaxis_core.onboarding.build_settings` turns them
into a validated `TenantSettings`. Calendar connection reuses /integrations/google.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.models import AuditLog, Location, Tenant
from novaxis_core.onboarding import Wizard, build_settings, defaults_for, wizard_from_settings
from novaxis_core.settings import get_settings
from novaxis_packs import get_pack

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
WRITERS = {"owner", "operator"}


def readable(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(x) for x in first["loc"])
    msg = str(first["msg"]).removeprefix("Value error, ")
    return f"{where}: {msg}" if where else msg


@router.get("")
def read(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    t = session.scalar(select(Tenant))
    assert t is not None
    pack = get_pack(t.pack_id)
    wizard = (
        wizard_from_settings(t.name, t.settings) if t.onboarded_at else defaults_for(pack, t.name)
    )
    return {
        "pack": {"id": pack.id, "name": pack.name, "channels": pack.manifest.get("channels")},
        "onboarded_at": t.onboarded_at.isoformat() if t.onboarded_at else None,
        "wizard": wizard,
        "google_calendar_available": bool(get_settings().google_client_id),
    }


@router.post("")
def save(body: dict[str, Any], principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    if principal.role not in WRITERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can set the business up")
    t = session.scalar(select(Tenant))
    assert t is not None
    try:
        wizard = Wizard.model_validate(body)
        built = build_settings(
            get_pack(t.pack_id),
            wizard,
            slug=t.slug,
            inbound_email_domain=get_settings().inbound_email_domain,
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, readable(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    # Keep what the wizard does not ask about (risk overrides, tone, pack settings).
    kept = {
        k: t.settings[k]
        for k in ("risk_overrides", "tone", "disclosure_text", "pack")
        if k in t.settings
    }
    t.settings = {**built.model_dump(), **kept}
    t.name = wizard.business_name
    # Slots are computed in the location's time zone; keep it in step with the answer.
    for loc in session.scalars(select(Location)):
        loc.timezone = wizard.timezone
    first = t.onboarded_at is None
    if first:
        t.onboarded_at = datetime.now(UTC)
    session.add(
        AuditLog(
            tenant_id=t.id,
            actor=f"user:{principal.user_id}",
            event="tenant.onboarded" if first else "onboarding.updated",
            subject_table="tenants",
            subject_id=t.id,
            diff={
                "services": len(wizard.services),
                "channels": [k for k, v in built.channels.items() if v.enabled],
            },
        )
    )
    session.flush()
    return read(principal, session)
