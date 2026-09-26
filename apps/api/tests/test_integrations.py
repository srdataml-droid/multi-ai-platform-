from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_api.routes_integrations import _sign_state, set_callback_transport
from novaxis_core.credentials import unseal
from novaxis_core.models import Integration, Tenant
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session


@pytest.fixture
def client(migrated: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("NOVAXIS_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("NOVAXIS_GOOGLE_CLIENT_SECRET", "cs")
    get_settings.cache_clear()
    with service_session(migrated) as s:
        seed(s)
    yield TestClient(create_app(), follow_redirects=False)
    get_settings.cache_clear()
    set_callback_transport(None)
    # Never leave a connected fake calendar behind for other tests, even if this one failed.
    with service_session(migrated) as s:
        for integ in s.scalars(
            select(Integration).where(Integration.provider == "google_calendar")
        ):
            integ.health = "disconnected"
            integ.encrypted_credentials = None


def _owner(slug: str = "demo-hvac") -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(f'dev|owner@{slug}')}"}


def test_connect_returns_google_url_and_callback_stores_sealed_tokens(client: TestClient) -> None:
    r = client.get("/integrations/google/connect", headers=_owner())
    assert r.status_code == 200 and r.json()["url"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?"
    )
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        tid = t.id

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
                "scope": "calendar.events",
            },
        )

    set_callback_transport(httpx.MockTransport(handler))
    r = client.get(
        "/integrations/google/callback", params={"code": "abc", "state": _sign_state(tid)}
    )
    assert r.status_code == 302 and "connected=google_calendar" in r.headers["location"]
    with tenant_session(tid) as s:
        integ = s.scalar(select(Integration).where(Integration.provider == "google_calendar"))
        assert integ is not None and integ.health == "connected"
        assert integ.encrypted_credentials is not None
        assert b'"refresh_token"' not in integ.encrypted_credentials, "sealed, not plaintext JSON"
        assert unseal(integ.encrypted_credentials)["refresh_token"] == "rt"
    listing = client.get("/integrations", headers=_owner()).json()
    assert listing["system_of_record"] == "google_calendar"
    assert listing["items"][0]["provider"] == "google_calendar"
    r = client.post(f"/integrations/{listing['items'][0]['id']}/disconnect", headers=_owner())
    assert r.status_code == 200 and r.json()["health"] == "disconnected"
    assert (
        client.get("/integrations", headers=_owner()).json()["system_of_record"] == "business_hours"
    )


def test_callback_with_forged_state_is_rejected(client: TestClient) -> None:
    r = client.get(
        "/integrations/google/callback", params={"code": "abc", "state": "not-a-tenant.deadbeef"}
    )
    assert r.status_code == 400
