"""GET /me: who am I and which tenant am I in. The first authenticated route,
and the smoke test for the whole auth-to-tenant-session chain."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.models import Tenant

router = APIRouter()


@router.get("/me")
def me(principal: CurrentPrincipal, session: TenantDb) -> dict[str, object]:
    # Under RLS this can only ever return the caller's own tenant row.
    tenant = session.scalar(select(Tenant).where(Tenant.id == principal.tenant_id))
    return {
        "user_id": str(principal.user_id),
        "email": principal.email,
        "role": principal.role,
        "tenant": None
        if tenant is None
        else {"id": str(tenant.id), "slug": tenant.slug, "pack_id": tenant.pack_id},
    }
