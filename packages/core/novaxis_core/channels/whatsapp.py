"""WhatsApp through Meta's WhatsApp Cloud API (docs/whatsapp.md).

Inbound: Meta calls our webhook. The first call is a GET handshake (echo `hub.challenge`
when `hub.verify_token` matches). Messages arrive as POSTs signed with
X-Hub-Signature-256 = "sha256=" + HMAC-SHA256(app secret, raw body). One POST can carry
several messages, and delivery/read receipts, which are ignored.

A business is found by its WhatsApp phone-number id (unique per business). The sender's
WhatsApp id is their phone number, so a customer who texts and uses WhatsApp is one
contact.

Outbound: free-form replies are only allowed within 24 hours of the customer's last
message; later messages need a template Meta has approved. The 24-hour check happens
before sending (outbound.py), so a closed window goes to a person instead of failing.
"""

from __future__ import annotations

import hashlib
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

MEDIA_PREFIX = "whatsapp-media:"
VOICE_NOTE = (
    "[The customer sent a voice note. Voice notes cannot be played here yet; "
    "ask them kindly to type their message.]"
)


def signature(app_secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()


def verify_handshake(query: dict[str, str]) -> str | None:
    """Meta's subscription check: return the challenge to echo, or None to refuse."""
    token = get_settings().whatsapp_verify_token
    if (
        token
        and query.get("hub.mode") == "subscribe"
        and hmac.compare_digest(query.get("hub.verify_token", ""), token)
    ):
        return query.get("hub.challenge", "")
    return None


def _text_of(m: dict[str, Any]) -> tuple[str, list[Media]]:
    kind = m.get("type")
    if kind == "text":
        return str((m.get("text") or {}).get("body", "")), []
    if kind in ("image", "document", "video", "sticker"):
        part = m.get(kind) or {}
        media = Media(
            url=MEDIA_PREFIX + str(part.get("id", "")),
            content_type=part.get("mime_type"),
            filename=part.get("filename"),
        )
        return str(part.get("caption") or ""), [media]
    if kind == "audio":
        return VOICE_NOTE, []
    if kind == "interactive":
        i = m.get("interactive") or {}
        reply = i.get("button_reply") or i.get("list_reply") or {}
        return str(reply.get("title", "")), []
    if kind == "button":
        return str((m.get("button") or {}).get("text", "")), []
    if kind == "location":
        loc = m.get("location") or {}
        parts = [
            loc.get("name"),
            loc.get("address"),
            f"{loc.get('latitude')},{loc.get('longitude')}",
        ]
        return "Location: " + ", ".join(str(p) for p in parts if p), []
    return f"[unsupported WhatsApp message type: {kind}]", []


class WhatsAppAdapter:
    channel = "whatsapp"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def verify_signature(self, request: InboundRequest) -> bool:
        secret = get_settings().whatsapp_app_secret
        given = request.header("X-Hub-Signature-256")
        if not secret or not given:
            return False
        return hmac.compare_digest(given, signature(secret, request.raw_body))

    def parse_many(self, request: InboundRequest) -> list[NormalisedInbound]:
        body = request.json or {}
        if body.get("object") != "whatsapp_business_account":
            raise ParseError("not a WhatsApp Business webhook")
        out: list[NormalisedInbound] = []
        for entry in body.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                phone_number_id = str((value.get("metadata") or {}).get("phone_number_id", ""))
                names = {
                    str(c.get("wa_id")): (c.get("profile") or {}).get("name")
                    for c in value.get("contacts") or []
                }
                for m in value.get("messages") or []:
                    sender = str(m.get("from", ""))
                    if not phone_number_id or not sender or not m.get("id"):
                        raise ParseError("message without id, sender or phone number id")
                    text, media = _text_of(m)
                    if not text and not media:
                        continue
                    out.append(
                        NormalisedInbound(
                            channel=self.channel,
                            provider_ref=str(m["id"]),
                            tenant_ref=phone_number_id,
                            sender_phone="+" + sender.lstrip("+"),
                            sender_name=names.get(sender),
                            body=text,
                            media=media,
                        )
                    )
        return out

    def parse_inbound(self, request: InboundRequest) -> NormalisedInbound:
        found = self.parse_many(request)
        if not found:
            raise ParseError("no customer message in this webhook")
        return found[0]

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        s = get_settings()
        phone_number_id = str(tenant_channel_config.get("phone_number_id", ""))
        if not phone_number_id or not s.whatsapp_access_token:
            raise ValueError("WhatsApp is not connected: phone number id or access token missing")
        with httpx.Client(transport=self._transport, timeout=10) as client:
            r = client.post(
                f"{s.whatsapp_api_base}/{phone_number_id}/messages",
                headers={"Authorization": f"Bearer {s.whatsapp_access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to.lstrip("+"),
                    "type": "text",
                    "text": {"body": body, "preview_url": False},
                },
            )
        r.raise_for_status()
        return ProviderRef(provider_ref=str(r.json()["messages"][0]["id"]))


def download(media_id: str, transport: httpx.BaseTransport | None = None) -> tuple[bytes, str]:
    """WhatsApp media is two calls: the id gives a short-lived URL, both need the token."""
    s = get_settings()
    auth = {"Authorization": f"Bearer {s.whatsapp_access_token}"}
    with httpx.Client(transport=transport, timeout=30, follow_redirects=True) as client:
        meta = client.get(f"{s.whatsapp_api_base}/{media_id}", headers=auth)
        meta.raise_for_status()
        info = meta.json()
        r = client.get(str(info["url"]), headers=auth)
        r.raise_for_status()
        return r.content, str(info.get("mime_type") or r.headers.get("content-type") or "")
