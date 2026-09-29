"""Read a conversation: transcript and extracted fields, with sensitive fields revealed
only to staff-level roles. The dashboard's conversation page (Chunk 9) reads this."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.booking_types import sensitive_keys_for
from novaxis_core.media import media_view
from novaxis_core.models import Contact, Conversation, Message, Tenant
from novaxis_core.sensitive import reveal
from novaxis_packs import get_pack

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such conversation")
    tenant = session.scalar(select(Tenant))
    pack = get_pack(tenant.pack_id if tenant else "generic")
    contact = session.get(Contact, conv.contact_id)
    messages = list(
        session.scalars(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
        )
    )
    private = sensitive_keys_for(tenant, pack) if tenant else pack.sensitive_keys
    return {
        "id": str(conv.id),
        "channel": conv.channel,
        "status": conv.status,
        "summary": conv.summary,
        "contact": {
            "id": str(contact.id) if contact else None,
            "display_name": contact.display_name if contact else None,
            "consent": contact.consent if contact else {},
        },
        "extracted": reveal(conv.extracted, private, principal.role),
        "sensitive_keys": sorted(private),
        "messages": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "author": m.author,
                "body": m.body,
                "media": media_view(m.media) if m.media else [],
                "at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }
