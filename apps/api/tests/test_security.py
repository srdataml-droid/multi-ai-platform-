"""The public doors: who the demo passcode opens, attempt limits, allowed widget websites,
and staying signed in."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.models import Tenant
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import service_session

PASS = "demo-pass-123"
OPS = "operator-pass-long-456"


@pytest.fixture
def env(migrated: str, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    with service_session(migrated) as s:
        seed(s)

    def make(**kv: str) -> TestClient:
        for k, v in kv.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        return TestClient(create_app())

    yield make
    get_settings.cache_clear()


def _prod(env, **extra: str) -> TestClient:  # type: ignore[no-untyped-def]
    return env(
        NOVAXIS_ENV="production",
        NOVAXIS_DEMO_PASSCODE=PASS,
        NOVAXIS_OPERATOR_PASSCODE=OPS,
        **extra,
    )


def _ip() -> dict[str, str]:
    return {"X-Forwarded-For": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"}


def _login(c: TestClient, email: str, code: str) -> int:
    return c.post(
        "/auth/dev-login", json={"email": email, "passcode": code}, headers=_ip()
    ).status_code


def test_demo_passcode_opens_demo_businesses_only(env) -> None:  # type: ignore[no-untyped-def]
    c = _prod(env)
    assert _login(c, "owner@demo-hvac.test", PASS) == 200
    assert _login(c, "operator@novaxis.test", PASS) == 401, "not the operator console"
    assert _login(c, "operator@novaxis.test", OPS) == 200
    signup = c.post(
        "/signup",
        json={
            "business_name": "Real Co",
            "email": f"{uuid.uuid4().hex[:8]}@real.test",
            "pack_id": "hvac",
            "passcode": PASS,
        },
        headers=_ip(),
    )
    assert signup.status_code == 200
    code = signup.json()["login_code"]
    assert code and len(code) == 10
    with service_session() as s:
        from novaxis_core.models import User

        u = s.scalar(select(User).where(User.tenant_id == uuid.UUID(signup.json()["tenant_id"])))
        assert u is not None
        email = u.email
    assert _login(c, email, PASS) == 401, "the shared passcode never opens a real sign-up"
    assert _login(c, email, code) == 200
    assert _login(c, email, code.lower()) == 200
    # Unknown email and wrong code look the same.
    r1 = c.post("/auth/dev-login", json={"email": "nobody@x.test", "passcode": PASS}, headers=_ip())
    r2 = c.post("/auth/dev-login", json={"email": email, "passcode": "WRONG"}, headers=_ip())
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_a_team_member_signs_in_with_their_own_code(env) -> None:  # type: ignore[no-untyped-def]
    """Hosted without an identity provider: each person the owner adds gets a code, shown
    once; a lost code is replaced and the old one stops working."""
    c = _prod(env)
    signup = c.post(
        "/signup",
        json={
            "business_name": "Team Co",
            "email": f"{uuid.uuid4().hex[:8]}@team.test",
            "pack_id": "hvac",
            "passcode": PASS,
        },
        headers=_ip(),
    ).json()
    owner = {"Authorization": f"Bearer {signup['token']}"}
    tech = f"tech-{uuid.uuid4().hex[:6]}@team.test"
    added = c.post("/settings/staff", json={"email": tech, "role": "staff"}, headers=owner)
    assert added.status_code == 200
    code = added.json()["login_code"]
    assert code and len(code) == 10
    assert _login(c, tech, PASS) == 401, "not the shared demo passcode"
    assert _login(c, tech, code) == 200
    listed = c.get("/settings/staff", headers=owner).json()["items"]
    assert all("login_code" not in u for u in listed), "shown once, never listed"
    fresh = c.post(f"/settings/staff/{added.json()['id']}/code", headers=owner)
    assert fresh.status_code == 200
    assert _login(c, tech, code) == 401, "the old code stops working"
    assert _login(c, tech, fresh.json()["login_code"]) == 200
    body = {"email": tech, "passcode": fresh.json()["login_code"]}
    staff_token = c.post("/auth/dev-login", json=body, headers=_ip()).json()["token"]
    other = c.post(
        f"/settings/staff/{added.json()['id']}/code",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert other.status_code == 403, "only the owner issues codes"


def test_login_attempts_are_limited(env) -> None:  # type: ignore[no-untyped-def]
    c = _prod(env, NOVAXIS_RATE_LIMITS_ENABLED="true")
    email = f"guess-{uuid.uuid4().hex[:6]}@demo-hvac.test"
    codes = [_login(c, email, f"try{i}") for i in range(12)]
    assert codes[:10] == [401] * 10
    assert codes[10:] == [429, 429]


def test_chat_messages_are_limited_per_visitor(env) -> None:  # type: ignore[no-untyped-def]
    c = _prod(env, NOVAXIS_RATE_LIMITS_ENABLED="true")
    first = c.post("/inbound/webchat/demo-hvac", json={"body": "hello"}, headers=_ip())
    token = first.json()["visitor_token"]
    statuses = [
        c.post(
            "/inbound/webchat/demo-hvac",
            json={"body": f"m{i}", "visitor_token": token},
            headers=_ip(),
        ).status_code
        for i in range(21)
    ]
    assert statuses[:19] == [200] * 19
    assert statuses[-1] == 429


def test_a_business_can_restrict_which_websites_host_its_widget(env) -> None:  # type: ignore[no-untyped-def]
    c = _prod(env)
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t is not None
        t.settings = {**t.settings, "widget_origins": ["https://www.smiles.test"]}
    try:

        def send(origin: str | None) -> int:
            h = {**_ip(), **({"Origin": origin} if origin else {})}
            return c.post(
                "/inbound/webchat/demo-dental", json={"body": "hi"}, headers=h
            ).status_code

        assert send("https://www.smiles.test") == 200
        assert send("https://copycat.test") == 403
        assert send(get_settings().public_web_url) == 200, "our own demo page"
        assert send(None) == 200, "not a browser"
    finally:
        with service_session() as s:
            seed(s)


def test_widget_origins_must_be_website_addresses() -> None:
    from pydantic import ValidationError

    from novaxis_core.tenant_settings import TenantSettings

    ts = TenantSettings(pack_id="hvac", widget_origins=["https://WWW.Example.co.uk/"])
    assert ts.widget_origins == ["https://www.example.co.uk"]
    with pytest.raises(ValidationError):
        TenantSettings(pack_id="hvac", widget_origins=["javascript:alert(1)"])


def test_staff_stay_signed_in_but_operator_entry_is_not_extended(env) -> None:  # type: ignore[no-untyped-def]
    c = env()
    h = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}
    r = c.post("/auth/refresh", headers=h)
    assert r.status_code == 200 and r.json()["token"]
    assert c.get("/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).status_code == 200
    with service_session() as s:
        tid = s.scalar(select(Tenant.id).where(Tenant.slug == "demo-hvac"))
    acting = {"Authorization": f"Bearer {mint('dev|operator@novaxis-ops', act_tenant=str(tid))}"}
    assert c.post("/auth/refresh", headers=acting).status_code == 403


def test_api_responses_carry_security_headers(env) -> None:  # type: ignore[no-untyped-def]
    r = env().get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
