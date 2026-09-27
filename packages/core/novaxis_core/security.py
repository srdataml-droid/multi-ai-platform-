"""Login codes for demo mode and a rate limiter every serverless instance shares."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

_N, _R, _P = 2**14, 8, 1


def new_login_code() -> str:
    """Ten characters, no look-alikes, easy to type from a phone."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


def hash_code(code: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(code.strip().upper().encode(), salt=salt, n=_N, r=_R, p=_P)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def check_code(code: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_b64, digest_b64 = stored.split("$")
    digest = hashlib.scrypt(
        code.strip().upper().encode(), salt=base64.b64decode(salt_b64), n=_N, r=_R, p=_P
    )
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def allow(
    session: Session, key: str, limit: int, window_seconds: int, now: datetime | None = None
) -> bool:
    """Count one request against `key` in the current fixed window; False once over `limit`.
    Needs a service session: the counter table is service-only."""
    now = now or datetime.now(UTC)
    epoch = int(now.timestamp())
    window = datetime.fromtimestamp(epoch - epoch % window_seconds, UTC)
    count: int = session.execute(
        text(
            "INSERT INTO rate_limits (key, window_start, count) VALUES (:k, :w, 1) "
            "ON CONFLICT (key, window_start) DO UPDATE SET count = rate_limits.count + 1 "
            "RETURNING count"
        ),
        {"k": key[:200], "w": window},
    ).scalar_one()
    return int(count) <= limit


def prune(session: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    result = session.execute(
        text("DELETE FROM rate_limits WHERE window_start < :cutoff"),
        {"cutoff": datetime.fromtimestamp(now.timestamp() - 86400, UTC)},
    )
    return int(getattr(result, "rowcount", 0) or 0)
