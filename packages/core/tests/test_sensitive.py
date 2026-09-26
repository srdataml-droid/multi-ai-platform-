from __future__ import annotations

import pytest

from novaxis_core.sensitive import (
    REDACTED,
    decrypt,
    decrypt_fields,
    encrypt,
    encrypt_fields,
    is_encrypted,
    reveal,
    strip_for_analytics,
)

KEYS = frozenset({"symptom", "pain_level"})


def test_roundtrip_and_prefix() -> None:
    token = encrypt("throbbing lower left")
    assert is_encrypted(token) and token.startswith("enc:v1:") and "throbbing" not in token
    assert decrypt(token) == "throbbing lower left"
    assert encrypt(token) == token, "encrypting twice is a no-op"
    assert decrypt("plain") == "plain"


def test_only_sensitive_keys_are_touched() -> None:
    enc = encrypt_fields({"name": "Ben", "symptom": "throbbing"}, KEYS)
    assert enc["name"] == "Ben" and is_encrypted(enc["symptom"])
    assert decrypt_fields(enc, KEYS) == {"name": "Ben", "symptom": "throbbing"}


@pytest.mark.parametrize(
    "role,expect",
    [
        ("owner", "throbbing"),
        ("staff", "throbbing"),
        ("operator", "throbbing"),
        ("viewer", REDACTED),
        ("", REDACTED),
    ],
)
def test_reveal_by_role(role: str, expect: str) -> None:
    enc = encrypt_fields({"name": "Ben", "symptom": "throbbing"}, KEYS)
    out = reveal(enc, KEYS, role)
    assert out["name"] == "Ben" and out["symptom"] == expect


def test_analytics_strip_keeps_presence_only() -> None:
    enc = encrypt_fields({"name": "Ben", "symptom": "throbbing", "pain_level": ""}, KEYS)
    assert strip_for_analytics(enc, KEYS) == {"name": "Ben", "symptom": True, "pain_level": False}
