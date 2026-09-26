"""Plans, the trial, metered usage and the billing state machine.

Why one module: a tenant's `status` decides whether the worker runs (the job picker only
takes `active` and `trial` tenants). Everything that moves that status for money reasons
lives here, behind `apply_event`, so the demo provider and a real Stripe webhook take the
same path and the tests cover both at once. See ADR 0014.

Stripe is spoken to over plain HTTPS (form-encoded, as its API expects) rather than
through its SDK: three calls do not justify a dependency in the serverless bundle.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novaxis_core.models import AuditLog, BillingEvent, Job, Message, Tenant, UsageEvent
from novaxis_core.settings import get_settings

REPORT_USAGE_KIND = "billing.report_usage"
STRIPE_TOLERANCE_SECONDS = 300


def provider() -> Literal["stripe", "demo"]:
    s = get_settings()
    return "stripe" if s.stripe_secret_key and s.stripe_webhook_secret else "demo"


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    setup_pence: int
    monthly_pence: int
    included_messages: int
    overage_pence: int
    note: str


def plans() -> dict[str, Plan]:
    s = get_settings()
    common = {
        "monthly_pence": s.price_monthly_pence,
        "included_messages": s.included_messages,
        "overage_pence": s.overage_pence_per_message,
    }
    return {
        "pilot": Plan(
            id="pilot",
            name="Pilot",
            setup_pence=0,
            note="Setup fee waived. 60 days, three success numbers agreed up front.",
            **common,
        ),
        "standard": Plan(
            id="standard",
            name="Standard",
            setup_pence=s.price_setup_pence,
            note="Setup covers configuration, channels, calendar and two weeks of tuning.",
            **common,
        ),
    }


@dataclass(frozen=True)
class Usage:
    ai_replies: int
    tokens: int


def usage_between(session: Session, tenant_id: uuid.UUID, start: datetime, end: datetime) -> Usage:
    """AI replies are the billed unit: outbound messages the worker wrote. Tokens are shown
    for cost awareness only."""
    replies = session.scalar(
        select(func.count(Message.id)).where(
            Message.tenant_id == tenant_id,
            Message.direction == "outbound",
            Message.author == "worker",
            Message.created_at >= start,
            Message.created_at < end,
        )
    )
    tokens = session.scalar(
        select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.unit == "tokens",
            UsageEvent.created_at >= start,
            UsageEvent.created_at < end,
        )
    )
    return Usage(ai_replies=int(replies or 0), tokens=int(tokens or 0))


def month_start(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def start_trial(tenant: Tenant, now: datetime) -> None:
    """A new tenant: full features, ends by date or by reply cap, whichever comes first."""
    tenant.status = "trial"
    tenant.plan = "trial"
    tenant.trial_ends_at = now + timedelta(days=get_settings().trial_days)


def trial_block_reason(session: Session, tenant: Tenant, now: datetime) -> str | None:
    """Why the worker may not reply for this tenant right now, or None if it may."""
    if tenant.status != "trial":
        return None
    if tenant.trial_ends_at is not None and now >= tenant.trial_ends_at:
        return "trial_expired"
    used = usage_between(session, tenant.id, tenant.created_at, now).ai_replies
    if used >= get_settings().trial_message_cap:
        return "trial_cap_reached"
    return None


def summary(session: Session, tenant: Tenant, now: datetime) -> dict[str, Any]:
    """Everything the billing page shows."""
    s = get_settings()
    period_start = month_start(now)
    period = usage_between(session, tenant.id, period_start, now)
    plan = plans().get(tenant.plan)
    over = max(0, period.ai_replies - plan.included_messages) if plan else 0
    trial: dict[str, Any] | None = None
    if tenant.status == "trial":
        used = usage_between(session, tenant.id, tenant.created_at, now).ai_replies
        ends = tenant.trial_ends_at
        trial = {
            "ends_at": ends.isoformat() if ends else None,
            "days_left": max(0, (ends - now).days) if ends else None,
            "replies_used": used,
            "reply_cap": s.trial_message_cap,
            "blocked": trial_block_reason(session, tenant, now),
        }
    return {
        "provider": provider(),
        "status": tenant.status,
        "plan": tenant.plan,
        "subscribed": tenant.billing_subscription_ref is not None,
        "trial": trial,
        "period": {
            "start": period_start.isoformat(),
            "ai_replies": period.ai_replies,
            "tokens": period.tokens,
            "included": plan.included_messages if plan else None,
            "overage_replies": over,
            "overage_pence": over * plan.overage_pence if plan else 0,
        },
        "plans": [asdict(p) for p in plans().values()],
        "prices_are_placeholders": True,
    }


# --- The state machine -------------------------------------------------------------------


def _find_tenant(session: Session, obj: dict[str, Any]) -> Tenant | None:
    meta = obj.get("metadata") or {}
    for raw in (meta.get("tenant_id"), obj.get("client_reference_id")):
        if raw:
            try:
                t = session.get(Tenant, uuid.UUID(str(raw)))
            except ValueError:
                t = None
            if t is not None:
                return t
    customer = obj.get("customer")
    if isinstance(customer, str) and customer:
        return session.scalar(select(Tenant).where(Tenant.billing_customer_ref == customer))
    return None


def _checkout_completed(tenant: Tenant, obj: dict[str, Any]) -> str:
    plan_id = str((obj.get("metadata") or {}).get("plan") or "standard")
    if plan_id not in plans():
        plan_id = "standard"
    tenant.plan = plan_id
    tenant.status = "active"
    if obj.get("customer"):
        tenant.billing_customer_ref = str(obj["customer"])
    if obj.get("subscription"):
        tenant.billing_subscription_ref = str(obj["subscription"])
    return f"activated on {plan_id}"


def _payment_failed(tenant: Tenant, obj: dict[str, Any]) -> str:
    if tenant.status in ("active", "trial"):
        tenant.status = "paused"
        return "paused: payment failed"
    return "no change"


def _invoice_paid(tenant: Tenant, obj: dict[str, Any]) -> str:
    # `paused` is only ever set by billing (the owner's switch is worker_enabled), so a paid
    # invoice safely lifts it. A closed tenant stays closed.
    if tenant.status == "paused":
        tenant.status = "active"
        return "resumed: invoice paid"
    return "no change"


def _subscription_deleted(tenant: Tenant, obj: dict[str, Any]) -> str:
    tenant.status = "closed"
    return "closed: subscription cancelled"


HANDLERS = {
    "checkout.session.completed": _checkout_completed,
    "invoice.payment_failed": _payment_failed,
    "invoice.paid": _invoice_paid,
    "customer.subscription.deleted": _subscription_deleted,
}


def apply_event(session: Session, event: dict[str, Any], source: str) -> str:
    """Apply one billing event exactly once. Needs a service session: the event log is
    service-only and the tenant is found by customer id across all tenants."""
    event_id = str(event.get("id") or "")
    kind = str(event.get("type") or "")
    if not event_id or not kind:
        raise ValueError("billing event needs an id and a type")
    if session.get(BillingEvent, event_id) is not None:
        return "duplicate"
    obj = (event.get("data") or {}).get("object") or {}
    handler = HANDLERS.get(kind)
    tenant = _find_tenant(session, obj) if handler else None
    if handler is None:
        outcome = "ignored"
    elif tenant is None:
        outcome = "no matching tenant"
    else:
        before = tenant.status
        outcome = handler(tenant, obj)
        session.add(
            AuditLog(
                tenant_id=tenant.id,
                actor=f"billing:{source}",
                event=f"billing.{kind}",
                subject_table="tenants",
                subject_id=tenant.id,
                diff={"status": [before, tenant.status], "outcome": outcome, "event": event_id},
            )
        )
    session.add(
        BillingEvent(
            id=event_id,
            provider=source,
            type=kind,
            tenant_id=tenant.id if tenant else None,
            outcome=outcome,
            payload={"object_id": obj.get("id"), "customer": obj.get("customer")},
        )
    )
    session.flush()
    return outcome


def demo_event(tenant: Tenant, kind: str, plan_id: str = "standard") -> dict[str, Any]:
    """The event Stripe would send, for the demo provider. Same handler, no money."""
    obj: dict[str, Any] = {
        "id": f"demo_obj_{uuid.uuid4().hex[:12]}",
        "customer": tenant.billing_customer_ref or f"demo_cus_{tenant.id.hex[:12]}",
        "metadata": {"tenant_id": str(tenant.id), "plan": plan_id},
    }
    if kind == "checkout.session.completed":
        obj["client_reference_id"] = str(tenant.id)
        obj["subscription"] = f"demo_sub_{tenant.id.hex[:12]}"
    return {"id": f"demo_evt_{uuid.uuid4().hex}", "type": kind, "data": {"object": obj}}


# --- Stripe over HTTPS -------------------------------------------------------------------


def verify_stripe_signature(
    payload: bytes, header: str, secret: str, now: float, tolerance: int = STRIPE_TOLERANCE_SECONDS
) -> bool:
    """Stripe signs `{timestamp}.{raw body}` with HMAC-SHA256 and sends `t=...,v1=...`."""
    pairs = [p.split("=", 1) for p in header.split(",") if "=" in p]
    stamp = next((v for k, v in pairs if k.strip() == "t"), None)
    sigs = [v for k, v in pairs if k.strip() == "v1"]
    if stamp is None or not sigs:
        return False
    try:
        t = int(stamp)
    except ValueError:
        return False
    if abs(now - t) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s.strip()) for s in sigs)


class StripeClient:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        s = get_settings()
        self._client = httpx.Client(
            base_url=s.stripe_api_base,
            auth=(s.stripe_secret_key, ""),
            timeout=15.0,
            transport=transport,
        )

    def _post(self, path: str, data: dict[str, str]) -> dict[str, Any]:
        r = self._client.post(path, data=data)
        if r.status_code >= 400:
            raise RuntimeError(f"stripe {path}: {r.status_code} {r.text[:300]}")
        out: dict[str, Any] = r.json()
        return out

    def checkout_url(self, tenant: Tenant, plan_id: str, success_url: str, cancel_url: str) -> str:
        prices = get_settings().stripe_prices.get(plan_id) or {}
        if not prices.get("monthly"):
            raise ValueError(f"no Stripe price configured for plan {plan_id!r}")
        data = {
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(tenant.id),
            "metadata[tenant_id]": str(tenant.id),
            "metadata[plan]": plan_id,
            "subscription_data[metadata][tenant_id]": str(tenant.id),
            "line_items[0][price]": prices["monthly"],
            "line_items[0][quantity]": "1",
        }
        i = 1
        if prices.get("setup") and plans()[plan_id].setup_pence > 0:
            data[f"line_items[{i}][price]"] = prices["setup"]
            data[f"line_items[{i}][quantity]"] = "1"
            i += 1
        if prices.get("metered"):
            data[f"line_items[{i}][price]"] = prices["metered"]
        if tenant.billing_customer_ref:
            data["customer"] = tenant.billing_customer_ref
        return str(self._post("/v1/checkout/sessions", data)["url"])

    def report_usage(self, customer: str, value: int, identifier: str, timestamp: int) -> None:
        self._post(
            "/v1/billing/meter_events",
            {
                "event_name": get_settings().stripe_meter_event_name,
                "payload[stripe_customer_id]": customer,
                "payload[value]": str(value),
                "identifier": identifier,
                "timestamp": str(timestamp),
            },
        )


def report_daily_usage(session: Session, tenant: Tenant, client: StripeClient, day: date) -> int:
    """Send one UTC day's AI replies to Stripe's meter. The identifier makes a retry of the
    same day a no-op on Stripe's side."""
    start = datetime.combine(day, time(), UTC)
    end = start + timedelta(days=1)
    n = usage_between(session, tenant.id, start, end).ai_replies
    if n and tenant.billing_customer_ref:
        client.report_usage(
            tenant.billing_customer_ref,
            n,
            identifier=f"{tenant.id}:{day.isoformat()}",
            timestamp=int(end.timestamp()) - 1,
        )
    return n


def enqueue_usage_reports(session: Session, now: datetime) -> int:
    """Called by the worker's timer with a service session: yesterday's usage, once per
    paying tenant. Does nothing under the demo provider."""
    if provider() != "stripe":
        return 0
    day = (now - timedelta(days=1)).date().isoformat()
    n = 0
    for tenant_id in session.scalars(
        select(Tenant.id).where(
            Tenant.status.in_(["active", "paused"]), Tenant.billing_customer_ref.is_not(None)
        )
    ):
        exists = session.scalar(
            select(Job.id)
            .where(
                Job.tenant_id == tenant_id,
                Job.kind == REPORT_USAGE_KIND,
                Job.payload["day"].astext == day,
            )
            .limit(1)
        )
        if exists is None:
            session.add(Job(tenant_id=tenant_id, kind=REPORT_USAGE_KIND, payload={"day": day}))
            n += 1
    session.flush()
    return n
