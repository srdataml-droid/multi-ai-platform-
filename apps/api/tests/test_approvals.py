from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.models import ActionProposal, Approval, Message, Tenant, User
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session


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


def _owner() -> dict[str, str]:
    return {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}


def _viewer() -> dict[str, str]:
    return {"Authorization": f"Bearer {mint('dev|viewer@demo-hvac')}"}


def _awaiting(kind: str = "reply", params: dict | None = None) -> tuple[uuid.UUID, uuid.UUID]:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        conv_id = ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref="demo-hvac",
                sender_visitor_id=v,
                body="hi",
            ),
        ).conversation_id
        p = ActionProposal(
            tenant_id=t.id,
            conversation_id=conv_id,
            kind=kind,
            params=params or {"text": "Hello from staff-approved worker"},
            risk="medium",
            state="awaiting",
            reason="test",
        )
        s.add(p)
        s.flush()
        return p.id, conv_id


def test_list_shows_awaiting_only(client: TestClient) -> None:
    pid, _ = _awaiting()
    r = client.get("/approvals", headers=_owner())
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()["items"]}
    assert str(pid) in ids
    assert all(i["state"] == "awaiting" for i in r.json()["items"])


def test_approve_executes_and_records(client: TestClient) -> None:
    pid, conv_id = _awaiting()
    r = client.post(
        f"/approvals/{pid}", json={"decision": "approve", "note": "fine"}, headers=_owner()
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "executed"
    with service_session() as s:
        a = s.scalar(select(Approval).where(Approval.proposal_id == pid))
        assert a is not None and a.decision == "approve" and a.decided_by is not None
        msg = s.scalar(
            select(Message).where(
                Message.conversation_id == conv_id, Message.direction == "outbound"
            )
        )
        assert msg is not None and msg.body == "Hello from staff-approved worker"


def test_reject_does_not_execute(client: TestClient) -> None:
    pid, conv_id = _awaiting()
    r = client.post(f"/approvals/{pid}", json={"decision": "reject"}, headers=_owner())
    assert r.status_code == 200 and r.json()["state"] == "rejected"
    with service_session() as s:
        assert (
            s.scalar(
                select(Message).where(
                    Message.conversation_id == conv_id, Message.direction == "outbound"
                )
            )
            is None
        )


def test_edit_creates_new_proposal_and_executes_it(client: TestClient) -> None:
    pid, conv_id = _awaiting()
    r = client.post(
        f"/approvals/{pid}",
        json={"decision": "edit", "params": {"text": "Edited text"}},
        headers=_owner(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (
        body["replaced"]["state"] == "rejected"
        and body["replaced"]["superseded_by"] == body["proposal"]["id"]
    )
    assert body["proposal"]["state"] == "executed"
    with service_session() as s:
        msg = s.scalar(
            select(Message).where(
                Message.conversation_id == conv_id, Message.direction == "outbound"
            )
        )
        assert msg is not None and msg.body == "Edited text"


def test_edit_that_gate_rejects_stays_rejected(client: TestClient) -> None:
    pid, _ = _awaiting("collect_payment", {"amount_minor": 100, "currency": "GBP"})
    r = client.post(
        f"/approvals/{pid}",
        json={"decision": "edit", "params": {"amount_minor": 1, "currency": "GBP"}},
        headers=_owner(),
    )
    assert r.status_code == 200 and r.json()["proposal"]["state"] == "rejected"


def test_viewer_cannot_decide(client: TestClient) -> None:
    pid, _ = _awaiting()
    assert (
        client.post(
            f"/approvals/{pid}", json={"decision": "approve"}, headers=_viewer()
        ).status_code
        == 403
    )
    assert client.get("/approvals", headers=_viewer()).status_code == 200


def test_deciding_twice_is_a_conflict(client: TestClient) -> None:
    pid, _ = _awaiting()
    client.post(f"/approvals/{pid}", json={"decision": "reject"}, headers=_owner())
    assert (
        client.post(f"/approvals/{pid}", json={"decision": "approve"}, headers=_owner()).status_code
        == 409
    )
