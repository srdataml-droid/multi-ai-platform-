"""The billing state machine against real rows, driven by recorded Stripe event fixtures,
plus the trial gate and usage metering."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from novaxis_core.billing import (
    REPORT_USAGE_KIND,
    StripeClient,
    apply_event,
    demo_event,
    enqueue_usage_reports,
    report_daily_usage,
    start_trial,
    summary,
    trial_block_reason,
    usage_between,
)
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM
from novaxis_core.models import AuditLog, BillingEvent, Conversation, Job, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.tenant_settings import ChannelConfig, TenantSettings
from novaxis_core.turn import run_turn
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

FIXTURES = Path(__file__).parent / "fixtures" / "stripe"


def _event(name: str, tenant_id: uuid.UUID, customer: str) -> dict[str, Any]:
    """A recorded Stripe event, made unique for this test (event id and customer)."""
    raw = (FIXTURES / f"{name}.json").read_text()
    raw = raw.replace("{{TENANT_ID}}", str(tenant_id)).replace("cus_Fixture123", customer)
    ev: dict[str, Any] = json.loads(raw)
    ev["id"] = f"{ev['id']}_{uuid.uuid4().hex[:8]}"
    return ev


@pytest.fixture
def trial_tenant(migrated: str) -> uuid.UUID:
    with service_session(migrated) as s:
        settings = TenantSettings(
            pack_id="hvac", channels={"webchat": ChannelConfig(enabled=True)}
        ).model_dump()
        t = Tenant(
            name="Trial Co",
            slug=f"trial-{uuid.uuid4().hex[:8]}",
            pack_id="hvac",
            settings=settings,
        )
        start_trial(t, datetime.now(UTC))
        s.add(t)
        s.flush()
        return t.id


def _status(tid: uuid.UUID) -> str:
    with service_session() as s:
        t = s.get(Tenant, tid)
        assert t is not None
        return t.status


def test_stripe_fixtures_walk_the_tenant_through_its_lifecycle(trial_tenant: uuid.UUID) -> None:
    cus = f"cus_{uuid.uuid4().hex[:10]}"
    steps = [
        ("checkout_session_completed", "activated on pilot", "active"),
        ("invoice_payment_failed", "paused: payment failed", "paused"),
        ("invoice_paid", "resumed: invoice paid", "active"),
        ("invoice_paid", "no change", "active"),
        ("customer_subscription_deleted", "closed: subscription cancelled", "closed"),
        ("invoice_paid", "no change", "closed"),
    ]
    for name, outcome, status in steps:
        with service_session() as s:
            assert apply_event(s, _event(name, trial_tenant, cus), "stripe") == outcome, name
        assert _status(trial_tenant) == status, name
    with service_session() as s:
        t = s.get(Tenant, trial_tenant)
        assert t is not None
        assert t.plan == "pilot"
        assert t.billing_customer_ref == cus
        assert t.billing_subscription_ref == "sub_Fixture123"
        audits = list(
            s.scalars(
                select(AuditLog)
                .where(AuditLog.tenant_id == trial_tenant, AuditLog.event.like("billing.%"))
                .order_by(AuditLog.created_at)
            )
        )
        assert [a.diff["status"] for a in audits] == [
            ["trial", "active"],
            ["active", "paused"],
            ["paused", "active"],
            ["active", "active"],
            ["active", "closed"],
            ["closed", "closed"],
        ]
        assert all(a.actor == "billing:stripe" for a in audits)


def test_a_replayed_event_is_a_no_op(trial_tenant: uuid.UUID) -> None:
    cus = f"cus_{uuid.uuid4().hex[:10]}"
    with service_session() as s:
        apply_event(s, _event("checkout_session_completed", trial_tenant, cus), "stripe")
    failed = _event("invoice_payment_failed", trial_tenant, cus)
    with service_session() as s:
        assert apply_event(s, failed, "stripe") == "paused: payment failed"
    with service_session() as s:
        t = s.get(Tenant, trial_tenant)
        assert t is not None
        t.status = "active"  # someone fixes it by hand; the replay must not undo that
    with service_session() as s:
        assert apply_event(s, failed, "stripe") == "duplicate"
        assert s.scalar(select(func.count()).where(BillingEvent.id == failed["id"])) == 1
    assert _status(trial_tenant) == "active"


def test_unknown_types_and_unknown_customers_are_logged_not_applied(migrated: str) -> None:
    with service_session(migrated) as s:
        ev = {"id": f"evt_{uuid.uuid4().hex}", "type": "charge.refunded", "data": {"object": {}}}
        assert apply_event(s, ev, "stripe") == "ignored"
        orphan = _event("invoice_payment_failed", uuid.uuid4(), f"cus_{uuid.uuid4().hex[:10]}")
        assert apply_event(s, orphan, "stripe") == "no matching tenant"
        row = s.get(BillingEvent, orphan["id"])
        assert row is not None and row.tenant_id is None


def test_a_paused_tenant_gets_no_worker(trial_tenant: uuid.UUID) -> None:
    from novaxis_worker.loop import pick_one

    with service_session() as s:
        s.add(Job(tenant_id=trial_tenant, kind="noop", payload={}))
        apply_event(s, demo_event(s.get(Tenant, trial_tenant), "invoice.payment_failed"), "demo")  # type: ignore[arg-type]
    with service_session() as s:
        while (p := pick_one(s, "test")) is not None:
            assert p.tenant_id != trial_tenant, "picked a job for a paused tenant"
            s.execute(Job.__table__.update().where(Job.id == p.job_id).values(state="done"))
    with service_session() as s:
        queued = s.scalar(
            select(func.count()).where(Job.tenant_id == trial_tenant, Job.state == "queued")
        )
        assert queued == 1


def _conversation(tid: uuid.UUID, body: str) -> uuid.UUID:
    with tenant_session(tid) as s:
        t = s.get(Tenant, tid)
        assert t is not None
        visitor = uuid.uuid4().hex[:12]
        return ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{visitor}:{uuid.uuid4().hex[:8]}",
                tenant_ref=t.slug,
                sender_visitor_id=visitor,
                body=body,
            ),
        ).conversation_id


def _worker_replies(
    s: Any, tid: uuid.UUID, n: int, conv_id: uuid.UUID, at: datetime | None = None
) -> None:
    for i in range(n):
        m = Message(
            tenant_id=tid,
            conversation_id=conv_id,
            direction="outbound",
            channel="webchat",
            author="worker",
            body=f"reply {i}",
        )
        if at is not None:
            m.created_at = at
        s.add(m)


def test_trial_ends_by_date_or_by_reply_cap(trial_tenant: uuid.UUID) -> None:
    now = datetime.now(UTC)
    cap = get_settings().trial_message_cap
    conv = _conversation(trial_tenant, "hello")
    with tenant_session(trial_tenant) as s:
        t = s.get(Tenant, trial_tenant)
        assert t is not None
        assert trial_block_reason(s, t, now) is None
        assert trial_block_reason(s, t, now + timedelta(days=15)) == "trial_expired"
        _worker_replies(s, trial_tenant, cap, conv)
        s.flush()
        assert trial_block_reason(s, t, now + timedelta(seconds=1)) == "trial_cap_reached"
        t.status = "active"
        assert trial_block_reason(s, t, now + timedelta(days=30)) is None, "paid tenants run"


def test_blocked_turn_hands_over_without_the_model(trial_tenant: uuid.UUID) -> None:
    conv_id = _conversation(trial_tenant, "my radiator is cold")
    llm = FakeLLM(script=[("should not be used", [])])
    with tenant_session(trial_tenant) as s:
        t = s.get(Tenant, trial_tenant)
        assert t is not None
        r = run_turn(s, t, get_pack("hvac"), llm, conv_id, blocked_reason="trial_cap_reached")
    assert r.skipped_reason == "trial_cap_reached" and r.reply_message_id is None
    assert llm.calls == []
    with tenant_session(trial_tenant) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"
        assert (
            s.scalar(
                select(func.count()).where(
                    AuditLog.event == "billing.worker_blocked",
                    AuditLog.diff["conversation_id"].astext == str(conv_id),
                )
            )
            == 1
        )


def test_emergencies_still_get_the_safety_reply_when_blocked(trial_tenant: uuid.UUID) -> None:
    conv_id = _conversation(trial_tenant, "I can smell gas in the kitchen")
    llm = FakeLLM(script=[])
    with tenant_session(trial_tenant) as s:
        t = s.get(Tenant, trial_tenant)
        assert t is not None
        r = run_turn(s, t, get_pack("hvac"), llm, conv_id, blocked_reason="trial_expired")
    assert r.skipped_reason is None and r.reply_message_id is not None
    assert "escalate_emergency" in r.decisions
    assert llm.calls == []


def test_usage_and_summary_count_only_this_tenants_worker_replies(
    trial_tenant: uuid.UUID, migrated: str
) -> None:
    conv = _conversation(trial_tenant, "hello")
    with tenant_session(trial_tenant) as s:
        _worker_replies(s, trial_tenant, 3, conv)
        s.add(
            Message(
                tenant_id=trial_tenant,
                conversation_id=conv,
                direction="outbound",
                channel="webchat",
                author="human",
                body="staff reply, not billed",
            )
        )
    now = datetime.now(UTC) + timedelta(seconds=1)
    with tenant_session(trial_tenant) as s:
        t = s.get(Tenant, trial_tenant)
        assert t is not None
        assert usage_between(s, trial_tenant, now - timedelta(hours=1), now).ai_replies == 3
        out = summary(s, t, now)
    assert out["provider"] == "demo"
    assert out["trial"]["replies_used"] == 3
    assert out["trial"]["reply_cap"] == get_settings().trial_message_cap
    assert out["period"]["ai_replies"] == 3
    assert {p["id"] for p in out["plans"]} == {"pilot", "standard"}


def test_daily_usage_goes_to_the_stripe_meter_once_per_day(
    trial_tenant: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVAXIS_STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("NOVAXIS_STRIPE_WEBHOOK_SECRET", "whsec_x")
    get_settings.cache_clear()
    cus = f"cus_{uuid.uuid4().hex[:10]}"
    try:
        with service_session() as s:
            apply_event(s, _event("checkout_session_completed", trial_tenant, cus), "stripe")
        conv = _conversation(trial_tenant, "hello")
        yesterday = datetime.now(UTC) - timedelta(days=1)
        with tenant_session(trial_tenant) as s:
            _worker_replies(s, trial_tenant, 4, conv, at=yesterday)
        with service_session() as s:
            assert enqueue_usage_reports(s, datetime.now(UTC)) >= 1
        with service_session() as s:
            enqueue_usage_reports(s, datetime.now(UTC))
            jobs = s.scalar(
                select(func.count()).where(
                    Job.tenant_id == trial_tenant, Job.kind == REPORT_USAGE_KIND
                )
            )
            assert jobs == 1, "one report job per tenant per day"
        sent: list[dict[str, str]] = []

        def handle(req: httpx.Request) -> httpx.Response:
            from urllib.parse import parse_qs

            sent.append({k: v[0] for k, v in parse_qs(req.content.decode()).items()})
            return httpx.Response(200, json={"object": "billing.meter_event"})

        with tenant_session(trial_tenant) as s:
            t = s.get(Tenant, trial_tenant)
            assert t is not None
            client = StripeClient(transport=httpx.MockTransport(handle))
            n = report_daily_usage(s, t, client, yesterday.date())
        assert n == 4
        assert sent == [
            {
                "event_name": "novaxis_ai_replies",
                "payload[stripe_customer_id]": cus,
                "payload[value]": "4",
                "identifier": f"{trial_tenant}:{yesterday.date().isoformat()}",
                "timestamp": sent[0]["timestamp"],
            }
        ]
        assert datetime.fromtimestamp(int(sent[0]["timestamp"]), UTC).date() == yesterday.date()
    finally:
        get_settings.cache_clear()


def test_demo_provider_never_enqueues_usage_reports(migrated: str) -> None:
    with service_session(migrated) as s:
        assert enqueue_usage_reports(s, datetime.now(UTC)) == 0
