"""Twilio SMS and MMS.

Signature: Twilio sends X-Twilio-Signature = base64(HMAC-SHA1(auth_token,
full_url + sorted form params concatenated)). We recompute it against the
public URL from settings, because behind a proxy the URL the app sees differs
from the one Twilio signed. Implemented directly so the core has no Twilio SDK
dependency; it is twelve lines and Twilio documents it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from novaxis_core.channels.base import (
    InboundRequest,
    Media,
    NormalisedInbound,
    ParseError,
    ProviderRef,
)
from novaxis_core.settings import get_settings


def compute_signature(auth_token: str, url: str, form: dict[str, str]) -> str:
    payload = url + "".join(k + form[k] for k in sorted(form))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _public_url(request_url: str) -> str:
    """The URL Twilio signed: our configured public base plus the request path and query."""
    base = urlsplit(get_settings().public_base_url)
    seen = urlsplit(request_url)
    return urlunsplit((base.scheme, base.netloc, seen.path, seen.query, ""))


class TwilioSmsAdapter:
    channel = "twilio_sms"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def verify_signature(self, request: InboundRequest) -> bool:
        token = get_settings().twilio_auth_token
        given = request.header("X-Twilio-Signature")
        if not token or not given:
            return False
        expected = compute_signature(token, _public_url(request.url), request.form)
        return hmac.compare_digest(given, expected)

    def parse_inbound(self, request: InboundRequest) -> NormalisedInbound:
        f = request.form
        sid, sender, to = f.get("MessageSid"), f.get("From"), f.get("To")
        if not sid or not sender or not to:
            raise ParseError("missing MessageSid, From or To")
        media: list[Media] = []
        for i in range(int(f.get("NumMedia", "0") or 0)):
            url = f.get(f"MediaUrl{i}")
            if url:
                media.append(Media(url=url, content_type=f.get(f"MediaContentType{i}")))
        body = (f.get("Body") or "").strip()
        if not body and not media:
            raise ParseError("empty message")
        return NormalisedInbound(
            channel=self.channel,
            provider_ref=sid,
            tenant_ref=to,
            sender_phone=sender,
            body=body,
            media=media,
            raw={k: f[k] for k in ("FromCity", "FromCountry") if k in f},
        )

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        s = get_settings()
        sender = str(tenant_channel_config.get("number", ""))
        if not sender:
            raise ValueError("tenant has no twilio number configured")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
        with httpx.Client(transport=self._transport, timeout=10) as client:
            r = client.post(
                url,
                auth=(s.twilio_account_sid, s.twilio_auth_token),
                data={"From": sender, "To": to, "Body": body},
            )
        r.raise_for_status()
        return ProviderRef(provider_ref=str(r.json()["sid"]))
