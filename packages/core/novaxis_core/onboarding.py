"""Turn the onboarding wizard's answers into a validated `TenantSettings`.

Why a separate shape: the wizard asks a business owner plain questions (what are your
hours, who is on call, which number do customers text). `TenantSettings` is the full
worker configuration. `build_settings` is the one mapping between them, a pure function
so it is tested per pack without a database or a browser.
"""

from __future__ import annotations

import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novaxis_core.packspec import PackSpec
from novaxis_core.tenant_settings import (
    ChannelConfig,
    DayHours,
    EscalationContact,
    Service,
    TenantSettings,
)

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class OnCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, pattern=r"^\+[1-9]\d{6,14}$")
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    @model_validator(mode="after")
    def _reachable(self) -> OnCall:
        if not self.phone and not self.email:
            raise ValueError("the on-call contact needs a phone number or an email address")
        return self


class Wizard(BaseModel):
    """Everything the wizard collects. Closed days are simply absent from `business_hours`."""

    model_config = ConfigDict(extra="forbid")
    business_name: str = Field(min_length=1, max_length=200)
    timezone: str = "Europe/London"
    business_hours: dict[str, DayHours] = Field(default_factory=dict)
    services: list[Service] = Field(min_length=1)
    service_area: list[str] = Field(default_factory=list)
    webchat: bool = True
    sms_number: str | None = Field(default=None, pattern=r"^\+[1-9]\d{6,14}$")
    email_from: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    on_call: OnCall

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone {v!r}") from exc
        return v

    @field_validator("service_area")
    @classmethod
    def _prefixes(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            p = re.sub(r"\s+", "", raw).upper()
            if not p:
                continue
            if not re.fullmatch(r"[A-Z0-9]{1,8}", p):
                raise ValueError(f"{raw!r} is not a postcode or ZIP prefix")
            if p not in out:
                out.append(p)
        return out

    @field_validator("business_hours")
    @classmethod
    def _open_before_close(cls, v: dict[str, DayHours]) -> dict[str, DayHours]:
        for day, h in v.items():
            if day not in WEEKDAYS:
                raise ValueError(f"unknown weekday {day!r}")
            if h.open >= h.close:
                raise ValueError(f"{day}: opening time must be before closing time")
        return v

    @field_validator("services")
    @classmethod
    def _unique_codes(cls, v: list[Service]) -> list[Service]:
        codes = [s.code for s in v]
        if len(codes) != len(set(codes)):
            raise ValueError("each service needs its own code")
        return v


def defaults_for(pack: PackSpec, business_name: str = "") -> dict[str, Any]:
    """What the wizard shows before the owner changes anything."""
    return Wizard.model_construct(
        business_name=business_name,
        timezone="Europe/London",
        business_hours={d: DayHours(open="08:00", close="18:00") for d in WEEKDAYS[:5]},
        services=[Service.model_validate(s) for s in pack.manifest.get("default_services", [])],
        service_area=list(pack.manifest.get("default_service_area", [])),
        webchat=True,
        sms_number=None,
        email_from=None,
        on_call=OnCall.model_construct(name="", phone=None, email=None),
    ).model_dump()


def build_settings(
    pack: PackSpec, wizard: Wizard, *, slug: str, inbound_email_domain: str
) -> TenantSettings:
    """The complete worker configuration for a newly onboarded tenant."""
    channels = {
        "webchat": ChannelConfig(enabled=wizard.webchat),
        "twilio_sms": ChannelConfig(
            enabled=wizard.sms_number is not None,
            config={"number": wizard.sms_number} if wizard.sms_number else {},
        ),
        "email": ChannelConfig(
            enabled=wizard.email_from is not None,
            config={
                "inbound_address": f"{slug}@{inbound_email_domain}",
                "from_address": wizard.email_from,
            }
            if wizard.email_from
            else {},
        ),
    }
    known = set(pack.manifest.get("channels") or channels)
    for name, ch in channels.items():
        if ch.enabled and name not in known:
            raise ValueError(f"the {pack.name} pack does not support the {name} channel")
    return TenantSettings(
        pack_id=pack.id,
        timezone=wizard.timezone,
        business_hours=wizard.business_hours,
        services=wizard.services,
        service_area=wizard.service_area,
        escalation_contacts=[
            EscalationContact(
                name=wizard.on_call.name, phone=wizard.on_call.phone, email=wizard.on_call.email
            )
        ],
        channels=channels,
    )


def wizard_from_settings(name: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Re-open the wizard on an existing configuration (the owner comes back to step 3)."""
    ts = TenantSettings.model_validate(settings)
    oc = ts.escalation_contacts[0] if ts.escalation_contacts else None
    sms = ts.channels.get("twilio_sms")
    email = ts.channels.get("email")
    web = ts.channels.get("webchat")
    return {
        "business_name": name,
        "timezone": ts.timezone,
        "business_hours": {k: v.model_dump() for k, v in ts.business_hours.items()},
        "services": [s.model_dump() for s in ts.services],
        "service_area": ts.service_area,
        "webchat": bool(web and web.enabled),
        "sms_number": sms.config.get("number") if sms and sms.enabled else None,
        "email_from": email.config.get("from_address") if email and email.enabled else None,
        "on_call": {
            "name": oc.name if oc else "",
            "phone": oc.phone if oc else None,
            "email": oc.email if oc else None,
        },
    }
