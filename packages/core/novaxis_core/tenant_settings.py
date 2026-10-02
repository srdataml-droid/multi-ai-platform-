"""Validated shape of `tenants.settings`.

Why a model and not free JSON: the worker reads these values on every turn, and a
typo in business hours must fail at save time in the dashboard, not at 2am in a
customer conversation. Packs extend this with their own fields via `pack` (Chunk 5).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class Technician(BaseModel):
    """A field worker the scheduler may rely on for a service.

    This is deliberately smaller than dispatch: Phase 1 only needs to know whether at
    least one suitably skilled person is working that day before it offers a slot.
    """

    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=100)
    service_codes: list[str] = Field(min_length=1)
    working_days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])

    @field_validator("working_days")
    @classmethod
    def _working_days(cls, v: list[str]) -> list[str]:
        bad = set(v) - set(_WEEKDAYS)
        if bad:
            raise ValueError(f"unknown weekday keys: {sorted(bad)}")
        if not v:
            raise ValueError("a technician must work at least one day")
        return list(dict.fromkeys(v))


class ProtectedTime(BaseModel):
    """Time nobody can book, even when the diary is free: lunch, a school run, the team
    meeting, time to prepare quotes."""

    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=60)
    days: list[str] = Field(min_length=1)
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[str]) -> list[str]:
        bad = set(v) - set(_WEEKDAYS)
        if bad:
            raise ValueError(f"unknown weekday keys: {sorted(bad)}")
        return v

    @model_validator(mode="after")
    def _order(self) -> ProtectedTime:
        if self.end <= self.start:
            raise ValueError(f"{self.label}: the end ({self.end}) must be after the start")
        return self


class BookingRules(BaseModel):
    """Free is not the same as available. What the assistant may offer on top of the
    opening hours and the calendar's busy times."""

    model_config = ConfigDict(extra="forbid")
    min_notice_minutes: int = Field(
        default=30, ge=0, le=14 * 24 * 60, description="How soon a booking may start"
    )
    buffer_minutes: int = Field(
        default=0, ge=0, le=240, description="Gap kept free before and after other bookings"
    )
    max_per_day: int | None = Field(
        default=None, ge=1, le=100, description="Most bookings in one day; empty for no limit"
    )
    protected: list[ProtectedTime] = Field(default_factory=list)


class BookingQuestion(BaseModel):
    """One thing a business asks before this kind of booking, in its own words."""

    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$", description="Made from the question")
    ask: str = Field(min_length=3, max_length=300)
    type: Literal["text", "choice", "phone", "email", "postcode", "yesno", "window"] = "text"
    choices: list[str] = Field(default_factory=list)
    required: bool = True
    sensitive: bool = Field(
        default=False,
        description="Private (health, money): encrypted at rest, hidden from viewers and agents",
    )

    @model_validator(mode="after")
    def _choices(self) -> BookingQuestion:
        if self.type == "choice" and len([c for c in self.choices if c.strip()]) < 2:
            raise ValueError(f"'{self.ask}': a choice question needs at least two options")
        if self.type != "choice" and self.choices:
            raise ValueError(f"'{self.ask}': options are only for choice questions")
        return self


class BookingType(BaseModel):
    """A kind of booking and who may make it: a new customer's first visit, an existing
    customer's follow-up, a quote. Each asks its own questions and books its own service."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=60)
    who: Literal["anyone", "new", "existing"] = "anyone"
    service_code: str
    questions: list[BookingQuestion] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _keys(self) -> BookingType:
        keys = [q.key for q in self.questions]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        if dupes:
            raise ValueError(f"'{self.name}': two questions share the key {dupes}")
        if "booking_type" in keys:
            raise ValueError(f"'{self.name}': the key 'booking_type' is kept for choosing the type")
        return self


class Faq(BaseModel):
    """A question customers ask and the business's own answer. The assistant states facts
    about the business only from these and the settings above; anything else goes to a
    person (turn.fact_check)."""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=200)
    answer: str = Field(min_length=1, max_length=600)


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
    booking_rules: BookingRules = Field(default_factory=BookingRules)
    services: list[Service] = Field(default_factory=list)
    technicians: list[Technician] = Field(
        default_factory=list,
        description="Field workers, their service skills and normal working days. Empty keeps legacy shared-calendar scheduling.",
    )
    faqs: list[Faq] = Field(
        default_factory=list,
        max_length=60,
        description="What customers ask, answered by the business (Gas Safe number, fees...)",
    )
    booking_types: list[BookingType] = Field(
        default_factory=list,
        description="Empty: every customer is asked the trade's standard questions",
    )
    booking_type_question: str = Field(
        default="What can we help you with?",
        min_length=3,
        max_length=200,
        description="Asked first when more than one booking type fits the customer",
    )
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
    assistant: Literal["built_in", "external"] = Field(
        default="built_in",
        description="Who answers customers: the built-in assistant, or the business's own agent "
        "through the agent API (docs/agent-api.md). The emergency check runs either way.",
    )
    widget_origins: list[str] = Field(
        default_factory=list,
        description="Websites allowed to host the chat widget, e.g. https://www.example.co.uk. "
        "Empty means any site.",
    )

    @model_validator(mode="after")
    def _types_book_known_services(self) -> TenantSettings:
        codes = {svc.code for svc in self.services}
        for t in self.booking_types:
            if t.service_code not in codes:
                raise ValueError(f"booking type '{t.name}' books '{t.service_code}', not a service")
        names = [t.name.strip().lower() for t in self.booking_types]
        if len(names) != len(set(names)):
            raise ValueError("two booking types share a name")
        tech_codes = [t.code for t in self.technicians]
        if len(tech_codes) != len(set(tech_codes)):
            raise ValueError("two technicians share a code")
        for tech in self.technicians:
            unknown = sorted(set(tech.service_codes) - codes)
            if unknown:
                raise ValueError(
                    f"technician '{tech.name}' handles unknown services: {unknown}"
                )
        return self

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
        twa = v.get("twilio_whatsapp")
        if twa and twa.config.get("number"):
            number = routing_phone(str(twa.config["number"]).removeprefix("whatsapp:"))
            if number is None:
                raise ValueError("twilio_whatsapp number must be a full number like +14155238886")
            twa.config["number"] = number
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
        if wa and wa.config.get("update_template") is not None:
            from novaxis_core.channels.whatsapp import check_update_template

            wa.config["update_template"] = check_update_template(wa.config["update_template"])
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
