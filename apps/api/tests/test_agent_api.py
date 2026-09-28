"""The agent API: a business's own agent reads conversations and proposes actions, and the
platform's gate decides. Keys are the owner's to make and revoke; an agent key opens only
/agent/v1 and one business; the disclosure, consent, emergency check and approvals stay
with the platform whoever the agent is."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.models import ActionProposal, Conversation, Message, Tenant, User
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

OWNER = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}


@pytest.fixture
def client(migrated: str) -> TestClient:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        if s.scalar(select(User).where(User.auth_subject == "dev|staff@demo-hvac")) is None:
            s.add(
                User(
                    tenant_id=t.id,
                    auth_subject="dev|staff@demo-hvac",
                    email="staff@demo-hvac.test",
                    role="staff",
                )
            )
    return TestClient(create_app())


def _tenant(slug: str = "demo-hvac") -> Tenant:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == slug))
        assert t is not None
        s.expunge(t)
        return t


def _external(slug: str = "demo-hvac") -> None:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == slug))
        assert t is not None
        t.settings = {**t.settings, "assistant": "external"}


def _key(c: TestClient, name: str = "hermes") -> dict[str, str]:
    r = c.post("/settings/agent-keys", json={"name": name}, headers=OWNER)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['key']}"}


def _customer_writes(text: str, slug: str = "demo-hvac", phone: str | None = None) -> uuid.UUID:
    t = _tenant(slug)
    with tenant_session(t.id) as s:
        if phone:
            msg = NormalisedInbound(
                channel="twilio_sms",
                provider_ref=f"SM{uuid.uuid4().hex}",
                tenant_ref=t.settings["channels"]["twilio_sms"]["config"]["number"],
                sender_phone=phone,
                body=text,
            )
        else:
            v = uuid.uuid4().hex[:10]
            msg = NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref=slug,
                sender_visitor_id=v,
                body=text,
            )
        return ingest(s, t, msg).conversation_id


def test_keys_are_the_owners_shown_once_and_revocable(client: TestClient) -> None:
    r = client.post("/settings/agent-keys", json={"name": "hermes"}, headers=OWNER)
    assert r.status_code == 201
    key, kid = r.json()["key"], r.json()["id"]
    assert key.startswith("nvx_agent_") and r.json()["prefix"] == key[:16]
    listed = client.get("/settings/agent-keys", headers=OWNER).json()["items"]
    assert any(k["id"] == kid for k in listed) and key not in json.dumps(listed)
    staff = {"Authorization": f"Bearer {mint('dev|staff@demo-hvac')}"}
    assert client.post("/settings/agent-keys", json={"name": "x"}, headers=staff).status_code == 403

    agent = {"Authorization": f"Bearer {key}"}
    assert client.get("/agent/v1/tools", headers=agent).status_code == 200
    assert client.delete(f"/settings/agent-keys/{kid}", headers=OWNER).status_code == 200
    assert client.get("/agent/v1/tools", headers=agent).status_code == 401, "revoked"


def test_an_agent_key_opens_only_the_agent_api_and_sign_in_does_not_open_it(
    client: TestClient,
) -> None:
    agent = _key(client)
    assert client.get("/approvals", headers=agent).status_code == 401
    assert client.get("/settings", headers=agent).status_code == 401
    assert client.get("/agent/v1/tools", headers=OWNER).status_code == 401
    assert client.get("/agent/v1/tools").status_code == 401
    bad = {"Authorization": "Bearer nvx_agent_not-a-real-key"}
    assert client.get("/agent/v1/tools", headers=bad).status_code == 401


def test_the_agent_gets_the_same_tools_and_instructions_as_the_built_in_assistant(
    client: TestClient,
) -> None:
    body = client.get("/agent/v1/tools", headers=_key(client)).json()
    names = [t["function"]["name"] for t in body["tools"]]
    pack = get_pack("hvac")
    assert names == ["reply", *[t["name"] for t in pack.tools]]
    assert all(t["type"] == "function" and "parameters" in t["function"] for t in body["tools"])
    assert body["instructions"] == pack.system_prompt and body["assistant"] == "built_in"


def test_the_agent_sees_what_it_needs_and_not_phone_numbers(client: TestClient) -> None:
    agent = _key(client)
    phone = f"+4477009{uuid.uuid4().int % 100000:05d}"
    conv_id = _customer_writes("Boiler is making a banging noise", phone=phone)
    waiting = client.get("/agent/v1/conversations", headers=agent).json()["items"]
    assert str(conv_id) in {w["conversation_id"] for w in waiting}
    ctx = client.get(f"/agent/v1/conversations/{conv_id}", headers=agent).json()
    assert ctx["messages"][-1] == {**ctx["messages"][-1], "from": "customer"}
    assert "banging noise" in ctx["messages"][-1]["text"]
    assert ctx["conversation"]["agent_may_act"] is True and "reply" in ctx["tools"]
    assert "Business name" in ctx["business"]
    assert phone not in json.dumps(ctx) and phone[1:] not in json.dumps(ctx)


def test_proposals_go_through_the_gate_with_the_disclosure_and_retries_are_harmless(
    client: TestClient,
) -> None:
    agent = _key(client)
    conv_id = _customer_writes("Hi, my radiator is cold")
    url = f"/agent/v1/conversations/{conv_id}/proposals"
    reply = {"kind": "reply", "params": {"text": "Sorry to hear that. What's your postcode?"}}
    assert client.post(url, json=reply, headers=agent).status_code == 409, "built-in mode"

    _external()
    r = client.post(url, json=reply, headers=agent)
    assert r.status_code == 201 and r.json()["state"] == "executed", r.text
    assert r.json()["reason"].startswith("agent:hermes")
    again = client.post(url, json=reply, headers=agent)
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert again.json()["proposal_id"] == r.json()["proposal_id"]
    second = {"kind": "reply", "params": {"text": "Thanks, and your name?"}}
    assert client.post(url, json=second, headers=agent).status_code == 201

    with tenant_session(_tenant().id) as s:
        sent = [
            m.body
            for m in s.scalars(
                select(Message)
                .where(Message.conversation_id == conv_id, Message.direction == "outbound")
                .order_by(Message.created_at)
            )
        ]
    assert len(sent) == 2, "the retry did not send a second message"
    assert sent[0].startswith("Hi, I'm the AI assistant") and "postcode" in sent[0]
    assert sent[1] == "Thanks, and your name?", "the disclosure opens only the first reply"


def test_risky_actions_wait_for_staff_and_the_agent_cannot_go_around_the_gate(
    client: TestClient,
) -> None:
    agent = _key(client)
    _external()
    conv_id = _customer_writes("Can someone come and fix my boiler next week?")
    url = f"/agent/v1/conversations/{conv_id}/proposals"
    booking = {"kind": "propose_appointment", "params": {"service_code": "repair_visit"}}
    r = client.post(url, json=booking, headers=agent)
    assert r.status_code == 201 and r.json()["state"] == "awaiting"
    pid = r.json()["proposal_id"]
    assert pid in {p["id"] for p in client.get("/approvals", headers=OWNER).json()["items"]}
    assert client.get(f"/agent/v1/proposals/{pid}", headers=agent).json()["state"] == "awaiting"
    assert (
        client.post(f"/approvals/{pid}", json={"decision": "approve"}, headers=agent).status_code
        == 401
    )

    pay = {"kind": "collect_payment", "params": {"amount_minor": 5000, "currency": "GBP"}}
    assert client.post(url, json=pay, headers=agent).status_code == 422, "not a pack tool"
    unsafe = {"kind": "reply", "params": {"text": "Is your son home alone right now?"}}
    refused = client.post(url, json=unsafe, headers=agent).json()
    assert refused["state"] == "rejected" and "safeguarding" in refused["reason"]


def test_one_business_agent_cannot_see_another_business(client: TestClient) -> None:
    agent = _key(client)
    dental_conv = _customer_writes("I have toothache", slug="demo-dental")
    assert client.get(f"/agent/v1/conversations/{dental_conv}", headers=agent).status_code == 404
    waiting = client.get("/agent/v1/conversations", headers=agent).json()["items"]
    assert str(dental_conv) not in {w["conversation_id"] for w in waiting}


class _NoModel:
    def complete(self, **_: Any) -> Any:
        raise AssertionError("the built-in model must not answer in external mode")


def test_in_external_mode_the_built_in_model_is_quiet_but_the_emergency_check_still_runs(
    client: TestClient,
) -> None:
    _external()
    t = _tenant()
    pack = get_pack("hvac")
    quiet = _customer_writes("Can you service my boiler?")
    gas = _customer_writes("I can smell gas in the kitchen")
    with tenant_session(t.id) as s:
        r = run_turn(s, t, pack, _NoModel(), quiet)  # type: ignore[arg-type]
        assert r.skipped_reason == "external_agent" and r.reply_message_id is None
        e = run_turn(s, t, pack, _NoModel(), gas)  # type: ignore[arg-type]
        assert e.emergency and e.reply_message_id is not None
        reply = s.get(Message, e.reply_message_id)
        assert reply is not None and pack.emergency_reply.split(".")[0] in reply.body
        assert s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == gas, ActionProposal.kind == "escalate_emergency"
            )
        )
        conv = s.get(Conversation, quiet)
        assert conv is not None and conv.status == "open", "left for the agent"


def test_the_example_hermes_agent_works_against_the_real_api(client: TestClient) -> None:
    """examples/hermes_agent.py, one pass, with the model's answer scripted: it reads the
    waiting conversation, turns the model's tool calls into proposals, and the gate decides."""
    import importlib.util
    from pathlib import Path

    import httpx

    path = Path(__file__).resolve().parents[3] / "examples" / "hermes_agent.py"
    spec = importlib.util.spec_from_file_location("hermes_agent", path)
    assert spec is not None and spec.loader is not None
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)

    _external()
    conv_id = _customer_writes("Radiator in the hall is cold, can someone come?")
    seen: list[dict[str, Any]] = []

    def hermes(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Sorry about that. I've asked the team for a time.",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {
                                        "name": "propose_appointment",
                                        "arguments": json.dumps({"service_code": "repair_visit"}),
                                    },
                                },
                                {
                                    "id": "c2",
                                    "type": "function",
                                    "function": {"name": "reply", "arguments": "{not json"},
                                },
                            ],
                        }
                    }
                ]
            },
        )

    client.headers.update(_key(client))
    llm = httpx.Client(base_url="http://hermes.test/v1", transport=httpx.MockTransport(hermes))
    results = [r for r in example.run_once(client, llm, "hermes3") if r.get("proposal_id")]
    mine = [
        r for r in results if r["proposal_id"] and r["kind"] in ("propose_appointment", "reply")
    ]
    assert {r["kind"]: r["state"] for r in mine} == {
        "propose_appointment": "awaiting",
        "reply": "executed",
    }, "the malformed tool call was dropped; the text became the reply"
    assert any(
        m["role"] == "system" and "Business name" in m["content"] for m in seen[0]["messages"]
    )
    assert [t["function"]["name"] for t in seen[0]["tools"]][0] == "reply"
    with tenant_session(_tenant().id) as s:
        out = s.scalar(
            select(Message).where(
                Message.conversation_id == conv_id, Message.direction == "outbound"
            )
        )
        assert out is not None and out.body.startswith("Hi, I'm the AI assistant")


def test_the_platform_checks_the_built_in_assistant_gets_apply_to_an_agent_too(
    client: TestClient,
) -> None:
    """A reply refused by the gate hands over with the fixed notice; a reply claiming a
    booking with nothing behind it is flagged for staff; after a refused action the next
    reply says a person will follow up."""
    agent = _key(client)
    _external()
    pack = get_pack("hvac")

    def post(conv: uuid.UUID, kind: str, params: dict[str, Any]) -> dict[str, Any]:
        r = client.post(
            f"/agent/v1/conversations/{conv}/proposals",
            json={"kind": kind, "params": params},
            headers=agent,
        )
        assert r.status_code in (200, 201), r.text
        return dict(r.json())

    refused = _customer_writes("My son is 10, he's home alone and the boiler is off")
    assert post(refused, "reply", {"text": "Is he home alone now?"})["state"] == "rejected"
    claim = _customer_writes("Can you come Friday?")
    post(claim, "reply", {"text": "Great, I've booked you in for Friday at 9."})
    failed = _customer_writes("Boiler service please")
    bad = post(failed, "propose_appointment", {"service_code": "repair_visit", "oops": 1})
    assert bad["state"] == "rejected"
    post(failed, "reply", {"text": "Thanks, noted."})

    with tenant_session(_tenant().id) as s:

        def sent(conv_id: uuid.UUID) -> list[str]:
            return [
                m.body
                for m in s.scalars(
                    select(Message).where(
                        Message.conversation_id == conv_id, Message.direction == "outbound"
                    )
                )
            ]

        conv = s.get(Conversation, refused)
        assert conv is not None and conv.status == "waiting_human"
        assert sent(refused) == [pack.handoff_notice], "only the fixed notice went out"
        assert s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == claim,
                ActionProposal.kind == "verify_claim",
                ActionProposal.state == "awaiting",
            )
        ), "staff check the booking the reply claimed"
        assert pack.high_risk_followup in sent(failed)[-1]
