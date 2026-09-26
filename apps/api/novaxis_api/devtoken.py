"""Mint a local JWT for a seeded user. Never valid outside env=local because
staging and production use a different secret.

    uv run python -m novaxis_api.devtoken owner@demo-hvac
"""

from __future__ import annotations

import sys
import time

import jwt

from novaxis_core.settings import get_settings


def mint(subject: str, ttl_seconds: int = 8 * 3600) -> str:
    s = get_settings()
    now = int(time.time())
    claims = {"sub": subject, "aud": s.jwt_audience, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m novaxis_api.devtoken <owner@demo-hvac>", file=sys.stderr)
        raise SystemExit(2)
    print(mint(f"dev|{sys.argv[1]}"))


if __name__ == "__main__":
    main()
