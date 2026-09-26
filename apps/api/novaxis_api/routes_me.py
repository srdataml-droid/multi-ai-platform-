"""GET /me: who am I and which tenant am I in. The first authenticated route,
and the smoke test for the whole auth-to-tenant-session chain."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.models import Tenant
from novaxis_packs import get_pack

router = APIRouter()


@router.get("/me")
def me(principal: CurrentPrincipal, session: TenantDb) -> dict[str, object]:
    # Under RLS this can only ever return the caller's own tenant row.
    tenant = session.scalar(select(Tenant).where(Tenant.id == principal.tenant_id))
    return {
        "user_id": str(principal.user_id),
        "email": principal.email,
        "role": principal.role,
        "acting": principal.acting,
        "tenant": None
        if tenant is None
        else {
            "id": str(tenant.id),
            "slug": tenant.slug,
            "name": tenant.name,
            "pack_id": tenant.pack_id,
            "status": tenant.status,
            "plan": tenant.plan,
            "onboarded": tenant.onboarded_at is not None,
        },
    }


@router.get("/pack")
def pack(principal: CurrentPrincipal, session: TenantDb) -> dict[str, object]:
    """The tenant's pack as the dashboard needs it: labels, columns, intake keys."""
    tenant = session.scalar(select(Tenant).where(Tenant.id == principal.tenant_id))
    if tenant is None:
        return {}
    p = get_pack(tenant.pack_id)
    return {
        "id": p.id,
        "name": p.name,
        "vocabulary": p.vocabulary,
        "dashboard": p.dashboard.model_dump(),
        "intake": [q.model_dump() for q in p.intake],
        "workflows": [w.model_dump() for w in p.workflows],
    }
