"""The booking bridge through the API: connect, upload an export, see and tick hand-offs."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from novaxis_api.main import create_app
from novaxis_core.sor import set_sor_override
from novaxis_db.seed import seed
from novaxis_db.session import service_session


@pytest.fixture
def owner(migrated: str) -> tuple[TestClient, dict[str, str]]:
    set_sor_override(None)
    with service_session(migrated) as s:
        seed(s)
    c = TestClient(create_app())
    r = c.post(
        "/signup",
        json={
            "business_name": "Bridge Test Co",
            "email": f"{uuid.uuid4().hex[:8]}@b.test",
            "pack_id": "hvac",
        },
    )
    assert r.status_code == 200, r.text
    return c, {"Authorization": f"Bearer {r.json()['token']}"}


def test_connect_upload_and_read_back(owner: tuple[TestClient, dict[str, str]]) -> None:
    c, h = owner
    assert c.get("/integrations/bridge", headers=h).json()["connected"] is False
    assert c.post("/integrations/bridge/import", headers=h, json={"csv": "x"}).status_code == 409

    bad = c.put("/integrations/bridge", headers=h, json={"vendor_name": "", "email_to": "nope"})
    assert bad.status_code == 422 and bad.json()["detail"].startswith("vendor_name")
    r = c.put(
        "/integrations/bridge",
        headers=h,
        json={
            "vendor_name": "Acme Jobs",
            "email_to": "office@b.test",
            "service_map": {"repair_visit": "Callout"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] and body["settings"]["vendor_name"] == "Acme Jobs"
    assert body["health"]["ok"] is False and "no diary export" in body["health"]["detail"]
    assert c.get("/integrations", headers=h).json()["system_of_record"] == "booking_bridge"

    day = datetime.now(ZoneInfo("Europe/London")) + timedelta(days=3)
    export = (
        "Start,End,Title,Status\n"
        f"{day:%d/%m/%Y} 09:00,{day:%d/%m/%Y} 10:00,Job A,Scheduled\n"
        f"{day:%d/%m/%Y} 11:00,{day:%d/%m/%Y} 12:00,Job B,Cancelled\n"
    )
    up = c.post("/integrations/bridge/import", headers=h, json={"csv": export})
    assert up.status_code == 200, up.text
    assert up.json() == {"rows": 2, "imported": 1, "skipped": 1, "errors": [], "conflicts": 0}
    after = c.get("/integrations/bridge", headers=h).json()
    assert after["health"]["ok"] is True and after["vendor_busy_upcoming"] == 1

    broken = c.post("/integrations/bridge/import", headers=h, json={"csv": "Title\nx\n"})
    assert broken.status_code == 422 and "no start or date column" in broken.json()["detail"]

    off = c.delete("/integrations/bridge", headers=h)
    assert off.json()["connected"] is False


def test_only_the_office_can_change_it(owner: tuple[TestClient, dict[str, str]]) -> None:
    from novaxis_api.devtoken import mint

    c, h = owner
    viewer = {"Authorization": f"Bearer {mint('dev|viewer@demo-hvac')}"}
    assert (
        c.put("/integrations/bridge", headers=viewer, json={"vendor_name": "X"}).status_code == 403
    )
    assert (
        c.post("/integrations/bridge/import", headers=viewer, json={"csv": ""}).status_code == 403
    )
    ticket = f"/integrations/bridge/tickets/{uuid.uuid4()}/entered"
    assert c.post(ticket, headers=viewer).status_code == 403
    assert c.post(ticket, headers=h).status_code == 404
