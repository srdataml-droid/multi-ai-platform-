"""Billing: the owner's view, checkout, and the Stripe webhook.

With no Stripe keys configured the provider is "demo": checkout applies the same
`checkout.session.completed` event a real payment would, through the same handler, and no
money moves. The webhook route exists only when Stripe is configured.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.billing import (
    StripeClient,
    apply_event,
    demo_event,
    plans,
    provider,
    summary,
    verify_stripe_signature,
)
from novaxis_core.models import Tenant
from novaxis_core.settings import get_settings
from novaxis_db.session import service_session

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("")
def read(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    t = session.scalar(select(Tenant))
    assert t is not None
    return summary(session, t, datetime.now(UTC))


class CheckoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str


@router.post("/checkout")
def checkout(body: CheckoutIn, principal: CurrentPrincipal) -> dict[str, Any]:
    if principal.role not in ("owner", "operator"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can manage billing")
    if body.plan not in plans():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown plan")
    # A service session: the demo path writes the service-only event log, like a webhook.
    with service_session() as session:
        t = session.get(Tenant, principal.tenant_id)
        assert t is not None
        if t.status == "closed":
            raise HTTPException(status.HTTP_409_CONFLICT, "this account is closed")
        if provider() == "demo":
            outcome = apply_event(
                session, demo_event(t, "checkout.session.completed", body.plan), "demo"
            )
            return {"url": None, "outcome": outcome}
        web = get_settings().public_web_url
        try:
            url = StripeClient().checkout_url(
                t, body.plan, f"{web}/billing?paid=1", f"{web}/billing"
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        return {"url": url, "outcome": "redirect"}


@router.post("/webhook")
async def webhook(
    request: Request, stripe_signature: str | None = Header(default=None)
) -> dict[str, str]:
    if provider() != "stripe":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not available")
    payload = await request.body()
    if not stripe_signature or not verify_stripe_signature(
        payload, stripe_signature, get_settings().stripe_webhook_secret, time.time()
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad signature")
    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "not json") from exc
    with service_session() as session:
        return {"outcome": apply_event(session, event, "stripe")}
