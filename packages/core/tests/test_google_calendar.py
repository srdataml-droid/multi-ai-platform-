from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from novaxis_core.settings import get_settings
from novaxis_core.sor.base import ExternalRef, Slot
from novaxis_core.sor.google_calendar import GoogleCalendar, auth_url, exchange_code


@pytest.fixture(autouse=True)
def _google_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOVAXIS_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("NOVAXIS_GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("NOVAXIS_PUBLIC_BASE_URL", "https://api.example.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_auth_url_and_code_exchange() -> None:
    url = auth_url("tenant.sig")
    assert (
        "client_id=cid" in url
        and "redirect_uri=https%3A%2F%2Fapi.example.test%2Fintegrations%2Fgoogle%2Fcallback" in url
    )
    assert "access_type=offline" in url and "state=tenant.sig" in url

    def handler(req: httpx.Request) -> httpx.Response:
        body = dict(x.split("=") for x in req.content.decode().split("&"))
        assert body["grant_type"] == "authorization_code" and body["code"] == "abc"
        return httpx.Response(
            200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        )

    tok = exchange_code("abc", transport=httpx.MockTransport(handler))
    assert tok["refresh_token"] == "rt" and tok["expires_at"] > time.time()


def test_busy_create_update_cancel_and_refresh() -> None:
    saved: list[dict] = []
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})
        if (
            req.method == "GET"
            and req.url.path.endswith("/events")
            and "privateExtendedProperty" in str(req.url)
        ):
            return httpx.Response(200, json={"items": []})
        if req.method == "GET" and req.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "status": "confirmed",
                            "start": {"dateTime": "2026-10-01T09:00:00+01:00"},
                            "end": {"dateTime": "2026-10-01T10:00:00+01:00"},
                        },
                        {
                            "status": "cancelled",
                            "start": {"dateTime": "2026-10-01T11:00:00+01:00"},
                            "end": {"dateTime": "2026-10-01T12:00:00+01:00"},
                        },
                    ]
                },
            )
        if req.method == "POST":
            return httpx.Response(200, json={"id": "evt123"})
        if req.method == "PATCH":
            return httpx.Response(200, json={"id": "evt123"})
        if req.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404)

    cal = GoogleCalendar(
        {"access_token": "stale", "refresh_token": "rt", "expires_at": time.time() - 10},
        saved.append,
        transport=httpx.MockTransport(handler),
    )
    now = datetime.now(UTC)
    busy = cal.busy("primary", now, now + timedelta(days=1))
    assert len(busy) == 1, "cancelled events are not busy"
    assert saved and saved[0]["access_token"] == "fresh", "expired token was refreshed and saved"
    assert calls[1].headers["authorization"] == "Bearer fresh"
    slot = Slot(now + timedelta(days=1), now + timedelta(days=1, hours=1))
    ref = cal.create_booking("primary", slot, "Check-up: Al", "desc", "confirm:p1")
    assert ref.ref == "primary:evt123"
    posted = json.loads(
        [c for c in calls if c.method == "POST" and c.url.host == "www.googleapis.com"][0].content
    )
    assert posted["extendedProperties"]["private"]["novaxis_key"] == "confirm:p1"
    cal.update_booking(ExternalRef("google_calendar", "primary:evt123"), slot)
    cal.cancel_booking(ExternalRef("google_calendar", "primary:evt123"))
    assert [c.method for c in calls[-2:]] == ["PATCH", "DELETE"]
