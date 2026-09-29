"""Sensitive intake fields at rest.

A pack marks intake questions `sensitive: true` (dental symptoms, pain, funding), and a
business can mark its own booking-type questions Private (booking_types.sensitive_keys_for
joins the two). Those values are encrypted before they reach `conversations.extracted`, decrypted
only inside a worker turn or for a staff-level read, excluded from logs and
analytics, and shown to a `viewer` as a placeholder.

Message text (what customers and the assistant wrote, voice-note transcripts) and
conversation summaries are encrypted the same way, always: `EncryptedText` on the columns,
`encrypt` on transcripts (migration 0022 encrypted what was stored before).

Application-level Fernet rather than pgcrypto, so the key lives in the process
environment and never in the database (ADR 0009).
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from novaxis_core.settings import get_settings

PREFIX = "enc:v1:"
REDACTED = "[redacted]"
READ_ROLES = frozenset({"owner", "staff", "operator"})


class EncryptedText(TypeDecorator[str]):
    """A text column stored encrypted and read as plain text. Rows written before a column
    became encrypted read as they are (decrypt passes plain text through) until the
    migration that encrypts them has run."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        return None if value is None else encrypt(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        return None if value is None else decrypt(value)


class SensitiveKeyError(RuntimeError):
    """No usable key outside local development."""


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    """NOVAXIS_SENSITIVE_FIELDS_KEY may hold several keys, comma separated: the first
    encrypts, any of them decrypts. To rotate, put the new key first and keep the old one
    after it until everything has been re-encrypted (docs/encryption.md)."""
    s = get_settings()
    keys = [Fernet(k.strip().encode()) for k in s.sensitive_fields_key.split(",") if k.strip()]
    if not keys:
        if s.env != "local" and s.env != "test":
            raise SensitiveKeyError("NOVAXIS_SENSITIVE_FIELDS_KEY must be set outside local")
        derived = hashlib.sha256(f"sensitive:{s.jwt_secret}".encode()).digest()
        keys = [Fernet(base64.urlsafe_b64encode(derived))]
    if s.sensitive_fields_key_next.strip():
        keys.insert(0, Fernet(s.sensitive_fields_key_next.strip().encode()))
    return MultiFernet(keys)


@lru_cache(maxsize=1)
def _newest() -> Fernet:
    s = get_settings()
    first = s.sensitive_fields_key_next.strip() or s.sensitive_fields_key.split(",")[0].strip()
    if first:
        return Fernet(first.encode())
    derived = hashlib.sha256(f"sensitive:{s.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def rotate(value: str) -> str:
    """The same value encrypted under the newest key; unchanged when it already is, or when
    it is not encrypted at all."""
    if not is_encrypted(value):
        return value
    token = value[len(PREFIX) :].encode()
    try:
        _newest().decrypt(token)
        return value
    except InvalidToken:
        pass
    try:
        return PREFIX + _fernet().rotate(token).decode()
    except InvalidToken as exc:
        raise SensitiveKeyError("cannot re-encrypt: no key decrypts this value") from exc


def reset_key_cache() -> None:
    _fernet.cache_clear()
    _newest.cache_clear()


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
    # By the value, not the list: an answer stays readable after its question stops being
    # marked private (it was encrypted when it was stored).
    del sensitive_keys
    return {k: (decrypt(v) if isinstance(v, str) else v) for k, v in fields.items()}


def _private(k: str, v: Any, sensitive_keys: frozenset[str]) -> bool:
    return k in sensitive_keys or is_encrypted(v)


def reveal(fields: dict[str, Any], sensitive_keys: frozenset[str], role: str) -> dict[str, Any]:
    """What a given role may see. Staff-level roles get plaintext; anyone else a placeholder."""
    if role in READ_ROLES:
        return decrypt_fields(fields, sensitive_keys)
    return {k: (REDACTED if _private(k, v, sensitive_keys) else v) for k, v in fields.items()}


def strip_for_analytics(fields: dict[str, Any], sensitive_keys: frozenset[str]) -> dict[str, Any]:
    """Roll-ups never carry sensitive values, only whether they were provided."""
    return {k: (bool(v) if _private(k, v, sensitive_keys) else v) for k, v in fields.items()}
