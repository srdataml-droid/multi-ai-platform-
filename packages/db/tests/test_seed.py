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
        assert {"demo-hvac", "demo-dental", "demo-restoration"} <= slugs
        demo = select(Tenant.id).where(Tenant.slug.like("demo-%"))
        for role in ("owner", "viewer"):
            n = s.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == role, User.tenant_id.in_(demo))
            )
            assert n == 3, role
        ops = s.scalar(select(User).where(User.email == "operator@novaxis.test"))
        assert ops is not None and ops.role == "operator"
        internal = s.get(Tenant, ops.tenant_id)
        assert internal is not None and internal.plan == "internal" and not internal.worker_enabled
        for t in s.scalars(
            select(Tenant).where(Tenant.slug.in_(["demo-hvac", "demo-dental", "demo-restoration"]))
        ):
            TenantSettings.model_validate(t.settings)
