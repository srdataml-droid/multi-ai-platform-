"""Getting customer attachments into our storage and onto the message row.

Inline attachments (Postmark) are stored during the webhook request. URL media
(Twilio MMS) is fetched by a `fetch_media` job with provider credentials, so a
slow provider never delays the webhook response. Either way the message's
`media` entry gains `stored_key`, `size` and `content_type`, or `error`.

Voice notes (audio) are transcribed by the same job (stt.py): the entry gains
`transcript`, or `transcript_error`. The assistant's turn for a voice note waits for
that job (inbound.py), and everything that reads what the customer said, the emergency
check included, reads `text_of(message)`: the text plus any transcripts.
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
from novaxis_core.stt import Transcriber, TranscriptionError, build_stt

UNHEARD = (
    "[The customer sent a voice note that could not be transcribed. Ask them kindly to "
    "type their message.]"
)


def is_audio(content_type: str | None) -> bool:
    return (content_type or "").lower().startswith("audio/")


def _entry(m: Media) -> dict[str, Any]:
    e: dict[str, Any] = {"url": m.url, "content_type": m.content_type, "filename": m.filename}
    if is_audio(m.content_type):
        e["audio"] = True
    return e


def text_of(msg: Message) -> str:
    """What the customer said: the text, then each voice note's transcript (or a note that
    it could not be heard). The only way turn, gate and agent read an inbound message."""
    parts = [msg.body] if msg.body else []
    for e in getattr(msg, "media", None) or []:
        if not e.get("audio"):
            continue
        t = str(e.get("transcript") or "").strip()
        parts.append(f"[Voice note]: {t}" if t else UNHEARD)
    return "\n".join(parts)


def voice_pending(msg: Message) -> bool:
    """A voice note that has not been through the fetch-and-transcribe job yet."""
    return any(
        e.get("audio") and "transcript" not in e and "transcript_error" not in e
        for e in msg.media or []
    )


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
        if e.get("audio") and not e.get("error"):
            needs_fetch = True  # the job transcribes it
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
    stt: Transcriber | None | bool = True,
) -> int:
    """Download every unfetched URL entry for a message, then transcribe its voice notes.
    Returns how many were stored. `stt=True` means "the configured transcriber"."""
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
    _transcribe(entries, build_stt() if stt is True else (stt or None))
    msg.media = entries
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor="worker:media",
            event="media.fetched",
            subject_table="messages",
            subject_id=msg.id,
            diff={
                "stored": stored,
                "failed": sum(1 for e in entries if e.get("error")),
                "transcribed": sum(1 for e in entries if e.get("transcript")),
            },
        )
    )
    session.flush()
    return stored


def _transcribe(entries: list[dict[str, Any]], stt: Transcriber | None) -> None:
    """Each stored voice note not yet transcribed. A failure is recorded on the entry and
    the assistant asks the customer to type; it never stops the conversation."""
    for e in entries:
        if not e.get("audio") or "transcript" in e or "transcript_error" in e:
            continue
        if not e.get("stored_key"):
            e["transcript_error"] = e.get("error") or "the voice note could not be fetched"
            continue
        if stt is None:
            e["transcript_error"] = "speech to text is not set up"
            continue
        try:
            audio, ct = get_store().get(str(e["stored_key"]))
            t = stt.transcribe(audio, ct or str(e.get("content_type") or ""), _filename(e))
            e["transcript"] = t.text
            e["transcript_model"] = t.model
        except (TranscriptionError, httpx.HTTPError, OSError, ValueError) as exc:
            e["transcript_error"] = f"{type(exc).__name__}: {exc}"[:300]


def _filename(e: dict[str, Any]) -> str:
    """Whisper servers pick the decoder from the file name's extension."""
    if e.get("filename"):
        return str(e["filename"])
    ct = str(e.get("content_type") or "").split(";")[0]
    ext = {
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/amr": "amr",
        "audio/aac": "aac",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
    }
    return f"voice-note.{ext.get(ct, 'ogg')}"


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
                "transcript": e.get("transcript"),
                "transcript_error": e.get("transcript_error") if e.get("audio") else None,
            }
        )
    return out
