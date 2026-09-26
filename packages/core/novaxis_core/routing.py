"""Which tenant does an inbound message belong to?

This runs before we know the tenant, so it is the one read that must use a
service session. It reads only `tenants.slug` and `tenants.settings.channels`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.models import Tenant

# channel -> the key inside settings.channels[channel].config that identifies the tenant
_ROUTE_KEYS = {"twilio_sms": "number", "email": "inbound_address"}


def resolve_tenant(session: Session, channel: str, tenant_ref: str) -> Tenant | None:
    if channel == "webchat":
        return session.scalar(select(Tenant).where(Tenant.slug == tenant_ref))
    key = _ROUTE_KEYS.get(channel)
    if key is None:
        return None
    ref = tenant_ref.strip().lower()
    stmt = select(Tenant).where(
        Tenant.settings["channels"][channel]["config"][key].astext.ilike(ref)
    )
    return session.scalar(stmt)
