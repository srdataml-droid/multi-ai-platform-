"""Booking types: each business sets what it books, for whom, and what it asks first.

A new patient and an existing one see different types; with more than one to choose from
the customer is asked which, and that answer brings that type's own questions and books
that type's service. Businesses without types keep their trade's standard questions."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from novaxis_api.main import create_app
from novaxis_core.booking_types import TYPE_KEY, intake_for, starter_type
from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM
from novaxis_core.models import ActionProposal, Appointment, Conversation, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.tenant_settings import TenantSettings
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

DENTAL = get_pack("dental")
TYPES = [
    {
        "name": "Emergency appointment",
        "who": "anyone",
        "service_code": "emergency",
        "questions": [
            {"key": "name", "ask": "What's your name?"},
            {"key": "pain", "ask": "Where does it hurt?"},
        ],
    },
    {
        "name": "New patient check-up",
        "who": "new",
        "service_code": "checkup",
        "questions": [
            {"key": "name", "ask": "What's your name?"},
            {"key": "phone", "ask": "Best number to reach you?", "type": "phone"},
            {"key": "when", "ask": "When suits you?", "type": "window"},
        ],
    },
    {
        "name": "Hygienist visit",
        "who": "existing",
        "service_code": "hygiene",
        "questions": [{"key": "when", "ask": "When suits you?", "type": "window"}],
    },
]


@pytest.fixture
def dental(migrated: str, monkeypatch: pytest.MonkeyPatch) -> Tenant:
    monkeypatch.setenv("NOVAXIS_INTAKE_EXTRACTION", "true")
    get_settings.cache_clear()
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t is not None
        t.settings = {**json.loads(json.dumps(t.settings)), "booking_types": TYPES}
        s.flush()
        s.expunge(t)
    yield t
    with service_session() as s:  # other tests expect the seeded questions
        t2 = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t2 is not None
        t2.settings = {k: v for k, v in t2.settings.items() if k != "booking_types"}
    get_settings.cache_clear()


def _customer(t: Tenant, text: str) -> tuple[uuid.UUID, uuid.UUID]:
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        r = ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref=t.slug,
                sender_visitor_id=v,
                body=text,
            ),
        )
        return r.conversation_id, r.contact_id


def _intake(t: Tenant, conv_id: uuid.UUID, plain: dict[str, str]):  # type: ignore[no-untyped-def]
    with tenant_session(t.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        return intake_for(s, t, DENTAL, conv, plain)


def test_new_and_existing_customers_see_different_types(dental: Tenant) -> None:
    conv_new, _ = _customer(dental, "Hi")
    first = _intake(dental, conv_new, {})
    assert first.questions[0].key == TYPE_KEY and first.type_name is None
    assert first.questions[0].choices == ["Emergency appointment", "New patient check-up"]

    conv_old, contact = _customer(dental, "Hi again")
    with tenant_session(dental.id) as s:
        start = datetime.now(UTC) - timedelta(days=30)
        s.add(
            Appointment(
                tenant_id=dental.id,
                contact_id=contact,
                starts_at=start,
                ends_at=start + timedelta(minutes=20),
                service_code="checkup",
                status="confirmed",
            )
        )
    assert _intake(dental, conv_old, {}).questions[0].choices == [
        "Emergency appointment",
        "Hygienist visit",
    ]

    chosen = _intake(dental, conv_new, {TYPE_KEY: "new patient CHECK-UP"})
    assert chosen.type_name == "New patient check-up" and chosen.service_code == "checkup"
    assert [q.key for q in chosen.questions] == [TYPE_KEY, "name", "phone", "when"]
    assert chosen.window_from == "when"


def test_one_message_picks_the_type_and_answers_its_questions(dental: Tenant) -> None:
    """The customer says everything at once. The first pass can only read the type (its
    questions are not known yet); the second reads that type's questions from the same
    message. The booking is for that type's service, and staff see which type it is."""
    conv_id, _ = _customer(
        dental, "I'm new here, I'd like a check-up. I'm Ann, 07700 900111, Monday morning."
    )
    llm = FakeLLM(
        script=[
            (json.dumps({TYPE_KEY: "New patient check-up", "name": "Ann"}), []),
            (json.dumps({"name": "Ann", "phone": "07700 900111", "when": "Monday morning"}), []),
            ("Thanks Ann, the team will confirm a time.", []),
        ]
    )
    from novaxis_core.turn import run_turn

    with tenant_session(dental.id) as s:
        run_turn(s, dental, DENTAL, llm, conv_id)
        booked = s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id,
                ActionProposal.kind == "propose_appointment",
            )
        )
        assert booked is not None and booked.state == "awaiting"
        assert booked.params["service_code"] == "checkup"
        assert booked.params["preferred_window"] == "Monday morning"
        assert booked.params["notes"].startswith("New patient check-up")
    assert "The customer is booking: New patient check-up." in llm.calls[2]["system_volatile"]


def test_businesses_without_types_keep_their_trade_questions(dental: Tenant) -> None:
    plain_tenant = Tenant(
        slug=dental.slug,
        name=dental.name,
        pack_id="dental",
        settings={k: v for k, v in dental.settings.items() if k != "booking_types"},
    )
    conv_id, _ = _customer(dental, "Hi")
    with tenant_session(dental.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        got = intake_for(s, plain_tenant, DENTAL, conv, {})
    assert [q.key for q in got.questions] == [q.key for q in DENTAL.intake]
    assert got.type_name is None


def test_types_are_checked_when_saved() -> None:
    base = {
        "pack_id": "dental",
        "services": [{"code": "checkup", "name": "Check-up", "duration_minutes": 20}],
    }
    ok = TenantSettings.model_validate({**base, "booking_types": [TYPES[1]]})
    assert ok.booking_types[0].who == "new"
    one = {"name": "X visit", "service_code": "checkup", "questions": [{"key": "a", "ask": "Why?"}]}
    for bad, words in (
        ({**one, "service_code": "nope"}, "not a service"),
        (
            {
                **one,
                "questions": [{"key": "a", "ask": "Pick?", "type": "choice", "choices": ["A"]}],
            },
            "two options",
        ),
        ({**one, "questions": [{"key": "booking_type", "ask": "Which?"}]}, "kept for choosing"),
        (
            {**one, "questions": [{"key": "a", "ask": "Why?"}, {"key": "a", "ask": "Why not?"}]},
            "share the key",
        ),
    ):
        with pytest.raises(ValidationError, match=words):
            TenantSettings.model_validate({**base, "booking_types": [bad]})
    with pytest.raises(ValidationError, match="share a name"):
        TenantSettings.model_validate({**base, "booking_types": [one, {**one, "name": "x VISIT"}]})


def test_the_starter_is_the_trades_own_questions_and_saves() -> None:
    services = [{"code": "checkup", "name": "Check-up", "duration_minutes": 20}]
    starter = starter_type(DENTAL, services)
    assert [q["key"] for q in starter["questions"]] == [q.key for q in DENTAL.intake]
    TenantSettings.model_validate(
        {"pack_id": "dental", "services": services, "booking_types": [starter]}
    )


def test_owners_save_types_in_settings(migrated: str) -> None:
    with service_session(migrated) as s:
        seed(s)
    c = TestClient(create_app())
    token = c.post("/auth/dev-login", json={"email": "owner@demo-dental.test"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    cur = c.get("/settings", headers=h).json()
    assert cur["starter_booking_type"]["questions"], "the trade's questions, to start from"
    settings = {**cur["settings"], "booking_types": TYPES}
    r = c.put("/settings", json={"settings": settings}, headers=h)
    assert r.status_code == 200, r.text
    assert [t["name"] for t in r.json()["settings"]["booking_types"]] == [t["name"] for t in TYPES]
    settings["booking_types"] = [{**TYPES[0], "service_code": "nope"}]
    r = c.put("/settings", json={"settings": settings}, headers=h)
    assert r.status_code == 422 and "not a service" in r.text
    settings["booking_types"] = []
    assert c.put("/settings", json={"settings": settings}, headers=h).status_code == 200


PRIVATE = {
    "name": "New patient check-up",
    "who": "anyone",
    "service_code": "checkup",
    "questions": [
        {"key": "name", "ask": "What's your name?"},
        {
            "key": "conditions",
            "ask": "Any medical conditions we should know about?",
            "sensitive": True,
        },
        {"key": "when", "ask": "When suits you?", "type": "window"},
    ],
}


def _set_types(t: Tenant, types: list[dict[str, object]]) -> None:
    with service_session() as s:
        row = s.get(Tenant, t.id)
        assert row is not None
        row.settings = {**row.settings, "booking_types": types}
    t.settings = {**t.settings, "booking_types": types}


def _login(c: TestClient, email: str) -> dict[str, str]:
    token = c.post("/auth/dev-login", json={"email": email}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_private_custom_answer_is_encrypted_and_only_staff_read_it(dental: Tenant) -> None:
    from novaxis_core.agent import context

    _set_types(dental, [PRIVATE])
    conv_id, _ = _customer(dental, "I'm Ann, I have asthma, Monday morning please.")
    llm = FakeLLM(
        script=[
            (json.dumps({"name": "Ann", "conditions": "asthma", "when": "Monday morning"}), []),
            ("Thanks Ann.", []),
        ]
    )
    from novaxis_core.turn import run_turn

    with tenant_session(dental.id) as s:
        run_turn(s, dental, DENTAL, llm, conv_id)
        booked = s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id,
                ActionProposal.kind == "propose_appointment",
            )
        )
        assert booked is not None, "the assistant read the encrypted answer as complete"
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        agent_view = context(s, dental, DENTAL, conv)["intake"]["answers"]
    with service_session() as s:
        raw = s.get(Conversation, conv_id)
        assert raw is not None
        assert raw.extracted["conditions"].startswith("enc:v1:"), "encrypted at rest"
        assert raw.extracted["name"] == "Ann", "only the private answer"
    assert agent_view["conditions"] == "(held by the business)"

    c = TestClient(create_app())
    owner = c.get(f"/conversations/{conv_id}", headers=_login(c, "owner@demo-dental.test")).json()
    viewer = c.get(f"/conversations/{conv_id}", headers=_login(c, "viewer@demo-dental.test")).json()
    assert owner["extracted"]["conditions"] == "asthma"
    assert viewer["extracted"]["conditions"] == "[redacted]"
    assert "conditions" in owner["sensitive_keys"]


def test_ticking_private_later_encrypts_answers_already_given(dental: Tenant) -> None:
    open_type = {**PRIVATE, "questions": [{**q, "sensitive": False} for q in PRIVATE["questions"]]}
    _set_types(dental, [open_type])
    conv_id, _ = _customer(dental, "hi")
    with tenant_session(dental.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        conv.extracted = {"name": "Bo", "conditions": "diabetes"}

    c = TestClient(create_app())
    h = _login(c, "owner@demo-dental.test")
    settings = c.get("/settings", headers=h).json()["settings"]
    settings["booking_types"] = [PRIVATE]
    r = c.put("/settings", json={"settings": settings}, headers=h)
    assert r.status_code == 200, r.text
    with service_session() as s:
        raw = s.get(Conversation, conv_id)
        assert raw is not None and raw.extracted["conditions"].startswith("enc:v1:")

    # Unticked again: the stored answer stays encrypted but staff can still read it.
    settings["booking_types"] = [open_type]
    assert c.put("/settings", json={"settings": settings}, headers=h).status_code == 200
    got = c.get(f"/conversations/{conv_id}", headers=h).json()["extracted"]
    assert got["conditions"] == "diabetes"
    viewer = c.get(f"/conversations/{conv_id}", headers=_login(c, "viewer@demo-dental.test"))
    assert viewer.json()["extracted"]["conditions"] == "[redacted]", "still encrypted: still hidden"
