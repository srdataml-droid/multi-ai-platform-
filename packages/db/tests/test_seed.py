from __future__ import annotations

from sqlalchemy import func, select

from novaxis_core.models import Tenant, User
from novaxis_core.tenant_settings import TenantSettings
from novaxis_db.seed import seed
from novaxis_db.session import service_session


def test_seed_is_idempotent_and_settings_validate(migrated: str) -> None:
    with service_session(migrated) as s:
        seed(s)
    with service_session(migrated) as s:
        seed(s)
        slugs = set(s.scalars(select(Tenant.slug)))
        assert {"demo-hvac", "demo-dental"} <= slugs
        assert s.scalar(select(func.count()).select_from(User).where(User.role == "owner")) == 2
        for t in s.scalars(select(Tenant).where(Tenant.slug.in_(["demo-hvac", "demo-dental"]))):
            TenantSettings.model_validate(t.settings)
