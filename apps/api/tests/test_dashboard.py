from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.models import Conversation, Message, Tenant, User
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session


@pytest.fixture
def client(migrated: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("NOVAXIS_LLM_PROVIDER", "fake")
    get_settings.cache_clear()
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
    yield TestClient(create_app())
    get_settings.cache_clear()


def _h(sub: str = "dev|owner@demo-hvac") -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(sub)}"}


def _conv(body: str = "hello") -> uuid.UUID:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        return ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref="demo-hvac",
                sender_visitor_id=v,
                body=body,
            ),
        ).conversation_id


def test_inbox_and_queue_list_conversations_with_pack_columns(client: TestClient) -> None:
    conv_id = _conv("no heating")
    inbox = client.get("/inbox", headers=_h()).json()
    assert [c["key"] for c in inbox["columns"]][:2] == ["name", "problem_type"]
    row = next(i for i in inbox["items"] if i["id"] == str(conv_id))
    assert (
        row["bucket"] == "new"
        and row["unread"] == 1
        and row["last_message"]["body"] == "no heating"
    )
    q = client.get("/work-queue", headers=_h()).json()
    assert any(
        b["key"] == "new" and any(i["id"] == str(conv_id) for i in b["items"]) for b in q["buckets"]
    )


def test_takeover_send_handback_and_suggest(client: TestClient) -> None:
    conv_id = _conv()
    assert (
        client.post(f"/conversations/{conv_id}/takeover", headers=_h()).json()["status"]
        == "waiting_human"
    )
    r = client.post(
        f"/conversations/{conv_id}/messages",
        json={"body": "Hi, this is Sam from the office"},
        headers=_h(),
    )
    assert r.status_code == 200
    with service_session() as s:
        m = s.get(Message, uuid.UUID(r.json()["message_id"]))
        assert m is not None and m.author == "human" and m.direction == "outbound"
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.owner_user_id is not None and conv.takeover_at is not None
    sug = client.post(f"/conversations/{conv_id}/suggest", headers=_h()).json()
    assert sug["suggestion"]
    assert (
        client.post(f"/conversations/{conv_id}/handback", headers=_h()).json()["status"]
        == "waiting_customer"
    )
    assert client.post(f"/conversations/{conv_id}/close", headers=_h()).json()["status"] == "closed"


def test_viewer_is_read_only(client: TestClient) -> None:
    conv_id = _conv()
    v = _h("dev|viewer@demo-hvac")
    assert client.get("/inbox", headers=v).status_code == 200
    assert client.post(f"/conversations/{conv_id}/takeover", headers=v).status_code == 403
    assert (
        client.post(f"/conversations/{conv_id}/messages", json={"body": "x"}, headers=v).status_code
        == 403
    )
    assert client.put("/settings", json={"name": "Nope"}, headers=v).status_code == 403
    contacts = client.get("/contacts", headers=v).json()["items"]
    assert all(p.endswith("...") for c in contacts for p in c["phones"])


def test_settings_roundtrip_and_floor_enforced(client: TestClient) -> None:
    cur = client.get("/settings", headers=_h()).json()
    settings = cur["settings"]
    settings["risk_overrides"] = {"propose_appointment": "low"}
    r = client.put("/settings", json={"settings": settings}, headers=_h())
    assert r.status_code == 200 and r.json()["settings"]["risk_overrides"] == {
        "propose_appointment": "low"
    }
    settings["risk_overrides"] = {"collect_payment": "low"}
    r = client.put("/settings", json={"settings": settings}, headers=_h())
    assert r.status_code == 422 and "cannot go below" in r.json()["detail"]
    settings["risk_overrides"] = {}
    settings["business_hours"]["funday"] = {"open": "09:00", "close": "17:00"}
    assert client.put("/settings", json={"settings": settings}, headers=_h()).status_code == 422
    assert "propose_appointment" in cur["risk_floors"]


def test_staff_add_and_role_change(client: TestClient) -> None:
    email = f"new-{uuid.uuid4().hex[:6]}@demo-hvac.test"
    r = client.post("/settings/staff", json={"email": email, "role": "staff"}, headers=_h())
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert (
        client.post(
            "/settings/staff", json={"email": email, "role": "staff"}, headers=_h()
        ).status_code
        == 409
    )
    assert (
        client.put(f"/settings/staff/{uid}", json={"role": "viewer"}, headers=_h()).json()["role"]
        == "viewer"
    )
    # First login binds the email-registered row to the provider subject.
    import jwt as pyjwt

    from novaxis_core.settings import get_settings as gs

    tok = pyjwt.encode(
        {"sub": "supabase-uuid-123", "aud": "authenticated", "email": email},
        gs().jwt_secret,
        algorithm="HS256",
    )
    me = client.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["role"] == "viewer"


def test_dev_login_widget_and_analytics(client: TestClient) -> None:
    r = client.post("/auth/dev-login", json={"email": "owner@demo-hvac.test"})
    assert r.status_code == 200 and r.json()["role"] == "owner"
    assert client.get("/auth/config").json()["mode"] == "dev"
    w = client.get("/settings/widget", headers=_h()).json()
    assert 'data-tenant="demo-hvac"' in w["snippet"] and "widget.js" in w["snippet"]
    a = client.get("/analytics", headers=_h()).json()
    assert set(a["totals"]) >= {"inbound", "bookings_approved"}
