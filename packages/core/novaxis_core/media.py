"""Getting customer attachments into our storage and onto the message row.

Inline attachments (Postmark) are stored during the webhook request. URL media
(Twilio MMS) is fetched by a `fetch_media` job with provider credentials, so a
slow provider never delays the webhook response. Either way the message's
`media` entry gains `stored_key`, `size` and `content_type`, or `error`.
"""

from __future__ import annotations

import base64
import uuid
from typing import Any

import httpx
from sqlalchemy.orm import Session

from novaxis_core.channels import Media
from novaxis_core.channels.whatsapp import MEDIA_PREFIX, download
from novaxis_core.models import AuditLog, Job, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.storage import MediaRejectedError, check_media, get_store, media_key


def _entry(m: Media) -> dict[str, Any]:
    return {"url": m.url, "content_type": m.content_type, "filename": m.filename}


def attach_media(session: Session, tenant: Tenant, msg: Message, media: list[Media]) -> None:
    """Called by ingest right after the message row exists. Stores inline content now,
    enqueues a fetch for URL media."""
    entries: list[dict[str, Any]] = []
    needs_fetch = False
    for i, m in enumerate(media):
        e = _entry(m)
        if m.inline_base64:
            try:
                data = base64.b64decode(m.inline_base64)
                ct = m.content_type or "application/octet-stream"
                check_media(data, ct)
                key = media_key(tenant.id, msg.id, i, ct, m.filename)
                obj = get_store().put(key, data, ct)
                e.update({"stored_key": obj.key, "size": obj.size, "content_type": ct})
            except (MediaRejectedError, ValueError) as exc:
                e["error"] = str(exc)
        else:
            e["stored_key"] = None
            needs_fetch = True
        entries.append(e)
    msg.media = entries
    session.flush()
    if needs_fetch:
        session.add(
            Job(tenant_id=tenant.id, kind="fetch_media", payload={"message_id": str(msg.id)})
        )
        session.flush()


def _provider_auth(url: str) -> tuple[str, str] | None:
    s = get_settings()
    if "twilio.com" in url and s.twilio_account_sid:
        return (s.twilio_account_sid, s.twilio_auth_token)
    return None


def fetch_media(
    session: Session,
    tenant: Tenant,
    message_id: uuid.UUID,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """Download every unfetched URL entry for a message. Returns how many were stored."""
    msg = session.get(Message, message_id)
    if msg is None:
        raise LookupError(f"message {message_id} not found")
    entries = [dict(e) for e in msg.media]
    stored = 0
    with httpx.Client(transport=transport, timeout=30, follow_redirects=True) as client:
        for i, e in enumerate(entries):
            if e.get("stored_key") or e.get("error"):
                continue
            url = str(e.get("url", ""))
            try:
                if url.startswith(MEDIA_PREFIX):
                    content, got_ct = download(url[len(MEDIA_PREFIX) :], transport)
                else:
                    r = client.get(url, auth=_provider_auth(url))
                    r.raise_for_status()
                    content, got_ct = r.content, r.headers.get("content-type") or ""
                ct = got_ct or e.get("content_type") or "application/octet-stream"
                check_media(content, ct)
                key = media_key(tenant.id, msg.id, i, ct, e.get("filename"))
                obj = get_store().put(key, content, ct)
                e.update({"stored_key": obj.key, "size": obj.size, "content_type": ct})
                stored += 1
            except (httpx.HTTPError, MediaRejectedError, ValueError) as exc:
                e["error"] = f"{type(exc).__name__}: {exc}"[:300]
    msg.media = entries
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor="worker:media",
            event="media.fetched",
            subject_table="messages",
            subject_id=msg.id,
            diff={"stored": stored, "failed": sum(1 for e in entries if e.get("error"))},
        )
    )
    session.flush()
    return stored


def media_view(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the API returns: a URL a staff member can open, never the provider URL."""
    store = get_store()
    out: list[dict[str, Any]] = []
    for e in entries:
        key = e.get("stored_key")
        out.append(
            {
                "content_type": e.get("content_type"),
                "filename": e.get("filename"),
                "size": e.get("size"),
                "url": store.url_for(str(key)) if key else None,
                "error": e.get("error"),
            }
        )
    return out
