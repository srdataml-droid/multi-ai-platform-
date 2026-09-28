"""Push events to a business's own agent, so it does not have to poll (docs/agent-api.md).

Events:
- `message.received`: a customer wrote and the agent should answer (sent after the
  platform's emergency check, and only when the conversation is the agent's to answer);
- `proposal.decided`: staff approved, edited or rejected something the agent proposed;
- `ping`: the owner's "Send test" button.

The body carries ids only, never names or message text: the agent reads the details with
its key. So a leaked or mistyped webhook address leaks nothing about customers.

Each request is signed: `X-Novaxis-Signature: t=<unix time>,v1=<hex HMAC-SHA256 of
"<t>.<body>" with the key's webhook secret>`. Agents should reject a bad signature and a
`t` more than five minutes old.

Delivery is a job, so it retries with backoff like any job. If `message.received` still
cannot be delivered after the last attempt, the job carries the conversation id, so the
job loop hands that conversation to a person: a customer is never left waiting on an agent
that cannot be reached. The agent can always poll as well.

Only public HTTPS addresses are called (checked when set and again, after DNS, when sent),
so the webhook cannot be pointed at the platform's own network.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.models import AgentKey, Job, Tenant
from novaxis_core.sensitive import decrypt, encrypt
from novaxis_core.settings import get_settings

AGENT_EVENT_JOB = "agent_event"
SIGNATURE_HEADER = "X-Novaxis-Signature"
MAX_AGE_SECONDS = 300


class WebhookError(ValueError):
    pass


def _dev() -> bool:
    return get_settings().env in ("local", "test")


def _public(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (
        a.is_private
        or a.is_loopback
        or a.is_link_local
        or a.is_reserved
        or a.is_multicast
        or a.is_unspecified
    )


def check_url(url: str) -> str:
    """A webhook address the platform may call: https, no credentials, not a private or
    internal address. Plain http and localhost only in local development."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise WebhookError("the webhook must be an https:// address")
    if parts.scheme == "http" and not _dev():
        raise WebhookError("the webhook must use https")
    if parts.username or parts.password:
        raise WebhookError("the webhook address must not contain a user name or password")
    host = parts.hostname
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if not _dev() and (host == "localhost" or (literal is not None and not _public(host))):
        raise WebhookError("the webhook must be a public address")
    if len(url) > 500:
        raise WebhookError("the webhook address is too long")
    return url


def _resolves_public(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(infos) and all(_public(str(info[4][0])) for info in infos)


def set_webhook(key: AgentKey, url: str | None) -> str | None:
    """Set or clear the key's webhook. Setting it makes a new secret, returned once."""
    if not url:
        key.webhook_url = None
        key.webhook_secret = None
        return None
    key.webhook_url = check_url(url)
    secret = "whsec_" + secrets.token_urlsafe(32)
    key.webhook_secret = encrypt(secret)
    return secret


def signature(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def verify(secret: str, header: str, body: bytes, now: float | None = None) -> bool:
    """What an agent should do with each request (the example agent uses the same logic)."""
    try:
        fields = dict(part.split("=", 1) for part in header.split(","))
        t = int(fields["t"])
    except (ValueError, KeyError):
        return False
    if abs((now or time.time()) - t) > MAX_AGE_SECONDS:
        return False
    return hmac.compare_digest(signature(secret, t, body), header)


def enqueue(
    session: Session,
    tenant_id: uuid.UUID,
    event: str,
    data: dict[str, Any],
    hand_over_if_undelivered: uuid.UUID | None = None,
) -> int:
    """One delivery job per key with a webhook. Returns how many were queued."""
    keys = session.scalars(
        select(AgentKey).where(AgentKey.revoked_at.is_(None), AgentKey.webhook_url.is_not(None))
    )
    n = 0
    for key in keys:
        payload: dict[str, Any] = {
            "key_id": str(key.id),
            "event": event,
            "event_id": str(uuid.uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "data": data,
        }
        if hand_over_if_undelivered is not None:
            # The job loop hands this conversation to a person after the last failed try.
            payload["conversation_id"] = str(hand_over_if_undelivered)
        session.add(Job(tenant_id=tenant_id, kind=AGENT_EVENT_JOB, payload=payload))
        n += 1
    if n:
        session.flush()
    return n


def body_for(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            "id": payload["event_id"],
            "event": payload["event"],
            "created_at": payload["created_at"],
            "data": payload["data"],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def send(key: AgentKey, body: bytes, transport: httpx.BaseTransport | None = None) -> int:
    """POST one signed event. Raises on anything but a 2xx answer."""
    if not key.webhook_url or not key.webhook_secret:
        raise WebhookError("this key has no webhook")
    url = check_url(key.webhook_url)
    if not _dev() and not _resolves_public(url):
        raise WebhookError("the webhook address does not resolve to a public address")
    secret = decrypt(key.webhook_secret)
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: signature(secret, int(time.time()), body),
        "User-Agent": "Novaxis-Webhooks/1",
    }
    with httpx.Client(transport=transport, timeout=5, follow_redirects=False) as client:
        r = client.post(url, content=body, headers=headers)
    r.raise_for_status()
    return r.status_code


def deliver(
    session: Session, tenant: Tenant, job: Job, transport: httpx.BaseTransport | None = None
) -> str:
    """The job handler. A revoked key or a removed webhook ends the job quietly."""
    key = session.get(AgentKey, uuid.UUID(job.payload["key_id"]))
    if key is None or key.revoked_at is not None or not key.webhook_url:
        return "skipped: no active webhook"
    status = send(key, body_for(job.payload), transport)
    return f"delivered {status}"


def ping(key: AgentKey, transport: httpx.BaseTransport | None = None) -> int:
    payload = {
        "event": "ping",
        "event_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "data": {"key": key.name},
    }
    return send(key, body_for(payload), transport)
