"""Push events to a business's own agent: set up by the owner with a secret shown once,
signed, ids only (no names or message text), sent after the emergency check, decisions
on the agent's proposals pushed too, and a customer handed to a person if the agent cannot
be reached. Webhook addresses cannot point inside the platform's network."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core import agent_webhooks as wh
from novaxis_core.agent_webhooks import AGENT_EVENT_JOB, WebhookError, check_url, deliver, verify
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.models import AgentKey, Conversation, Job, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack
from novaxis_worker.loop import Picked, run_job

OWNER = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}
HOOK = "https://agent.example.com/novaxis"


@pytest.fixture
def client(migrated: str) -> TestClient:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        t.settings = {**t.settings, "assistant": "external"}
        for k in s.scalars(select(AgentKey).where(AgentKey.tenant_id == t.id)):
            k.revoked_at = k.revoked_at or k.created_at  # a clean slate of keys per test
    return TestClient(create_app())


def _tenant() -> Tenant:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        return t


def _key_with_hook(c: TestClient) -> tuple[str, str, str]:
    """Returns (agent key, key id, webhook secret)."""
    r = c.post("/settings/agent-keys", json={"name": "hermes"}, headers=OWNER)
    key, kid = r.json()["key"], r.json()["id"]
    r = c.put(f"/settings/agent-keys/{kid}/webhook", json={"url": HOOK}, headers=OWNER)
    assert r.status_code == 200, r.text
    return key, kid, r.json()["webhook_secret"]


def _customer_writes(text: str, phone: str | None = None) -> uuid.UUID:
    """A customer message, then the platform's turn (the emergency check; no model)."""
    t = _tenant()
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
                sender_name="Wendy Customer",
                body=text,
            ),
        ).conversation_id
        run_turn(s, t, get_pack("hvac"), None, conv_id)  # type: ignore[arg-type]
    return conv_id


def _events(conv_or_proposal: str) -> list[Job]:
    with service_session() as s:
        jobs = list(s.scalars(select(Job).where(Job.kind == AGENT_EVENT_JOB)))
        s.expunge_all()
    return [j for j in jobs if conv_or_proposal in json.dumps(j.payload)]


def test_the_owner_sets_a_webhook_and_sees_the_secret_once(client: TestClient) -> None:
    _, kid, secret = _key_with_hook(client)
    assert secret.startswith("whsec_")
    listed = client.get("/settings/agent-keys", headers=OWNER).json()["items"]
    mine = next(k for k in listed if k["id"] == kid)
    assert mine["webhook_url"] == HOOK and secret not in json.dumps(listed)
    with service_session() as s:
        row = s.get(AgentKey, uuid.UUID(kid))
        assert row is not None and row.webhook_secret and secret not in row.webhook_secret
    bad = client.put(
        f"/settings/agent-keys/{kid}/webhook",
        json={"url": "https://169.254.169.254/latest"},
        headers=OWNER,
    )
    assert bad.status_code in (200, 422)  # dev allows it; production rules tested below
    cleared = client.put(f"/settings/agent-keys/{kid}/webhook", json={"url": None}, headers=OWNER)
    assert cleared.json()["webhook_url"] is None and "webhook_secret" not in cleared.json()


def test_a_customer_message_is_pushed_signed_with_ids_only(client: TestClient) -> None:
    _, _, secret = _key_with_hook(client)
    conv_id = _customer_writes("My radiator is cold, can someone come?")
    jobs = _events(str(conv_id))
    assert len(jobs) == 1 and jobs[0].payload["event"] == "message.received"

    got: list[httpx.Request] = []

    def agent(req: httpx.Request) -> httpx.Response:
        got.append(req)
        return httpx.Response(204)

    t = _tenant()
    with tenant_session(t.id) as s:
        job = s.get(Job, jobs[0].id)
        assert job is not None
        assert deliver(s, t, job, transport=httpx.MockTransport(agent)) == "delivered 204"
    req = got[0]
    assert str(req.url) == HOOK
    assert verify(secret, req.headers["X-Novaxis-Signature"], req.content)
    assert not verify("whsec_wrong", req.headers["X-Novaxis-Signature"], req.content)
    body = json.loads(req.content)
    assert body["event"] == "message.received"
    assert body["data"] == {"conversation_id": str(conv_id), "channel": "webchat"}
    raw = req.content.decode()
    assert "radiator" not in raw and "Wendy" not in raw, "no message text or names"


def test_emergencies_are_handled_by_the_platform_and_not_pushed(client: TestClient) -> None:
    _key_with_hook(client)
    conv_id = _customer_writes("I can smell gas in the hallway")
    assert _events(str(conv_id)) == []
    with service_session() as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"


def test_staff_decisions_on_the_agents_proposals_are_pushed(client: TestClient) -> None:
    key, _, _ = _key_with_hook(client)
    conv_id = _customer_writes("Can someone fix my boiler next week?")
    r = client.post(
        f"/agent/v1/conversations/{conv_id}/proposals",
        json={"kind": "propose_appointment", "params": {"service_code": "repair_visit"}},
        headers={"Authorization": f"Bearer {key}"},
    )
    pid = r.json()["proposal_id"]
    assert r.json()["state"] == "awaiting"
    assert (
        client.post(f"/approvals/{pid}", json={"decision": "reject"}, headers=OWNER).status_code
        == 200
    )
    decided = [j for j in _events(pid) if j.payload["event"] == "proposal.decided"]
    assert len(decided) == 1
    data: dict[str, Any] = decided[0].payload["data"]
    assert data["state"] == "rejected" and data["about_conversation"] == str(conv_id)
    assert "conversation_id" not in decided[0].payload, "a lost decision hands nobody over"


def test_an_agent_that_cannot_be_reached_hands_the_customer_to_a_person(
    client: TestClient,
) -> None:
    _key_with_hook(client)
    conv_id = _customer_writes("Hello, is anyone there?")
    job = _events(str(conv_id))[0]

    def down(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    handlers = {
        AGENT_EVENT_JOB: lambda s, t, j: deliver(s, t, j, transport=httpx.MockTransport(down))
    }
    for attempt in range(get_settings().worker_max_attempts):
        assert not run_job(Picked(job.id, job.tenant_id, AGENT_EVENT_JOB, attempt), handlers)
    with service_session() as s:
        failed = s.get(Job, job.id)
        conv = s.get(Conversation, conv_id)
        assert failed is not None and failed.state == "failed"
        assert conv is not None and conv.status == "waiting_human"
        assert s.scalar(
            select(Job).where(
                Job.kind == "alert_staff", Job.payload["url"].astext == f"/conversations/{conv_id}"
            )
        )


def test_a_revoked_key_gets_nothing_and_the_owner_can_send_a_test(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, kid, secret = _key_with_hook(client)
    answers = iter([httpx.Response(503), httpx.Response(200)])
    pings: list[httpx.Request] = []

    def agent(req: httpx.Request) -> httpx.Response:
        pings.append(req)
        return next(answers)

    real_client = httpx.Client
    monkeypatch.setattr(
        wh.httpx,
        "Client",
        lambda **kw: real_client(**{**kw, "transport": httpx.MockTransport(agent)}),
    )
    down = client.post(f"/settings/agent-keys/{kid}/webhook/test", headers=OWNER).json()
    assert down["ok"] is False and "503" in down["detail"]
    up = client.post(f"/settings/agent-keys/{kid}/webhook/test", headers=OWNER).json()
    assert up == {"ok": True, "status_code": 200}
    assert json.loads(pings[1].content)["event"] == "ping"
    assert verify(secret, pings[1].headers["X-Novaxis-Signature"], pings[1].content)

    conv_id = _customer_writes("Anyone?")
    client.delete(f"/settings/agent-keys/{kid}", headers=OWNER)
    t = _tenant()
    with tenant_session(t.id) as s:
        job = s.get(Job, _events(str(conv_id))[0].id)
        assert job is not None
        assert deliver(s, t, job).startswith("skipped")


def test_webhook_addresses_cannot_point_inside_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wh, "_dev", lambda: False)
    assert check_url("https://agent.example.com/hook") == "https://agent.example.com/hook"
    for bad in (
        "http://agent.example.com/hook",
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://10.0.0.5/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/hook",
        "https://user:pass@agent.example.com/hook",
        "ftp://agent.example.com",
    ):
        with pytest.raises(WebhookError):
            check_url(bad)
    monkeypatch.setattr(
        wh.socket, "getaddrinfo", lambda host, port: [(0, 0, 0, "", ("10.1.2.3", 0))]
    )
    assert not wh._resolves_public("https://sneaky.example.com/hook"), "DNS pointing inside"


def test_old_or_forged_signatures_are_rejected() -> None:
    body = b'{"event":"ping"}'
    fresh = wh.signature("whsec_x", 1_000_000, body)
    assert verify("whsec_x", fresh, body, now=1_000_100)
    assert not verify("whsec_x", fresh, body, now=1_000_000 + 301), "too old: a replay"
    assert not verify("whsec_x", fresh, body + b" ", now=1_000_100), "body changed"
    assert not verify("whsec_x", "garbage", body, now=1_000_100)


def test_the_example_agent_checks_signatures_the_same_way() -> None:
    import importlib.util
    import time
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "examples" / "hermes_agent.py"
    spec = importlib.util.spec_from_file_location("hermes_agent", path)
    assert spec is not None and spec.loader is not None
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    body = b'{"event":"message.received"}'
    header = wh.signature("whsec_abc", int(time.time()), body)
    assert example.verify("whsec_abc", header, body)
    assert not example.verify("whsec_other", header, body)
    assert not example.verify("whsec_abc", header, body + b"x")
    stale = wh.signature("whsec_abc", int(time.time()) - 600, body)
    assert not example.verify("whsec_abc", stale, body)
