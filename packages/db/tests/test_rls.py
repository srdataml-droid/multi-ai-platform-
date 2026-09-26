"""The tenancy boundary, proven at the database."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import ProgrammingError

from novaxis_core.models import TENANT_TABLES, Contact, Tenant
from novaxis_db.session import service_session, tenant_session


def test_tenant_b_cannot_read_tenant_a_rows(two_tenants: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, b = two_tenants
    with tenant_session(a) as s:
        s.add(Contact(tenant_id=a, display_name="Alice"))
    with tenant_session(a) as s:
        assert [c.display_name for c in s.scalars(select(Contact))] == ["Alice"]
    with tenant_session(b) as s:
        assert list(s.scalars(select(Contact))) == []


def test_tenant_b_cannot_update_tenant_a_rows(two_tenants: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, b = two_tenants
    with tenant_session(a) as s:
        c = Contact(tenant_id=a, display_name="Alice")
        s.add(c)
        s.flush()
        cid = c.id
    with tenant_session(b) as s:
        result = s.execute(update(Contact).where(Contact.id == cid).values(display_name="Mallory"))
        assert result.rowcount == 0
    with tenant_session(a) as s:
        assert s.get(Contact, cid).display_name == "Alice"  # type: ignore[union-attr]


def test_tenant_b_cannot_insert_rows_for_tenant_a(
    two_tenants: tuple[uuid.UUID, uuid.UUID],
) -> None:
    a, b = two_tenants
    with pytest.raises(ProgrammingError, match="row-level security"):
        with tenant_session(b) as s:
            s.add(Contact(tenant_id=a, display_name="Forged"))
            s.flush()


def test_tenant_sees_only_its_own_tenant_row(two_tenants: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, b = two_tenants
    with tenant_session(a) as s:
        rows = list(s.scalars(select(Tenant)))
        assert [t.id for t in rows] == [a]


def test_no_tenant_set_sees_nothing(two_tenants: tuple[uuid.UUID, uuid.UUID]) -> None:
    """The app role with no app.tenant_id set must see zero rows, not all rows."""
    a, _ = two_tenants
    with tenant_session(a) as s:
        s.add(Contact(tenant_id=a, display_name="Alice"))
    with service_session() as s:
        s.execute(text('SET LOCAL ROLE "novaxis_app"'))
        assert s.execute(text("select count(*) from contacts")).scalar() == 0


def test_every_tenant_table_has_forced_rls_and_a_policy(migrated: str) -> None:
    with service_session(migrated) as s:
        rows = s.execute(
            text(
                """
                select c.relname, c.relrowsecurity, c.relforcerowsecurity,
                       (select count(*) from pg_policy p where p.polrelid = c.oid) as policies
                from pg_class c join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = 'public' and c.relkind = 'r'
                  and c.relname not in ('alembic_version')
                """
            )
        ).all()
    by_name = {r[0]: r for r in rows}
    assert set(by_name) == set(TENANT_TABLES) | {"tenants"}
    for name, enabled, forced, policies in rows:
        assert enabled and forced and policies >= 1, name


def test_migration_table_list_matches_models(migrated: str) -> None:
    """Migration 0001 hard-codes its table list; every entry must still be a model table.
    Later migrations add tables; the live-database test above is the complete guard."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "novaxis_db"
        / "migrations"
        / "versions"
        / "0001_core_tables.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0001", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.TENANT_TABLES) <= set(TENANT_TABLES)
