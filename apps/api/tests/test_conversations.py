from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM, ToolCall
from novaxis_core.models import Tenant, User
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack


@pytest.fixture
def client(migrated: str) -> TestClient:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t is not None
        if s.scalar(select(User).where(User.auth_subject == "dev|viewer@demo-dental")) is None:
            s.add(
                User(
                    tenant_id=t.id,
                    auth_subject="dev|viewer@demo-dental",
                    email="viewer@demo-dental.test",
                    role="viewer",
                )
            )
    return TestClient(create_app())


def _conversation_with_symptom() -> uuid.UUID:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t is not None
        s.expunge(t)
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        conv_id = ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:x",
                tenant_ref="demo-dental",
                sender_visitor_id=v,
                body="toothache",
            ),
        ).conversation_id
    fake = FakeLLM(
        script=[
            (
                "Your name?",
                [
                    ToolCall(
                        "extract_fields",
                        {"fields": {"reason": "pain", "symptom": "sharp pain top right"}},
                        "t",
                    )
                ],
            )
        ]
    )
    with tenant_session(t.id) as s:
        run_turn(s, t, get_pack("dental"), fake, conv_id)
    return conv_id


def test_staff_sees_symptom_viewer_sees_redacted(client: TestClient) -> None:
    conv_id = _conversation_with_symptom()
    owner = client.get(
        f"/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {mint('dev|owner@demo-dental')}"},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["extracted"]["symptom"] == "sharp pain top right"
    assert owner.json()["extracted"]["reason"] == "pain"
    viewer = client.get(
        f"/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {mint('dev|viewer@demo-dental')}"},
    )
    assert viewer.status_code == 200
    assert viewer.json()["extracted"]["symptom"] == "[redacted]"
    assert viewer.json()["extracted"]["reason"] == "pain"
    assert "symptom" in viewer.json()["sensitive_keys"]


def test_other_tenant_cannot_read_it(client: TestClient) -> None:
    conv_id = _conversation_with_symptom()
    r = client.get(
        f"/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"},
    )
    assert r.status_code == 404
