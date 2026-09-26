"""Sensitive intake fields at rest.

A pack marks intake questions `sensitive: true` (dental symptoms, pain, funding).
Those values are encrypted before they reach `conversations.extracted`, decrypted
only inside a worker turn or for a staff-level read, excluded from logs and
analytics, and shown to a `viewer` as a placeholder.

Application-level Fernet rather than pgcrypto, so the key lives in the process
environment and never in the database (ADR 0009).
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from novaxis_core.settings import get_settings

PREFIX = "enc:v1:"
REDACTED = "[redacted]"
READ_ROLES = frozenset({"owner", "staff", "operator"})


class SensitiveKeyError(RuntimeError):
    """No usable key outside local development."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    s = get_settings()
    if s.sensitive_fields_key:
        return Fernet(s.sensitive_fields_key.encode())
    if s.env != "local" and s.env != "test":
        raise SensitiveKeyError("NOVAXIS_SENSITIVE_FIELDS_KEY must be set outside local")
    derived = hashlib.sha256(f"sensitive:{s.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def reset_key_cache() -> None:
    _fernet.cache_clear()


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value: str) -> str:
    if is_encrypted(value):
        return value
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not is_encrypted(value):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken as exc:
        raise SensitiveKeyError("cannot decrypt: wrong key") from exc


def encrypt_fields(fields: dict[str, str], sensitive_keys: frozenset[str]) -> dict[str, str]:
    # Empty stays empty so "was it provided" survives encryption.
    return {k: (encrypt(v) if k in sensitive_keys and v else v) for k, v in fields.items()}


def decrypt_fields(fields: dict[str, Any], sensitive_keys: frozenset[str]) -> dict[str, Any]:
    return {
        k: (decrypt(v) if k in sensitive_keys and isinstance(v, str) else v)
        for k, v in fields.items()
    }


def reveal(fields: dict[str, Any], sensitive_keys: frozenset[str], role: str) -> dict[str, Any]:
    """What a given role may see. Staff-level roles get plaintext; anyone else a placeholder."""
    if role in READ_ROLES:
        return decrypt_fields(fields, sensitive_keys)
    return {k: (REDACTED if k in sensitive_keys else v) for k, v in fields.items()}


def strip_for_analytics(fields: dict[str, Any], sensitive_keys: frozenset[str]) -> dict[str, Any]:
    """Roll-ups never carry sensitive values, only whether they were provided."""
    return {k: (bool(v) if k in sensitive_keys else v) for k, v in fields.items()}
