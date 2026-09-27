"""Which tenant does an inbound message belong to?

This runs before we know the tenant, so it is the one read that must use a
service session. It reads only `tenants.slug` and `tenants.settings.channels`.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novaxis_core.models import Tenant

log = logging.getLogger("novaxis.routing")

# channel -> the key inside settings.channels[channel].config that identifies the tenant
ROUTE_KEYS = {"twilio_sms": "number", "email": "inbound_address", "whatsapp": "phone_number_id"}
# Channels that share another channel's address: one Twilio number takes texts and calls.
ROUTE_ALIASES = {"twilio_voice": "twilio_sms"}


def resolve_tenant(session: Session, channel: str, tenant_ref: str) -> Tenant | None:
    if channel == "webchat":
        return session.scalar(select(Tenant).where(Tenant.slug == tenant_ref))
    channel = ROUTE_ALIASES.get(channel, channel)
    key = ROUTE_KEYS.get(channel)
    if key is None:
        return None
    ref = tenant_ref.strip().lower()
    if not ref:
        return None
    # Exact match, never a pattern: a "%" or "_" in an address must not match other businesses.
    # Unique indexes (migration 0013) mean at most one business holds each address; if that
    # ever fails, refuse rather than guess, because a guess hands one business's customers
    # to another.
    matches = list(
        session.scalars(
            select(Tenant)
            .where(func.lower(Tenant.settings["channels"][channel]["config"][key].astext) == ref)
            .limit(2)
        )
    )
    if len(matches) != 1:
        if matches:
            log.error(
                "routing: %d businesses claim %s %s; message refused", len(matches), channel, ref
            )
        return None
    return matches[0]


def keep_routing(new: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
    """`new` settings with the routing addresses from `old`. Owners change these only through
    onboarding (SMS number) or not at all (the inbound address is made from the slug)."""
    channels = {k: {**v, "config": dict(v.get("config") or {})} for k, v in new["channels"].items()}
    for channel, key in ROUTE_KEYS.items():
        before = ((old.get("channels") or {}).get(channel) or {}).get("config") or {}
        if channel not in channels:
            continue
        if before.get(key):
            channels[channel]["config"][key] = before[key]
        else:
            channels[channel]["config"].pop(key, None)
    return {**new, "channels": channels}


def claim_error(exc: IntegrityError) -> str | None:
    """A readable reason when a save broke a routing-address unique index, else None."""
    text = str(exc.orig)
    if "uq_tenants_sms_number" in text:
        return "That SMS number is already connected to another business."
    if "uq_tenants_inbound_email" in text:
        return "That inbound email address is already used by another business."
    if "uq_tenants_whatsapp_number" in text:
        return "That WhatsApp number is already connected to another business."
    return None
