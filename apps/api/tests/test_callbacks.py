from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.gate import GateContext, decide
from novaxis_core.models import ActionProposal, AuditLog, Message, Tenant
from novaxis_db.seed import seed
from novaxis_db.session import service_session


def auth(who: str = "owner@demo-hvac") -> dict[str, str]:
    return {"Authorization": f"Bearer {mint('dev|' + who)}"}


def enquiry() -> dict:
    return {
        "request_id": str(uuid.uuid4()),
        "name": "Callback Test",
        "phone": "07700 900123",
        "email": "test@example.test",
        "postcode": "N13 4SD",
        "service": "Boiler service",
        "details": "A routine service",
        "preferred_window": "2026-10-20 14:00 Europe/London",
        "consent": True,
    }


@pytest.fixture
def client(migrated: str) -> TestClient:
    with service_session() as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        t.settings = {**t.settings, "callback_enquiries_enabled": True}
    return TestClient(create_app())


def submit(client: TestClient) -> str:
    body = enquiry()
    assert client.post("/enquiries/demo-hvac", json=body).status_code == 201
    with service_session() as s:
        message = s.scalar(
            select(Message).where(Message.provider_ref == f"enquiry:{body['request_id']}")
        )
        return str(
            s.scalar(
                select(ActionProposal.id).where(
                    ActionProposal.conversation_id == message.conversation_id
                )
            )
        )


def test_persistent_approval_edit_outcome_and_isolation(client: TestClient) -> None:
    pid = submit(client)
    assert client.get("/callbacks").status_code == 401
    assert client.get("/callbacks", headers=auth("viewer@demo-hvac")).status_code == 403
    assert (
        client.post(
            f"/approvals/{pid}", headers=auth("viewer@demo-hvac"), json={"decision": "approve"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/approvals/{pid}", headers=auth("owner@demo-dental"), json={"decision": "approve"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/callbacks/{pid}/outcome", headers=auth(), json={"outcome": "completed"}
        ).status_code
        == 409
    )
    r = client.post(
        f"/approvals/{pid}",
        headers=auth(),
        json={"decision": "edit", "params": {"window": "2026-10-21 09:00 Europe/London"}},
    )
    assert r.status_code == 200, r.text
    updated = r.json()["proposal"]
    assert updated["state"] == "executed"
    new_id = updated["id"]
    assert (
        client.post(
            f"/approvals/{new_id}", headers=auth(), json={"decision": "approve"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/callbacks/{new_id}/outcome",
            headers=auth("owner@demo-dental"),
            json={"outcome": "completed"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/callbacks/{new_id}/outcome",
            headers=auth("viewer@demo-hvac"),
            json={"outcome": "completed"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/callbacks/{new_id}/outcome", headers=auth(), json={"outcome": "completed"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/callbacks/{new_id}/outcome", headers=auth(), json={"outcome": "no_answer"}
        ).status_code
        == 409
    )
    # Fresh request/session proves this is not browser or in-process state.
    rows = TestClient(create_app()).get("/callbacks", headers=auth()).json()["items"]
    record = next(x for x in rows if x["id"] == new_id)
    assert record["outcome"] == "completed"
    assert record["window"] == "2026-10-21 09:00 Europe/London"
    assert all(x["id"] != pid for x in rows)
    with service_session() as s:
        p = s.get(ActionProposal, uuid.UUID(new_id))
        assert (
            s.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == p.conversation_id, Message.direction == "outbound"
                )
            )
            == 0
        )
        assert (
            s.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.subject_id == p.id, AuditLog.event == "callback.outcome")
            )
            == 1
        )


def test_concurrent_submission_and_decision_are_once(client: TestClient) -> None:
    body = enquiry()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: client.post("/enquiries/demo-hvac", json=body).status_code, range(2))
        )
    assert results == [201, 201]
    with service_session() as s:
        messages = list(
            s.scalars(
                select(Message).where(Message.provider_ref == f"enquiry:{body['request_id']}")
            )
        )
        assert len(messages) == 1
        pid = str(
            s.scalar(
                select(ActionProposal.id).where(
                    ActionProposal.conversation_id == messages[0].conversation_id
                )
            )
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: (
                    client.post(
                        f"/approvals/{pid}", headers=auth(), json={"decision": "approve"}
                    ).status_code
                ),
                range(2),
            )
        )
    assert sorted(results) == [200, 409]


def test_reject_and_invalid_input(client: TestClient) -> None:
    pid = submit(client)
    assert (
        client.post(f"/approvals/{pid}", headers=auth(), json={"decision": "reject"}).status_code
        == 200
    )
    assert (
        client.post(
            f"/callbacks/{pid}/outcome", headers=auth(), json={"outcome": "completed"}
        ).status_code
        == 409
    )
    for change in (
        {"consent": False},
        {"name": "   "},
        {"details": "x" * 1001},
        {"email": "invalid"},
        {"phone": "nobody here"},
    ):
        assert client.post("/enquiries/demo-hvac", json={**enquiry(), **change}).status_code == 422
    assert client.post("/enquiries/demo-dental", json=enquiry()).status_code == 404
    assert (
        client.post(f"/approvals/{pid}", headers=auth(), json={"decision": "approve"}).status_code
        == 409
    )


def test_callback_always_needs_human() -> None:
    d = decide("schedule_callback", {"window": "Tomorrow"}, GateContext())
    assert d.state == "awaiting"
    assert d.risk == "medium"


def test_opt_in_and_origin_controls(client: TestClient) -> None:
    assert (
        client.put(
            "/callbacks/config", headers=auth("viewer@demo-hvac"), json={"enabled": True}
        ).status_code
        == 403
    )
    assert client.get("/callbacks/config", headers=auth()).json()["enabled"] is True
    assert (
        client.put("/callbacks/config", headers=auth(), json={"enabled": False}).status_code == 200
    )
    assert client.get("/enquiries/demo-hvac").status_code == 404
    assert client.post("/enquiries/demo-hvac", json=enquiry()).status_code == 404
    assert (
        client.put("/callbacks/config", headers=auth(), json={"enabled": True}).status_code == 200
    )
    assert client.get("/enquiries/demo-hvac").status_code == 200
    with service_session() as s:
        tenant = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        tenant.settings = {**tenant.settings, "widget_origins": ["https://allowed.example"]}
    assert (
        client.post(
            "/enquiries/demo-hvac", json=enquiry(), headers={"Origin": "https://other.example"}
        ).status_code
        == 403
    )
