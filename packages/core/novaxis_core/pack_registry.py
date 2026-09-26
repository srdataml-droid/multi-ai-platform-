"""How core code finds a tenant's pack without importing the packs package.

The packs package registers its loader at import time; the worker, the API and
the tests all import it. Core only ever calls `resolve_pack(pack_id)`.
"""

from __future__ import annotations

from collections.abc import Callable

from novaxis_core.packspec import PackSpec

_resolver: Callable[[str], PackSpec] | None = None


def set_pack_resolver(fn: Callable[[str], PackSpec]) -> None:
    global _resolver
    _resolver = fn


def resolve_pack(pack_id: str) -> PackSpec:
    if _resolver is None:
        raise RuntimeError("no pack resolver registered; import novaxis_packs first")
    return _resolver(pack_id)
