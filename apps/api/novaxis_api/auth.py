"""Who is calling, and which tenant they belong to.

The dashboard sends a JWT issued by the identity provider (Supabase Auth in
staging and production, `devtoken.py` locally). We verify it, look the subject
up in `users`, and hand the route a tenant-scoped session. The route never
sees a tenant id it did not earn through this dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.models import User
from novaxis_core.settings import get_settings
from novaxis_db.session import service_session, tenant_session


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    email: str


def _decode(token: str) -> tuple[str, str | None]:
    """Verify the JWT; return (subject, email-or-None)."""
    s = get_settings()
    try:
        claims = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], audience=s.jwt_audience)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token has no subject")
    email = claims.get("email")
    return sub, (email.lower() if isinstance(email, str) else None)


def current_principal(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    subject, email = _decode(authorization.split(" ", 1)[1].strip())
    # Cross-tenant lookup by subject: the one place a request uses the service session.
    with service_session() as s:
        user = s.scalar(select(User).where(User.auth_subject == subject))
        if user is None and email:
            # First login of a user an owner pre-registered by email: bind the subject.
            user = s.scalar(select(User).where(User.auth_subject == f"email|{email}"))
            if user is not None:
                user.auth_subject = subject
                s.flush()
        if user is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "no user for this identity")
        return Principal(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role, email=user.email
        )


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def db(principal: CurrentPrincipal) -> Iterator[Session]:
    with tenant_session(principal.tenant_id) as s:
        yield s


TenantDb = Annotated[Session, Depends(db)]
