"""Run migrations from Python, so tests and `make migrate` share one code path."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _config(url: str) -> Config:
    cfg = Config(str(_INI))
    cfg.attributes["url"] = url
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(_config(url), revision)


def downgrade(url: str, revision: str = "base") -> None:
    command.downgrade(_config(url), revision)
