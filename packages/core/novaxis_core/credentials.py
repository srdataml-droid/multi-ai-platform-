"""Per-tenant integration credentials, encrypted at rest with the sensitive-fields key.
The web never sees these; only the worker and the OAuth callback touch them."""

from __future__ import annotations

import json
from typing import Any

from novaxis_core.sensitive import decrypt, encrypt


def seal(data: dict[str, Any]) -> bytes:
    return encrypt(json.dumps(data, sort_keys=True)).encode()


def unseal(blob: bytes | None) -> dict[str, Any]:
    if not blob:
        return {}
    out = json.loads(decrypt(blob.decode()))
    return out if isinstance(out, dict) else {}
