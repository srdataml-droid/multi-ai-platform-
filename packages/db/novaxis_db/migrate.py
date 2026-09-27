"""Run migrations from Python, so tests and `make migrate` share one code path."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _config(url: str) -> Config:
    cfg = Config(str(_INI))
    cfg.attributes["url"] = url
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(_config(url), revision)


def downgrade(url: str, revision: str = "base") -> None:
    command.downgrade(_config(url), revision)


def current(url: str) -> str | None:
    engine = create_engine(url, poolclass=NullPool, connect_args=_connect_args(url))
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def _connect_args(url: str) -> dict[str, object]:
    return {"prepare_threshold": None} if "psycopg" in url else {}


def head(url: str) -> str | None:
    return ScriptDirectory.from_config(_config(url)).get_current_head()


def ensure_schema(url: str) -> bool:
    """Bring the database to head if it is behind. Returns True if anything ran.

    Called when a new API deployment starts (NOVAXIS_AUTO_MIGRATE), so new code never
    serves requests against the previous schema. Concurrent callers are serialised by the
    lock in env.py."""
    if current(url) == head(url):
        return False
    upgrade(url, "head")
    return True
