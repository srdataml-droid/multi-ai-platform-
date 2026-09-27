"""Chunk 10 end to end through the API: sign up, onboard, pay, and the operator console."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.models import AuditLog, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.tenant_settings import TenantSettings
from novaxis_db.seed import seed
from novaxis_db.session import service_session

OPERATOR = {"Authorization": f"Bearer {mint('dev|operator@novaxis-ops')}"}
HVAC_OWNER = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}


@pytest.fixture
def client(migrated: str) -> TestClient:
    with service_session(migrated) as s:
        seed(s)
    return TestClient(create_app())


@pytest.fixture
def env(migrated: str, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    with service_session(migrated) as s:
        seed(s)

    def set_env(**kv: str) -> TestClient:
        for k, v in kv.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        return TestClient(create_app())

    yield set_env
    get_settings.cache_clear()


def _signup(c: TestClient, pack: str = "hvac", **extra: str) -> dict[str, Any]:
    email = f"owner-{uuid.uuid4().hex[:8]}@newbiz.test"
    r = c.post(
        "/signup",
        json={"business_name": "New Biz Heating", "email": email, "pack_id": pack, **extra},
    )
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    body["headers"] = {"Authorization": f"Bearer {body['token']}"}
    body["email"] = email
    return body


def _answers(c: TestClient, h: dict[str, str]) -> dict[str, Any]:
    r = c.get("/onboarding", headers=h)
    assert r.status_code == 200, r.text
    w: dict[str, Any] = r.json()["wizard"]
    w["on_call"] = {"name": "Sam", "phone": "+447700900123", "email": None}
    return w


def test_signup_to_onboarded_without_touching_the_database(client: TestClient) -> None:
    opts = client.get("/signup/options").json()
    assert opts["mode"] == "dev"
    assert {"hvac", "dental", "restoration"} <= {p["id"] for p in opts["packs"]}

    new = _signup(client)
    h = new["headers"]
    me = client.get("/me", headers=h).json()
    assert me["role"] == "owner"
    assert me["tenant"]["status"] == "trial" and me["tenant"]["onboarded"] is False
    assert me["tenant"]["slug"].startswith("new-biz-heating")

    ob = client.get("/onboarding", headers=h).json()
    assert ob["pack"]["id"] == "hvac" and ob["onboarded_at"] is None
    assert [s["code"] for s in ob["wizard"]["services"]][0] == "repair_visit"

    answers = _answers(client, h)
    answers["business_name"] = "New Biz Heating Ltd"
    answers["sms_number"] = "+447700900777"
    r = client.post("/onboarding", headers=h, json=answers)
    assert r.status_code == 200, r.text
    assert r.json()["onboarded_at"] is not None
    assert r.json()["wizard"]["sms_number"] == "+447700900777"

    me = client.get("/me", headers=h).json()
    assert me["tenant"]["onboarded"] is True and me["tenant"]["name"] == "New Biz Heating Ltd"
    with service_session() as s:
        t = s.get(Tenant, uuid.UUID(new["tenant_id"]))
        assert t is not None and t.trial_ends_at is not None
        TenantSettings.model_validate(t.settings)
        events = list(s.scalars(select(AuditLog.event).where(AuditLog.tenant_id == t.id)))
    assert "tenant.created" in events and "tenant.onboarded" in events

    # Coming back to the wizard later edits, it does not re-onboard.
    again = client.post("/onboarding", headers=h, json=answers)
    assert again.status_code == 200
    with service_session() as s:
        assert "onboarding.updated" in set(
            s.scalars(
                select(AuditLog.event).where(AuditLog.tenant_id == uuid.UUID(new["tenant_id"]))
            )
        )


def test_a_new_business_cannot_take_another_business_number_or_address(
    client: TestClient,
) -> None:
    new = _signup(client)
    h = new["headers"]
    answers = _answers(client, h)
    answers["sms_number"] = "+15005550006"  # demo-hvac's
    r = client.post("/onboarding", headers=h, json=answers)
    assert r.status_code == 409 and "another business" in r.json()["detail"]
    own = f"+4477009{uuid.uuid4().int % 100000:05d}"
    answers["sms_number"] = own
    assert client.post("/onboarding", headers=h, json=answers).status_code == 200

    # Settings can't be used to rewrite the routing addresses either.
    st = client.get("/settings", headers=h).json()["settings"]
    st["channels"]["twilio_sms"]["config"]["number"] = "+15005550006"
    st["channels"]["email"]["config"]["inbound_address"] = "demo-hvac@inbound.novaxis.test"
    st["tone"] = "warm"
    assert client.put("/settings", headers=h, json={"settings": st}).status_code == 200
    with service_session() as s:
        t = s.get(Tenant, uuid.UUID(new["tenant_id"]))
        assert t is not None
        assert t.settings["tone"] == "warm", "other settings still save"
        assert t.settings["channels"]["twilio_sms"]["config"]["number"] == own
        assert "inbound_address" not in t.settings["channels"]["email"]["config"]
        tid = t.id

    # The operator may reassign numbers, but still never onto another business's.
    acting = {"Authorization": f"Bearer {mint('dev|operator@novaxis-ops', act_tenant=str(tid))}"}
    r = client.put("/settings", headers=acting, json={"settings": st})
    assert r.status_code == 409 and "another business" in r.json()["detail"]


def test_onboarding_errors_are_readable_and_owner_only(client: TestClient) -> None:
    h = _signup(client)["headers"]
    bad = _answers(client, h)
    bad["on_call"] = {"name": "Sam", "phone": None, "email": None}
    r = client.post("/onboarding", headers=h, json=bad)
    assert r.status_code == 422
    assert (
        r.json()["detail"]
        == "on_call: the on-call contact needs a phone number or an email address"
    )
    viewer = {"Authorization": f"Bearer {mint('dev|viewer@demo-hvac')}"}
    assert client.post("/onboarding", headers=viewer, json=bad).status_code == 403


def test_signup_refuses_duplicates_unknown_packs_and_a_full_deployment(env) -> None:  # type: ignore[no-untyped-def]
    c = env()
    first = _signup(c)
    r = c.post(
        "/signup",
        json={"business_name": "Again", "email": first["email"], "pack_id": "hvac"},
    )
    assert r.status_code == 409
    r = c.post("/signup", json={"business_name": "X Co", "email": "x@x.test", "pack_id": "bakery"})
    assert r.status_code == 422
    c = env(NOVAXIS_SIGNUP_MAX_TENANTS="1")
    r = c.post(
        "/signup", json={"business_name": "Late Co", "email": "late@x.test", "pack_id": "hvac"}
    )
    assert r.status_code == 409 and "full" in r.json()["detail"]


def test_demo_signup_needs_the_passcode(env) -> None:  # type: ignore[no-untyped-def]
    c = env(NOVAXIS_ENV="production", NOVAXIS_DEMO_PASSCODE="open-sesame-123")
    body = {
        "business_name": "Demo Signup",
        "email": f"{uuid.uuid4().hex[:6]}@d.test",
        "pack_id": "dental",
    }
    assert c.post("/signup", json=body).status_code == 401
    assert c.post("/signup", json={**body, "passcode": "nope"}).status_code == 401
    ok = c.post("/signup", json={**body, "passcode": "open-sesame-123"})
    assert ok.status_code == 200 and ok.json()["token"]
    c = env(NOVAXIS_ENV="production", NOVAXIS_DEMO_PASSCODE="")
    assert c.post("/signup", json=body).status_code == 404


def test_demo_checkout_activates_through_the_event_handler(client: TestClient) -> None:
    new = _signup(client)
    h = new["headers"]
    b = client.get("/billing", headers=h).json()
    assert b["provider"] == "demo" and b["status"] == "trial" and b["trial"]["days_left"] >= 13
    r = client.post("/billing/checkout", headers=h, json={"plan": "pilot"})
    assert r.status_code == 200 and r.json() == {"url": None, "outcome": "activated on pilot"}
    b = client.get("/billing", headers=h).json()
    assert b["status"] == "active" and b["plan"] == "pilot" and b["subscribed"]
    assert b["trial"] is None
    viewer = {"Authorization": f"Bearer {mint('dev|viewer@demo-hvac')}"}
    assert (
        client.post("/billing/checkout", headers=viewer, json={"plan": "pilot"}).status_code == 403
    )
    assert client.post("/billing/checkout", headers=h, json={"plan": "gold"}).status_code == 422
    assert client.post("/billing/webhook", content=b"{}").status_code == 404, "demo: no webhook"


def _signed(payload: bytes, secret: str) -> dict[str, str]:
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"}


def test_stripe_webhook_verifies_and_applies(env) -> None:  # type: ignore[no-untyped-def]
    c = env()
    new = _signup(c)
    c = env(NOVAXIS_STRIPE_SECRET_KEY="sk_test_x", NOVAXIS_STRIPE_WEBHOOK_SECRET="whsec_abc")
    event = {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": new["tenant_id"],
                "customer": f"cus_{uuid.uuid4().hex[:8]}",
                "subscription": "sub_x",
                "metadata": {"plan": "standard"},
            }
        },
    }
    payload = json.dumps(event).encode()
    assert c.post("/billing/webhook", content=payload).status_code == 400, "unsigned"
    bad = c.post("/billing/webhook", content=payload, headers=_signed(payload, "whsec_wrong"))
    assert bad.status_code == 400
    ok = c.post("/billing/webhook", content=payload, headers=_signed(payload, "whsec_abc"))
    assert ok.status_code == 200 and ok.json()["outcome"] == "activated on standard"
    again = c.post("/billing/webhook", content=payload, headers=_signed(payload, "whsec_abc"))
    assert again.json()["outcome"] == "duplicate"
    me = c.get("/me", headers=new["headers"]).json()
    assert me["tenant"]["status"] == "active" and me["tenant"]["plan"] == "standard"


def test_operator_console_lists_enters_with_audit_and_simulates(client: TestClient) -> None:
    new = _signup(client)
    tid = new["tenant_id"]

    listing = client.get("/operator/tenants", headers=OPERATOR)
    assert listing.status_code == 200, listing.text
    rows = {r["id"]: r for r in listing.json()["items"]}
    assert tid in rows and rows[tid]["status"] == "trial"
    assert "onboarding not finished" in rows[tid]["problems"]
    assert all(r["slug"] != "novaxis-ops" for r in rows.values()), "internal tenant hidden"

    entered = client.post(f"/operator/tenants/{tid}/enter", headers=OPERATOR)
    assert entered.status_code == 200, entered.text
    act = {"Authorization": f"Bearer {entered.json()['token']}"}
    me = client.get("/me", headers=act).json()
    assert me["acting"] is True and me["role"] == "operator" and me["tenant"]["id"] == tid
    assert client.get("/settings", headers=act).status_code == 200
    with service_session() as s:
        audit = s.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == uuid.UUID(tid), AuditLog.event == "operator.entered"
            )
        )
        assert audit is not None
        assert audit.actor.startswith("operator:")
        assert audit.diff["operator_email"] == "operator@novaxis.test"

    # While acting inside a tenant the console itself is closed, and no one else gets in.
    assert client.get("/operator/tenants", headers=act).status_code == 403
    assert client.get("/operator/tenants", headers=HVAC_OWNER).status_code == 403
    assert client.post(f"/operator/tenants/{tid}/enter", headers=HVAC_OWNER).status_code == 403
    forged = mint("dev|owner@demo-hvac", act_tenant=tid)
    r = client.get("/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 403, "an owner cannot mint their way into another tenant"

    r = client.post(
        f"/operator/tenants/{tid}/billing-event",
        headers=OPERATOR,
        json={"event": "invoice.payment_failed"},
    )
    assert r.json() == {"outcome": "paused: payment failed"}
    rows = {r["id"]: r for r in client.get("/operator/tenants", headers=OPERATOR).json()["items"]}
    assert rows[tid]["status"] == "paused" and "billing: paused" in rows[tid]["problems"]
    with service_session() as s:
        ops_id = s.scalar(select(Tenant.id).where(Tenant.slug == "novaxis-ops"))
    assert client.post(f"/operator/tenants/{ops_id}/enter", headers=OPERATOR).status_code == 404


def test_wizard_time_zone_reaches_the_diary(client: TestClient) -> None:
    from novaxis_core.models import Location

    new = _signup(client)
    answers = _answers(client, new["headers"])
    answers["timezone"] = "America/New_York"
    assert client.post("/onboarding", headers=new["headers"], json=answers).status_code == 200
    with service_session() as s:
        tz = s.scalar(
            select(Location.timezone).where(Location.tenant_id == uuid.UUID(new["tenant_id"]))
        )
    assert tz == "America/New_York", "slots are computed in the location's zone"
