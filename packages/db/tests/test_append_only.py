"""messages and audit_log accept inserts and refuse updates and deletes from the app role."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import ProgrammingError

from novaxis_core.models import AuditLog, Contact, Conversation, Message
from novaxis_db import audit
from novaxis_db.session import tenant_session


def _seed_message(tenant_id: uuid.UUID) -> uuid.UUID:
    with tenant_session(tenant_id) as s:
        c = Contact(tenant_id=tenant_id, display_name="Alice")
        s.add(c)
        s.flush()
        conv = Conversation(tenant_id=tenant_id, contact_id=c.id, channel="webchat")
        s.add(conv)
        s.flush()
        m = Message(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            direction="inbound",
            channel="webchat",
            author="customer",
            body="hi",
        )
        s.add(m)
        s.flush()
        return m.id


def test_messages_cannot_be_updated(two_tenants: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, _ = two_tenants
    mid = _seed_message(a)
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(a) as s:
            s.execute(update(Message).where(Message.id == mid).values(body="edited"))


def test_messages_cannot_be_deleted(two_tenants: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, _ = two_tenants
    mid = _seed_message(a)
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(a) as s:
            s.execute(delete(Message).where(Message.id == mid))


def test_audit_record_writes_and_is_immutable(two_tenants: tuple[uuid.UUID, uuid.UUID]) -> None:
    a, _ = two_tenants
    with tenant_session(a) as s:
        row = audit.record(
            s, tenant_id=a, actor="test", event="contact.created", diff={"name": "Alice"}
        )
        rid = row.id
    with tenant_session(a) as s:
        assert s.scalar(select(AuditLog).where(AuditLog.id == rid)).event == "contact.created"  # type: ignore[union-attr]
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(a) as s:
            s.execute(update(AuditLog).where(AuditLog.id == rid).values(event="tampered"))
