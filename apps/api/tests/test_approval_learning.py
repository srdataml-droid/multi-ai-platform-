"""The approval model: a proposal that starts waiting gets the model's guess stored with
it, staff see it, the shadow report compares guesses with decisions, and the model never
approves anything or blocks the queue when it fails."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core import approval_model
from novaxis_core.channels import NormalisedInbound
from novaxis_core.gate import GateContext
from novaxis_core.inbound import ingest
from novaxis_core.models import ActionProposal, Conversation, Job, Tenant
from novaxis_core.turn import propose
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session

OWNER = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}


@pytest.fixture
def client(migrated: str) -> TestClient:
    with service_session(migrated) as s:
        seed(s)
    return TestClient(create_app())


def _held_reply(text: str) -> uuid.UUID:
    """A reply the business's own rule holds for approval, proposed the normal way."""
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
                body="Can someone come on Monday?",
            ),
        ).conversation_id
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        ctx = GateContext(tenant_settings={"risk_overrides": {"reply": "medium"}})
        p, d = propose(s, t, conv, "reply", {"text": text}, ctx, "model proposal")
        assert d.state == "awaiting"
        return p.id


def test_a_waiting_proposal_carries_the_models_guess_and_staff_see_it(client: TestClient) -> None:
    pid = _held_reply("Yes, an engineer can come Monday morning. It costs £85.")
    items = client.get("/approvals", headers=OWNER).json()["items"]
    mine = next(i for i in items if i["id"] == str(pid))
    g = mine["prediction"]
    assert 0 < g["p"] < 1 and g["level"] in ("likely", "unsure", "unlikely")
    assert g["data"] == "synthetic" and "demo model trained on synthetic data" in g["reasons"]
    assert all("£85" not in r and "Monday" not in r for r in g["reasons"]), "no message text"
    assert mine["state"] == "awaiting", "advice only: the model approved nothing"


def test_the_shadow_report_compares_the_guesses_with_what_staff_decided(
    client: TestClient,
) -> None:
    before = client.get("/approvals/learning", headers=OWNER).json()
    assert before["model"]["data"] == "synthetic" and before["model"]["rows"] > 0
    ids = [_held_reply(f"Short reply {n}") for n in range(3)]
    with service_session() as s:  # fix the guesses so the arithmetic is checkable
        for pid, p in zip(ids, (0.97, 0.92, 0.3), strict=True):
            row = s.get(ActionProposal, pid)
            assert row is not None
            row.prediction = {**(row.prediction or {}), "p": p}
    assert (
        client.post(f"/approvals/{ids[0]}", json={"decision": "approve"}, headers=OWNER).status_code
        == 200
    )
    assert (
        client.post(f"/approvals/{ids[1]}", json={"decision": "reject"}, headers=OWNER).status_code
        == 200
    )
    assert (
        client.post(f"/approvals/{ids[2]}", json={"decision": "reject"}, headers=OWNER).status_code
        == 200
    )

    after = client.get("/approvals/learning", headers=OWNER).json()["shadow"]
    b = before["shadow"]
    assert after["decided_with_prediction"] - b["decided_with_prediction"] == 3
    assert after["staff_approved"] - b["staff_approved"] == 1

    def at(report: dict[str, Any], t: float) -> dict[str, Any]:
        return next(x for x in report["thresholds"] if x["threshold"] == t)

    for t, auto, wrong in ((0.9, 2, 1), (0.95, 1, 0)):
        assert at(after, t)["would_auto_approve"] - at(b, t)["would_auto_approve"] == auto
        d = (
            at(after, t)["of_which_staff_did_not_approve"]
            - at(b, t)["of_which_staff_did_not_approve"]
        )
        assert d == wrong


def test_a_failing_model_never_stops_a_proposal_reaching_staff(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: approval_model.ApprovalModel, x: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("model file damaged")

    monkeypatch.setattr(approval_model.ApprovalModel, "predict", broken)
    pid = _held_reply("Can we do Tuesday instead?")
    with service_session() as s:
        p = s.get(ActionProposal, pid)
        assert p is not None and p.state == "awaiting" and p.prediction is None
        assert s.scalar(
            select(Job).where(
                Job.kind == "notify_staff", Job.payload["proposal_id"].astext == str(pid)
            )
        ), "staff are still told"


def test_a_real_business_never_sees_the_synthetic_model() -> None:
    m = approval_model.load()
    assert m is not None and m.synthetic
    assert approval_model.model_for("demo-dental") is m
    assert approval_model.model_for("acme-heating") is None


def test_a_database_error_while_guessing_is_contained(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import text

    def failing_query(session: Any, tenant: Any, p: Any) -> Any:
        session.execute(text("select 1/0"))  # the database raises mid-prediction

    monkeypatch.setattr(approval_model, "input_for", failing_query)
    pid = _held_reply("Could we move it to Thursday?")
    with service_session() as s:
        p = s.get(ActionProposal, pid)
        assert p is not None and p.state == "awaiting" and p.prediction is None
        assert s.scalar(
            select(Job).where(
                Job.kind == "notify_staff", Job.payload["proposal_id"].astext == str(pid)
            )
        ), "the proposal and the staff alert were kept"
