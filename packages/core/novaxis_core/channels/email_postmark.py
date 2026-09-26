"""Email via Postmark: inbound webhook JSON in, send API out.

Postmark does not sign inbound webhooks; its guidance is a secret in the webhook
URL. We accept it as `?token=` or `X-Novaxis-Inbound-Token` and compare in
constant time. Tenant routing is by the `To` address (each tenant gets an inbound
address, or a plus-suffix on a shared one via Postmark's MailboxHash).
"""

from __future__ import annotations

import hmac
from typing import Any

import httpx

from novaxis_core.channels.base import (
    InboundRequest,
    Media,
    NormalisedInbound,
    ParseError,
    ProviderRef,
)
from novaxis_core.settings import get_settings


class PostmarkEmailAdapter:
    channel = "email"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def verify_signature(self, request: InboundRequest) -> bool:
        expected = get_settings().postmark_inbound_token
        given = request.query.get("token") or request.header("X-Novaxis-Inbound-Token") or ""
        return bool(expected) and hmac.compare_digest(given, expected)

    def parse_inbound(self, request: InboundRequest) -> NormalisedInbound:
        p = request.json or {}
        message_id = p.get("MessageID")
        from_full = p.get("FromFull") or {}
        sender = (from_full.get("Email") or p.get("From") or "").strip().lower()
        to_full = p.get("ToFull") or []
        to = (to_full[0].get("Email") if to_full else p.get("To") or "").strip().lower()
        if not message_id or not sender or not to:
            raise ParseError("missing MessageID, From or To")
        body = (p.get("StrippedTextReply") or p.get("TextBody") or "").strip()
        subject = (p.get("Subject") or "").strip()
        if subject and body:
            body = f"Subject: {subject}\n\n{body}"
        elif subject:
            body = f"Subject: {subject}"
        if not body:
            raise ParseError("empty email")
        media = [
            Media(
                url=f"postmark-attachment:{a.get('Name')}",
                content_type=a.get("ContentType"),
                filename=a.get("Name"),
                inline_base64=a.get("Content"),
            )
            for a in p.get("Attachments") or []
            if a.get("Name")
        ]
        return NormalisedInbound(
            channel=self.channel,
            provider_ref=str(message_id),
            tenant_ref=to,
            sender_email=sender,
            sender_name=(from_full.get("Name") or "").strip() or None,
            body=body[:8000],
            media=media,
            raw={"subject": subject} if subject else {},
        )

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        s = get_settings()
        sender = str(tenant_channel_config.get("from_address", ""))
        if not sender:
            raise ValueError("tenant has no email from_address configured")
        subject = str(tenant_channel_config.get("subject", "Reply from {business}")).format(
            business=tenant_channel_config.get("business_name", "us")
        )
        with httpx.Client(transport=self._transport, timeout=10) as client:
            r = client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": s.postmark_server_token},
                json={"From": sender, "To": to, "Subject": subject, "TextBody": body},
            )
        r.raise_for_status()
        return ProviderRef(provider_ref=str(r.json()["MessageID"]))
