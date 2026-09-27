"""Staff alerts from the dashboard: turn browser push on or off for this device, send a test,
and see which ways of reaching the team actually work."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.alerts import ALERT_ROLES, alert_channels, alert_staff, alerts_off
from novaxis_core.models import AuditLog, PushSubscription, Tenant
from novaxis_core.settings import get_settings

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _tenant(session: TenantDb) -> Tenant:
    t = session.scalar(select(Tenant))
    assert t is not None
    return t


@router.get("")
def read(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    channels = alert_channels(session, _tenant(session))
    mine = session.scalar(
        select(PushSubscription.id).where(PushSubscription.user_id == principal.user_id).limit(1)
    )
    return {
        "public_key": get_settings().vapid_public_key or None,
        "channels": channels,
        "alerts_off": alerts_off(channels),
        "this_user_subscribed": mine is not None,
        "can_subscribe": principal.role in ALERT_ROLES,
    }


class Keys(BaseModel):
    model_config = ConfigDict(extra="ignore")
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscriptionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    endpoint: str = Field(pattern=r"^https://", max_length=2000)
    keys: Keys


@router.post("/subscriptions")
def subscribe(
    body: SubscriptionIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    if principal.role not in ALERT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only owners and staff receive alerts")
    sub = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
        )
        session.add(sub)
    else:
        sub.user_id, sub.p256dh, sub.auth = principal.user_id, body.keys.p256dh, body.keys.auth
    try:
        session.flush()
    except IntegrityError as exc:  # this browser is subscribed for another business
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this device gets another team's alerts"
        ) from exc
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="alerts.subscribed",
            subject_table="push_subscriptions",
            subject_id=sub.id,
            diff={},
        )
    )
    return read(principal, session)


class Unsubscribe(BaseModel):
    model_config = ConfigDict(extra="ignore")
    endpoint: str


@router.post("/subscriptions/remove")
def unsubscribe(
    body: Unsubscribe, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    sub = session.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == principal.user_id,
        )
    )
    if sub is not None:
        session.delete(sub)
        session.flush()
    return read(principal, session)


@router.post("/test")
def test_alert(principal: CurrentPrincipal, session: TenantDb) -> dict[str, int]:
    n = alert_staff(
        session,
        _tenant(session),
        "Alerts are working",
        "This device will be told when a customer needs your team.",
        "/settings",
        only_user=principal.user_id,
    )
    if n == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "no device of yours accepted the alert")
    return {"delivered": n}
