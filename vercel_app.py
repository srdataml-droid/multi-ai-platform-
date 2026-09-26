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

__all__ = ["app"]
