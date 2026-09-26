"""Alembic environment. The database URL comes from settings (or an explicit
override in `config.attributes["url"]` when run programmatically)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from novaxis_core.models import Base
from novaxis_core.settings import get_settings

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    override = config.attributes.get("url")
    return str(override) if override else get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
