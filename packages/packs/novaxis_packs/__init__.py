"""Vertical packs. Until the loader lands in Chunk 5, every pack id resolves to the
generic pack so the worker runs end to end for any tenant."""

from __future__ import annotations

from novaxis_core.packspec import PackSpec
from novaxis_packs.generic import GENERIC

PACK_IDS: tuple[str, ...] = ("hvac", "dental", "restoration")


def get_pack(pack_id: str) -> PackSpec:
    return GENERIC
