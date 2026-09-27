"""Staff record whether a customer came: the labels the no-show model learns from."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.models import Appointment, AuditLog, Contact, Conversation, Tenant, User
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session

OWNER = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}
VIEWER = {"Authorization": f"Bearer {mint('dev|viewer@demo-hvac')}"}


@pytest.fixture
def client(migrated: str) -> TestClient:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        if s.scalar(select(User).where(User.auth_subject == "dev|viewer@demo-hvac")) is None:
            s.add(
                User(
                    tenant_id=t.id,
                    auth_subject="dev|viewer@demo-hvac",
                    email="viewer@demo-hvac.test",
                    role="viewer",
                )
            )
    return TestClient(create_app())


def _appointment(hours_from_now: float, status: str = "confirmed") -> uuid.UUID:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        r = ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:x",
                tenant_ref=t.slug,
                sender_visitor_id=v,
                body="hi",
            ),
        )
        start = datetime.now(UTC) + timedelta(hours=hours_from_now)
        a = Appointment(
            tenant_id=t.id,
            contact_id=s.get(Conversation, r.conversation_id).contact_id,  # type: ignore[union-attr]
            conversation_id=r.conversation_id,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            service_code="repair_visit",
            status=status,
        )
        s.add(a)
        s.flush()
        return a.id


def test_staff_record_who_came_and_can_undo(client: TestClient) -> None:
    aid = _appointment(-3)
    url = f"/appointments/{aid}/outcome"
    assert client.post(url, json={"outcome": "no_show"}, headers=VIEWER).status_code == 403
    assert client.post(url, json={"outcome": "maybe"}, headers=OWNER).status_code == 422
    r = client.post(url, json={"outcome": "no_show"}, headers=OWNER)
    assert r.status_code == 200 and r.json()["outcome"] == "no_show"
    items = client.get("/appointments?back=1", headers=OWNER).json()["items"]
    assert next(i for i in items if i["id"] == str(aid))["outcome"] == "no_show"
    assert client.post(url, json={"outcome": None}, headers=OWNER).json()["outcome"] is None
    with service_session() as s:
        a = s.get(Appointment, aid)
        assert a is not None and a.outcome is None and a.outcome_at is None
        events = list(
            s.scalars(
                select(AuditLog.diff).where(
                    AuditLog.event == "appointment.outcome", AuditLog.subject_id == aid
                )
            )
        )
    assert len(events) == 2, "every change is audited"


def test_no_outcome_before_the_visit_or_for_unconfirmed_bookings(client: TestClient) -> None:
    future = _appointment(+24)
    r = client.post(f"/appointments/{future}/outcome", json={"outcome": "attended"}, headers=OWNER)
    assert r.status_code == 409
    held = _appointment(-3, status="held")
    r = client.post(f"/appointments/{held}/outcome", json={"outcome": "attended"}, headers=OWNER)
    assert r.status_code == 409


def test_upcoming_bookings_show_no_show_risk_but_the_demo_model_stays_with_demos(
    client: TestClient,
) -> None:
    from novaxis_core.no_show import load

    load.cache_clear()
    model = load()
    assert model is not None and model.synthetic, "the repo ships the synthetic demo model"
    upcoming = _appointment(+30)
    past = _appointment(-30)
    items = {i["id"]: i for i in client.get("/appointments?back=2", headers=OWNER).json()["items"]}
    risk = items[str(upcoming)]["risk"]
    assert risk is not None and 0 < risk["score"] < 1 and risk["level"] in ("low", "medium", "high")
    assert "synthetic" in risk["reasons"][-1], "a demo score says it is a demo"
    assert items[str(past)]["risk"] is None, "only upcoming bookings are scored"

    # A real business never sees a model trained on synthetic data.
    with service_session() as s:
        t = Tenant(
            name="Real Heating",
            slug=f"real-{uuid.uuid4().hex[:8]}",
            pack_id="hvac",
            status="active",
            settings={"pack_id": "hvac", "timezone": "Europe/London", "channels": {}},
        )
        s.add(t)
        s.flush()
        sub = f"dev|owner@{t.slug}"
        s.add(User(tenant_id=t.id, auth_subject=sub, email=f"o@{t.slug}.test", role="owner"))
        c = Contact(tenant_id=t.id, display_name="Real Customer")
        s.add(c)
        s.flush()
        start = datetime.now(UTC) + timedelta(days=2)
        s.add(
            Appointment(
                tenant_id=t.id,
                contact_id=c.id,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                service_code="repair_visit",
                status="confirmed",
            )
        )
    real = {"Authorization": f"Bearer {mint(sub)}"}
    items = client.get("/appointments", headers=real).json()["items"]
    assert items and all(i["risk"] is None for i in items)
