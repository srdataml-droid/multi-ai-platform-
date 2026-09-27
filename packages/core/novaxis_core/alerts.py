"""Staff alerts: tell a person, on their own phone or computer, that something needs them.

Browser push (Web Push, VAPID) is the channel that needs no provider account, so it works
from day one: an owner taps "turn on alerts on this device" once. Email and SMS are added
by `notify.py` and the emergency executor when those providers are connected.

What goes on a lock screen is deliberately generic: no customer names, no message text.
The alert says what kind of thing is waiting and links to the dashboard.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novaxis_core.models import AuditLog, Job, PushSubscription, Tenant, User
from novaxis_core.settings import get_settings

log = logging.getLogger("novaxis.alerts")

ALERT_JOB = "alert_staff"
ALERT_ROLES = ("owner", "staff")

# (subscription_info, payload json) -> HTTP status from the push service.
PushSender = Callable[[dict[str, Any], str], int]
_sender_override: PushSender | None = None


def set_push_sender(fn: PushSender | None) -> None:
    """Tests plug in a fake push service."""
    global _sender_override
    _sender_override = fn


def push_configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


def _webpush(subscription: dict[str, Any], payload: str) -> int:
    from pywebpush import WebPushException, webpush

    s = get_settings()
    try:
        r = webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject or s.public_web_url},
            timeout=10,
        )
        return int(r.status_code)
    except WebPushException as exc:
        return int(exc.response.status_code) if exc.response is not None else 0
    except Exception:  # noqa: BLE001 - one bad device must not stop the others
        log.exception("push failed")
        return 0


def alert_staff(
    session: Session,
    tenant: Tenant,
    title: str,
    body: str,
    url: str,
    urgent: bool = False,
    only_user: uuid.UUID | None = None,
) -> int:
    """Push to every device of the tenant's owners and staff. Returns how many accepted it."""
    if not push_configured():
        return 0
    staff = select(User.id).where(User.role.in_(ALERT_ROLES))
    if only_user is not None:
        staff = staff.where(User.id == only_user)
    subs = list(
        session.scalars(select(PushSubscription).where(PushSubscription.user_id.in_(staff)))
    )
    payload = json.dumps({"title": title, "body": body, "url": url, "urgent": urgent, "tag": url})
    send = _sender_override or _webpush
    delivered = 0
    for sub in subs:
        status = send(
            {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, payload
        )
        if 200 <= status < 300:
            delivered += 1
            sub.last_ok_at = datetime.now(UTC)
        elif status in (404, 410):
            session.delete(sub)  # the browser unsubscribed or the device is gone
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor="worker:alerts",
            event="staff.alerted",
            diff={"title": title, "devices": len(subs), "delivered": delivered, "urgent": urgent},
        )
    )
    session.flush()
    return delivered


def enqueue_alert(session: Session, tenant_id: uuid.UUID, title: str, body: str, url: str) -> Job:
    """For alerts that need not hold up the current work (everything but emergencies)."""
    job = Job(
        tenant_id=tenant_id,
        kind=ALERT_JOB,
        payload={"title": title, "body": body, "url": url},
    )
    session.add(job)
    session.flush()
    return job


def needs_a_person(session: Session, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> Job:
    return enqueue_alert(
        session,
        tenant_id,
        "A customer needs a person",
        "A conversation has been handed to your team. Open it to reply.",
        f"/conversations/{conversation_id}",
    )


def alert_channels(session: Session, tenant: Tenant) -> dict[str, Any]:
    """Which ways of reaching staff actually work right now. The dashboard warns when none."""
    staff = select(User.id).where(User.role.in_(ALERT_ROLES))
    devices = session.scalar(
        select(func.count())
        .select_from(PushSubscription)
        .where(PushSubscription.user_id.in_(staff))
    )
    return {**alert_channels_for_settings(tenant.settings), "push_devices": int(devices or 0)}


def alert_channels_for_settings(settings: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    email_cfg = ((settings.get("channels") or {}).get("email") or {}).get("config") or {}
    sms_cfg = ((settings.get("channels") or {}).get("twilio_sms") or {}).get("config") or {}
    return {
        "push_available": push_configured(),
        "push_devices": 0,
        "email": bool(s.postmark_server_token and email_cfg.get("from_address")),
        "sms": bool(s.twilio_account_sid and s.twilio_auth_token and sms_cfg.get("number")),
    }


def alerts_off(channels: dict[str, Any]) -> bool:
    return not (channels["push_devices"] or channels["email"] or channels["sms"])
