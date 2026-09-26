"""Our own website widget.

Verification: the widget is public code, so there is no secret to check. What we
verify is the *visitor token*, an HMAC-signed visitor id we minted, so a returning
visitor threads into the same conversation and nobody can forge another visitor's
id. Origin allow-listing and rate limits arrive in Chunk 12.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from novaxis_core.channels.base import (
    InboundRequest,
    NormalisedInbound,
    ParseError,
    ProviderRef,
)
from novaxis_core.settings import get_settings


def _secret() -> bytes:
    s = get_settings()
    return (s.visitor_token_secret or s.jwt_secret).encode()


def mint_visitor_token(visitor_id: str | None = None) -> str:
    vid = visitor_id or secrets.token_urlsafe(16)
    sig = hmac.new(_secret(), vid.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{vid}.{sig}"


def verify_visitor_token(token: str | None) -> str | None:
    """Return the visitor id if the token is genuine, else None."""
    if not token or "." not in token:
        return None
    vid, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret(), vid.encode(), hashlib.sha256).hexdigest()[:32]
    return vid if hmac.compare_digest(sig, expected) else None


class WebchatAdapter:
    channel = "webchat"

    def verify_signature(self, request: InboundRequest) -> bool:
        # Nothing to verify at the transport level; see module docstring.
        return True

    def parse_inbound(self, request: InboundRequest) -> NormalisedInbound:
        body = request.json or {}
        text = str(body.get("body", "")).strip()
        if not text:
            raise ParseError("empty body")
        tenant_slug = request.query.get("tenant") or str(body.get("tenant", ""))
        if not tenant_slug:
            raise ParseError("missing tenant")
        visitor_id = (
            verify_visitor_token(body.get("visitor_token")) or mint_visitor_token().split(".")[0]
        )
        message_id = str(body.get("message_id") or secrets.token_urlsafe(12))
        return NormalisedInbound(
            channel=self.channel,
            provider_ref=f"webchat:{visitor_id}:{message_id}",
            tenant_ref=tenant_slug,
            sender_visitor_id=visitor_id,
            sender_name=(str(body["name"]).strip() or None) if body.get("name") else None,
            body=text[:4000],
            raw={"page": body.get("page")} if body.get("page") else {},
        )

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        # Web chat replies are read back by the widget from the conversation itself
        # (GET /inbound/webchat/messages); there is no push transport to call.
        return ProviderRef(provider_ref=f"webchat:{to}:{secrets.token_urlsafe(8)}")
