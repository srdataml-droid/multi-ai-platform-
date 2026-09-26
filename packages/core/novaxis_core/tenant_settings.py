"""Validated shape of `tenants.settings`.

Why a model and not free JSON: the worker reads these values on every turn, and a
typo in business hours must fail at save time in the dashboard, not at 2am in a
customer conversation. Packs extend this with their own fields via `pack` (Chunk 5).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    @field_validator("business_hours")
    @classmethod
    def _weekday_keys(cls, v: dict[str, DayHours]) -> dict[str, DayHours]:
        allowed = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        bad = set(v) - allowed
        if bad:
            raise ValueError(f"unknown weekday keys: {sorted(bad)}")
        return v

    @field_validator("risk_overrides")
    @classmethod
    def _risk_values(cls, v: dict[str, str]) -> dict[str, str]:
        bad = {k: r for k, r in v.items() if r not in ("low", "medium", "high")}
        if bad:
            raise ValueError(f"risk must be low, medium or high: {bad}")
        return v
