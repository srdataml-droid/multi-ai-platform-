"""Validated shape of `tenants.settings`.

Why a model and not free JSON: the worker reads these values on every turn, and a
typo in business hours must fail at save time in the dashboard, not at 2am in a
customer conversation. Packs extend this with their own fields via `pack` (Chunk 5).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from novaxis_core.identifiers import normalize_email, routing_phone


class DayHours(BaseModel):
    """Opening hours for one weekday, 24h clock, local to the location."""

    model_config = ConfigDict(extra="forbid")
    open: str = Field(pattern=r"^\d{2}:\d{2}$")
    close: str = Field(pattern=r"^\d{2}:\d{2}$")


class EscalationContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    phone: str | None = None
    email: str | None = None
    role: str = "on_call"


class Service(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    duration_minutes: int = Field(ge=5, le=480)
    auto_confirm: bool = False


class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class TenantSettings(BaseModel):
    """Everything a tenant can configure without a code change."""

    model_config = ConfigDict(extra="forbid")

    pack_id: str
    timezone: str = "Europe/London"
    business_hours: dict[str, DayHours] = Field(default_factory=dict)
    services: list[Service] = Field(default_factory=list)
    service_area: list[str] = Field(
        default_factory=list, description="Postcode or ZIP prefixes the business serves"
    )
    escalation_contacts: list[EscalationContact] = Field(default_factory=list)
    risk_overrides: dict[str, str] = Field(
        default_factory=dict, description="action kind -> risk, within the pack's allowed range"
    )
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    tone: str = "friendly, brief, plain English"
    disclosure_text: str = (
        "Hi, I'm the AI assistant for {business_name}. A member of the team can step in "
        "at any time. How can I help?"
    )
    pack: dict[str, Any] = Field(default_factory=dict, description="Pack-specific settings")
    retention_days: int = Field(
        default=730,
        ge=30,
        le=3650,
        description="Customers with no conversation or booking for this many days are deleted, "
        "with their messages, bookings and photos. Set it from your own retention policy.",
    )
    privacy_url: str | None = Field(
        default=None,
        description="Your privacy notice. Linked in the assistant's first reply to each customer.",
    )
    widget_origins: list[str] = Field(
        default_factory=list,
        description="Websites allowed to host the chat widget, e.g. https://www.example.co.uk. "
        "Empty means any site.",
    )

    @field_validator("business_hours")
    @classmethod
    def _weekday_keys(cls, v: dict[str, DayHours]) -> dict[str, DayHours]:
        allowed = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        bad = set(v) - allowed
        if bad:
            raise ValueError(f"unknown weekday keys: {sorted(bad)}")
        return v

    @field_validator("channels")
    @classmethod
    def _routing_addresses(cls, v: dict[str, ChannelConfig]) -> dict[str, ChannelConfig]:
        """The SMS number and inbound address decide which business receives a message, so
        they are stored in one canonical form; the database keeps each one unique."""
        sms = v.get("twilio_sms")
        if sms and sms.config.get("number"):
            number = routing_phone(str(sms.config["number"]))
            if number is None:
                raise ValueError("twilio_sms number must be a full number like +447700900123")
            sms.config["number"] = number
        email = v.get("email")
        if email and email.config.get("inbound_address"):
            address = normalize_email(str(email.config["inbound_address"]))
            if address is None:
                raise ValueError("email inbound_address must be an email address")
            email.config["inbound_address"] = address
        wa = v.get("whatsapp")
        if wa and wa.config.get("phone_number_id"):
            pid = str(wa.config["phone_number_id"]).strip()
            if not pid.isdigit():
                raise ValueError("whatsapp phone_number_id is the number id from Meta (digits)")
            wa.config["phone_number_id"] = pid
        return v

    @field_validator("privacy_url")
    @classmethod
    def _privacy_url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not re.fullmatch(r"https://[^\s<>\"']+", v):
            raise ValueError("the privacy notice link must start with https://")
        return v

    @field_validator("widget_origins")
    @classmethod
    def _origins(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            o = raw.strip().rstrip("/").lower()
            if not re.fullmatch(r"https?://[a-z0-9.-]+(:\d{1,5})?", o):
                raise ValueError(f"{raw!r} is not a website address like https://www.example.com")
            if o not in out:
                out.append(o)
        return out

    @field_validator("risk_overrides")
    @classmethod
    def _risk_values(cls, v: dict[str, str]) -> dict[str, str]:
        bad = {k: r for k, r in v.items() if r not in ("low", "medium", "high")}
        if bad:
            raise ValueError(f"risk must be low, medium or high: {bad}")
        return v
