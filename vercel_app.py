"""Vercel entrypoint for the API project.

The repo is a uv workspace; on Vercel only the root dependencies are installed, so
the workspace packages are made importable from their source folders here. The app
itself is exactly `novaxis_api.main:app`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _pkg in ("packages/core", "packages/db", "packages/packs", "apps/worker", "apps/api"):
    _p = str(_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from novaxis_api.main import app  # noqa: E402
from novaxis_core.settings import get_settings  # noqa: E402

if get_settings().auto_migrate:
    # A new deployment starts serving the moment it is promoted; bring the schema to head
    # first so its code never meets the previous schema. See ADR 0013.
    import logging

    from novaxis_db.migrate import ensure_schema
    from novaxis_db.session import normalise_url

    try:
        if ensure_schema(normalise_url(get_settings().database_url)):
            logging.getLogger("novaxis.deploy").warning("auto-migrate applied pending migrations")
    except Exception:  # noqa: BLE001 - log loudly, keep serving what still works
        logging.getLogger("novaxis.deploy").exception("auto-migrate failed")

__all__ = ["app"]
