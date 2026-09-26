"""Vertical packs as folders of data. `get_pack(id)` loads and caches them; an
unknown id falls back to the generic pack so a mistyped tenant setting degrades
to a safe default rather than a crash."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from novaxis_core.packs import load_pack
from novaxis_core.packspec import PackSpec

PACKS_DIR = Path(__file__).resolve().parent
PACK_IDS: tuple[str, ...] = ("hvac", "dental", "restoration")


def available_packs() -> list[str]:
    return sorted(p.name for p in PACKS_DIR.iterdir() if (p / "manifest.yaml").exists())


@lru_cache(maxsize=16)
def get_pack(pack_id: str) -> PackSpec:
    folder = PACKS_DIR / pack_id
    if not (folder / "manifest.yaml").exists():
        folder = PACKS_DIR / "generic"
    return load_pack(folder)
