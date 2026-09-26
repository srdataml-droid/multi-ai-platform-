"""Migrations round-trip on an empty database and leave nothing behind."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from novaxis_db import migrate


def _table_names(url: str) -> set[str]:
    with create_engine(url).connect() as c:
        rows = c.execute(text("select tablename from pg_tables where schemaname = 'public'")).all()
    return {r[0] for r in rows}


def test_upgrade_downgrade_upgrade(db_url: str) -> None:
    migrate.downgrade(db_url, "base")
    assert _table_names(db_url) <= {"alembic_version"}
    migrate.upgrade(db_url, "head")
    assert "tenants" in _table_names(db_url)
    migrate.downgrade(db_url, "base")
    assert _table_names(db_url) <= {"alembic_version"}
    migrate.upgrade(db_url, "head")


def test_ensure_schema_catches_up_once_then_does_nothing(db_url: str) -> None:
    migrate.upgrade(db_url, "head")
    assert migrate.ensure_schema(db_url) is False
    migrate.downgrade(db_url, "-1")
    behind = migrate.current(db_url)
    assert migrate.ensure_schema(db_url) is True
    assert migrate.current(db_url) != behind
    assert migrate.ensure_schema(db_url) is False
