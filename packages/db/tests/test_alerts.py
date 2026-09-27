"""Staff alerts by browser push: who gets them, what counts as delivered, and the places
that must raise one (approval waiting, emergency, hand-over, expiry)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from novaxis_core.alerts import ALERT_JOB, alert_staff, set_push_sender
from novaxis_core.approvals import expire_stale_proposals
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM
from novaxis_core.models import (
    ActionProposal,
    Conversation,
    Job,
    Location,
    Message,
    PushSubscription,
    Tenant,
    User,
)
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack


class FakePush:
    def __init__(self, status: int = 201) -> None:
        self.status = status
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, sub: dict[str, Any], payload: str) -> int:
        self.sent.append((sub["endpoint"], json.loads(payload)))
        return self.status


@pytest.fixture
def push(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("NOVAXIS_VAPID_PUBLIC_KEY", "BPub")
    monkeypatch.setenv("NOVAXIS_VAPID_PRIVATE_KEY", "priv")
    from novaxis_core.settings import get_settings

    get_settings.cache_clear()
    fake = FakePush()
    set_push_sender(fake)
    yield fake
    set_push_sender(None)


@pytest.fixture
def shop(migrated: str) -> dict[str, Any]:
    """A fresh HVAC business with an owner, a staff member and a viewer."""
    with service_session(migrated) as s:
        seed(s)
        demo = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert demo is not None
        t = Tenant(
            name="Alert Heating",
            slug=f"alert-{uuid.uuid4().hex[:8]}",
            pack_id="hvac",
            status="active",
            # Web chat only: sharing demo-hvac's SMS number or inbound address would make
            # inbound routing ambiguous for every later test.
            settings={
                **demo.settings,
                "channels": {"webchat": demo.settings["channels"]["webchat"]},
            },
        )
        s.add(t)
        s.flush()
        s.add(Location(tenant_id=t.id, name="Main"))
        users = {}
        for role in ("owner", "staff", "viewer"):
            u = User(
                tenant_id=t.id,
                auth_subject=f"x|{uuid.uuid4().hex}",
                email=f"{role}-{uuid.uuid4().hex[:6]}@a.test",
                role=role,
            )
            s.add(u)
            s.flush()
            users[role] = u.id
        s.expunge(t)
        return {"tenant": t, "users": users}


def _subscribe(tid: uuid.UUID, user_id: uuid.UUID) -> str:
    endpoint = f"https://push.example/{uuid.uuid4().hex}"
    with tenant_session(tid) as s:
        s.add(
            PushSubscription(
                tenant_id=tid, user_id=user_id, endpoint=endpoint, p256dh="p" * 20, auth="a" * 12
            )
        )
    return endpoint


def test_owners_and_staff_get_alerts_viewers_do_not(shop: dict[str, Any], push: FakePush) -> None:
    t, u = shop["tenant"], shop["users"]
    owner_ep = _subscribe(t.id, u["owner"])
    staff_ep = _subscribe(t.id, u["staff"])
    _subscribe(t.id, u["viewer"])
    with tenant_session(t.id) as s:
        n = alert_staff(s, t, "Approval needed", "x", "/approvals")
    assert n == 2
    assert {ep for ep, _ in push.sent} == {owner_ep, staff_ep}
    assert push.sent[0][1]["url"] == "/approvals"


def test_a_device_that_unsubscribed_is_forgotten(shop: dict[str, Any], push: FakePush) -> None:
    t, u = shop["tenant"], shop["users"]
    _subscribe(t.id, u["owner"])
    push.status = 410
    with tenant_session(t.id) as s:
        assert alert_staff(s, t, "x", "y", "/") == 0
    with tenant_session(t.id) as s:
        assert s.scalar(select(func.count()).select_from(PushSubscription)) == 0


def test_without_keys_nothing_is_pushed(shop: dict[str, Any]) -> None:
    t, u = shop["tenant"], shop["users"]
    _subscribe(t.id, u["owner"])
    with tenant_session(t.id) as s:
        assert alert_staff(s, t, "x", "y", "/") == 0


def _conversation(t: Tenant, body: str) -> uuid.UUID:
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        return ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:1",
                tenant_ref=t.slug,
                sender_visitor_id=v,
                body=body,
            ),
        ).conversation_id


def test_an_emergency_pushed_to_a_phone_counts_as_alerted(
    shop: dict[str, Any], push: FakePush
) -> None:
    t, u = shop["tenant"], shop["users"]
    _subscribe(t.id, u["owner"])
    conv_id = _conversation(t, "I can smell gas in the hallway")
    with tenant_session(t.id) as s:
        r = run_turn(s, t, get_pack("hvac"), FakeLLM(script=[]), conv_id)
        reply = s.get(Message, r.reply_message_id)
        esc = s.scalar(
            select(ActionProposal).where(
                ActionProposal.kind == "escalate_emergency",
                ActionProposal.conversation_id == conv_id,
            )
        )
        assert esc is not None and esc.state == "executed"
        assert reply is not None and "I have alerted our on-call engineer" in reply.body
    urgent = [p for _, p in push.sent if p["urgent"]]
    assert urgent and urgent[0]["url"] == f"/conversations/{conv_id}"
    assert "gas" not in urgent[0]["body"].lower(), "no customer words on a lock screen"


def test_a_waiting_approval_reaches_the_team(shop: dict[str, Any], push: FakePush) -> None:
    from novaxis_core.notify import notify_staff

    t, u = shop["tenant"], shop["users"]
    _subscribe(t.id, u["staff"])
    conv_id = _conversation(t, "hi")
    with tenant_session(t.id) as s:
        p = ActionProposal(
            tenant_id=t.id,
            conversation_id=conv_id,
            kind="propose_appointment",
            params={},
            risk="medium",
            state="awaiting",
        )
        s.add(p)
        s.flush()
        assert notify_staff(s, t, p.id) >= 1
    assert push.sent[-1][1]["title"] == "Approval needed"


def _alert_jobs(tid: uuid.UUID) -> int:
    with tenant_session(tid) as s:
        return s.scalar(select(func.count()).where(Job.kind == ALERT_JOB)) or 0


def test_a_refused_reply_hands_over_and_queues_an_alert(shop: dict[str, Any]) -> None:
    t = shop["tenant"]
    conv_id = _conversation(t, "he threatened me at the door")
    before = _alert_jobs(t.id)
    with tenant_session(t.id) as s:
        run_turn(s, t, get_pack("hvac"), FakeLLM(script=[("ok", [])]), conv_id)
    with tenant_session(t.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"
    assert _alert_jobs(t.id) == before + 1


def test_an_approval_nobody_decides_expires_and_the_team_is_told(shop: dict[str, Any]) -> None:
    t = shop["tenant"]
    conv_id = _conversation(t, "hello")
    with tenant_session(t.id) as s:
        old = ActionProposal(
            tenant_id=t.id,
            conversation_id=conv_id,
            kind="propose_appointment",
            params={},
            risk="medium",
            state="awaiting",
            created_at=datetime.now(UTC) - timedelta(hours=80),
        )
        fresh = ActionProposal(
            tenant_id=t.id,
            conversation_id=conv_id,
            kind="reply",
            params={"text": "x"},
            risk="medium",
            state="awaiting",
        )
        s.add_all([old, fresh])
        s.flush()
        old_id, fresh_id = old.id, fresh.id
    before = _alert_jobs(t.id)
    with service_session() as s:
        assert expire_stale_proposals(s, datetime.now(UTC)) >= 1
    with tenant_session(t.id) as s:
        assert s.get(ActionProposal, old_id).state == "expired"  # type: ignore[union-attr]
        assert s.get(ActionProposal, fresh_id).state == "awaiting"  # type: ignore[union-attr]
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"
    assert _alert_jobs(t.id) == before + 1
