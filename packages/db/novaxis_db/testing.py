"""Shared Postgres fixtures, loaded as a pytest plugin from the root conftest.
Tests that need Postgres are skipped, with a message, when NOVAXIS_TEST_DATABASE_URL
is unreachable. CI provides a Postgres service."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from novaxis_core.models import Tenant
from novaxis_db import migrate
from novaxis_db.session import get_engine, service_session

TEST_URL = os.environ.get(
    "NOVAXIS_TEST_DATABASE_URL",
    "postgresql+psycopg://novaxis:novaxis@localhost:5432/novaxis_test",
)


def _reachable(url: str) -> bool:
    try:
        with create_engine(url).connect() as c:
            c.execute(text("select 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure means "no database here"
        return False


@pytest.fixture(scope="session")
def db_url() -> str:
    if not _reachable(TEST_URL):
        pytest.skip(f"no test database at {TEST_URL}")
    return TEST_URL


@pytest.fixture(scope="session")
def migrated(db_url: str) -> Iterator[str]:
    """A fresh schema at head for the whole test session."""
    migrate.downgrade(db_url, "base")
    migrate.upgrade(db_url, "head")
    get_engine.cache_clear()
    os.environ["NOVAXIS_DATABASE_URL"] = db_url
    from novaxis_core.settings import get_settings

    get_settings.cache_clear()
    yield db_url


@pytest.fixture
def two_tenants(migrated: str) -> tuple[uuid.UUID, uuid.UUID]:
    with service_session(migrated) as s:
        a = Tenant(name="A", slug=f"a-{uuid.uuid4().hex[:8]}", pack_id="hvac")
        b = Tenant(name="B", slug=f"b-{uuid.uuid4().hex[:8]}", pack_id="dental")
        s.add_all([a, b])
        s.flush()
        return a.id, b.id
