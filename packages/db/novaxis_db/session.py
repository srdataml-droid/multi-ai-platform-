"""Sessions with the tenant boundary applied by the database.

`tenant_session(tenant_id)` switches the connection to the app role and sets
`app.tenant_id` at the start of every transaction, so RLS filters every query.
`service_session()` does neither and is for migrations, seeds and cross-tenant
roll-ups only. Nothing that handles a web request or a job may use it.

Why SET ROLE rather than a second login: one connection string, one pool, and
the owner role keeps the power to run migrations. The app role is a member
grant, not a password. See ADR 0003.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.orm import Session, SessionTransaction

from novaxis_core.settings import get_settings


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url, pool_pre_ping=True)


def _apply_tenant(conn: Connection, tenant_id: uuid.UUID, role: str) -> None:
    # Role names cannot be bound parameters; the value comes from settings, not users.
    conn.execute(text(f'SET LOCAL ROLE "{role}"'))
    conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})


@contextmanager
def tenant_session(tenant_id: uuid.UUID, url: str | None = None) -> Iterator[Session]:
    """A session that can only see and write rows belonging to `tenant_id`."""
    role = get_settings().app_role
    session = Session(get_engine(url))

    @event.listens_for(session, "after_begin")
    def _on_begin(sess: Session, _tx: SessionTransaction, conn: Connection) -> None:
        _apply_tenant(conn, tenant_id, role)

    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def service_session(url: str | None = None) -> Iterator[Session]:
    """Unscoped session. Migrations, seeds, operator tooling and roll-ups only."""
    session = Session(get_engine(url))
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
