"""Google Calendar over its REST API, with OAuth tokens refreshed in the worker.

Endpoints used: events.list (busy times), events.insert, events.patch,
events.delete, and the OAuth token endpoint for refresh. Written from the API's
documented shape; confirm against a real connection on first deploy [VERIFY].
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from novaxis_core.settings import get_settings
from novaxis_core.sor.base import Busy, ExternalRef, Health, Slot

API = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/calendar.events"

TokenSaver = Callable[[dict[str, Any]], None]


def auth_url(state: str) -> str:
    s = get_settings()
    params = httpx.QueryParams(
        {
            "client_id": s.google_client_id,
            "redirect_uri": f"{s.public_base_url}/integrations/google/callback",
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{AUTH_URL}?{params}"


def exchange_code(code: str, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    s = get_settings()
    with httpx.Client(transport=transport, timeout=20) as c:
        r = c.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": f"{s.public_base_url}/integrations/google/callback",
                "grant_type": "authorization_code",
            },
        )
    r.raise_for_status()
    tok: dict[str, Any] = dict(r.json())
    tok["expires_at"] = time.time() + float(tok.get("expires_in", 3600))
    return tok


class GoogleCalendar:
    provider = "google_calendar"

    def __init__(
        self, tokens: dict[str, Any], save: TokenSaver, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._tokens = dict(tokens)
        self._save = save
        self._transport = transport

    def _access_token(self) -> str:
        if self._tokens.get("expires_at", 0) - 60 < time.time() and self._tokens.get(
            "refresh_token"
        ):
            s = get_settings()
            with httpx.Client(transport=self._transport, timeout=20) as c:
                r = c.post(
                    TOKEN_URL,
                    data={
                        "refresh_token": self._tokens["refresh_token"],
                        "client_id": s.google_client_id,
                        "client_secret": s.google_client_secret,
                        "grant_type": "refresh_token",
                    },
                )
            r.raise_for_status()
            fresh = r.json()
            self._tokens["access_token"] = fresh["access_token"]
            self._tokens["expires_at"] = time.time() + float(fresh.get("expires_in", 3600))
            self._save(self._tokens)
        return str(self._tokens.get("access_token", ""))

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self._transport,
            timeout=20,
            headers={"Authorization": f"Bearer {self._access_token()}"},
        )

    def busy(
        self, calendar_ref: str | None, window_start: datetime, window_end: datetime
    ) -> list[Busy]:
        cal = calendar_ref or "primary"
        with self._client() as c:
            r = c.get(
                f"{API}/calendars/{cal}/events",
                params={
                    "timeMin": window_start.astimezone(UTC).isoformat(),
                    "timeMax": window_end.astimezone(UTC).isoformat(),
                    "singleEvents": "true",
                    "maxResults": "250",
                },
            )
        r.raise_for_status()
        out: list[Busy] = []
        for item in r.json().get("items", []):
            if item.get("status") == "cancelled" or item.get("transparency") == "transparent":
                continue
            start = (item.get("start") or {}).get("dateTime")
            end = (item.get("end") or {}).get("dateTime")
            if start and end:
                out.append(Busy(datetime.fromisoformat(start), datetime.fromisoformat(end)))
        return out

    def create_booking(
        self,
        calendar_ref: str | None,
        slot: Slot,
        summary: str,
        description: str,
        idempotency_key: str,
    ) -> ExternalRef:
        cal = calendar_ref or "primary"
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": slot.starts_at.isoformat()},
            "end": {"dateTime": slot.ends_at.isoformat()},
            "extendedProperties": {"private": {"novaxis_key": idempotency_key}},
        }
        with self._client() as c:
            existing = c.get(
                f"{API}/calendars/{cal}/events",
                params={
                    "privateExtendedProperty": f"novaxis_key={idempotency_key}",
                    "maxResults": "1",
                },
            )
            if existing.status_code == 200 and existing.json().get("items"):
                return ExternalRef(self.provider, f"{cal}:{existing.json()['items'][0]['id']}")
            r = c.post(f"{API}/calendars/{cal}/events", json=body)
        r.raise_for_status()
        return ExternalRef(self.provider, f"{cal}:{r.json()['id']}")

    def _split(self, ref: ExternalRef) -> tuple[str, str]:
        cal, _, event_id = ref.ref.partition(":")
        return cal, event_id

    def update_booking(self, ref: ExternalRef, slot: Slot) -> None:
        cal, event_id = self._split(ref)
        with self._client() as c:
            r = c.patch(
                f"{API}/calendars/{cal}/events/{event_id}",
                json={
                    "start": {"dateTime": slot.starts_at.isoformat()},
                    "end": {"dateTime": slot.ends_at.isoformat()},
                },
            )
        r.raise_for_status()

    def cancel_booking(self, ref: ExternalRef) -> None:
        cal, event_id = self._split(ref)
        with self._client() as c:
            r = c.delete(f"{API}/calendars/{cal}/events/{event_id}")
        if r.status_code not in (200, 204, 404, 410):
            r.raise_for_status()

    def health(self) -> Health:
        try:
            with self._client() as c:
                r = c.get(f"{API}/users/me/calendarList", params={"maxResults": "1"})
            r.raise_for_status()
            return Health(True, "connected")
        except httpx.HTTPError as exc:
            return Health(False, f"{type(exc).__name__}: {exc}"[:200])
