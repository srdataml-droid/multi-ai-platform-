"""The pack contract: what a vertical pack is, as validated data.

A pack is a folder (see `packs.py` for the loader). This module holds the shapes
so that core code, the loader and tests agree. Packs contain no core code; the
one hook is `rules.py`, which may define `classify(kind, params, ctx)` for the
gate and `is_emergency(text)` for the pre-check.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from novaxis_core.actions import ACTIONS

PackRule = Callable[[str, dict[str, Any], Any], str | None]
EmergencyCheck = Callable[[str], bool]


class IntakeQuestion(BaseModel):
    """One thing the worker needs to learn. `key` is the extracted field name."""

    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    ask: str
    type: Literal["text", "choice", "phone", "email", "postcode", "yesno", "window"] = "text"
    choices: list[str] = Field(default_factory=list)
    required: bool = True
    sensitive: bool = False
    skip_if: dict[str, str] = Field(
        default_factory=dict, description="Skip when every listed key equals the given value"
    )
    pattern: str | None = Field(default=None, description="Regex the value must match")

    @field_validator("choices")
    @classmethod
    def _choices_only_for_choice(cls, v: list[str], info: Any) -> list[str]:
        if v and info.data.get("type") != "choice":
            raise ValueError("choices are only valid for type=choice")
        return v


class WorkflowStep(BaseModel):
    """Something that happens later, without a customer message to trigger it."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    trigger: Literal[
        "conversation_idle", "intake_complete", "appointment_confirmed", "before_appointment"
    ]
    after: str = Field(description="Delay like 30m, 24h, 3d", pattern=r"^\d+[mhd]$")
    action: Literal["send_message", "close_conversation"]
    template: str = ""
    only_if_status: list[str] = Field(default_factory=lambda: ["waiting_customer"])


class DashboardColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    label: str
    source: Literal["extracted", "contact", "conversation"] = "extracted"


class DashboardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inbox_columns: list[DashboardColumn] = Field(default_factory=list)
    work_queue_buckets: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)


class AfterIntake(BaseModel):
    """What to do when every required question is answered."""

    model_config = ConfigDict(extra="forbid")
    action: Literal["propose_appointment", "hand_to_human", "none"] = "propose_appointment"
    service_code_from: str | None = Field(
        default=None, description="Extracted key whose value maps to a service code"
    )
    service_code_map: dict[str, str] = Field(default_factory=dict)
    default_service_code: str = ""
    window_from: str = "preferred_window"


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    version: str = "0.1"
    tools: list[str] = Field(description="Action kinds the model may propose")
    channels: list[str] = Field(default_factory=lambda: ["webchat", "twilio_sms", "email"])
    intake_opening: str
    emergency_keywords: list[str] = Field(default_factory=list)
    emergency_reply: str = ""
    high_risk_followup: str = "A member of the team will follow up with you on that directly."
    handoff_notice: str = (
        "Thanks for your message. A member of the team will be in touch with you shortly."
    )
    service_area_field: str | None = None
    out_of_area_reply: str = ""
    after_intake: AfterIntake = Field(default_factory=AfterIntake)
    risk_overrides: dict[str, str] = Field(default_factory=dict)

    @field_validator("tools")
    @classmethod
    def _known_tools(cls, v: list[str]) -> list[str]:
        unknown = [t for t in v if t not in ACTIONS]
        if unknown:
            raise ValueError(f"unknown action kind(s) in tools: {unknown}")
        return v


def proposal_tool(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    """A strict tool schema. The model proposes; the gate decides."""
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


# The model-facing tool definitions for every kind a pack may list.
TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "extract_fields": proposal_tool(
        "extract_fields",
        "Record facts the customer has given, using the intake keys you were given. "
        "Call this whenever you learn something new.",
        {"fields": {"type": "object", "additionalProperties": {"type": "string"}}},
        ["fields"],
    ),
    "propose_appointment": proposal_tool(
        "propose_appointment",
        "Propose an appointment once intake is complete. A staff member approves it before "
        "anything is booked, so never tell the customer it is booked.",
        {
            "service_code": {"type": "string"},
            "preferred_window": {
                "type": "string",
                "description": "Customer's words, e.g. 'Tuesday morning'",
            },
            "notes": {"type": "string"},
        },
        ["service_code", "preferred_window", "notes"],
    ),
    "hand_to_human": proposal_tool(
        "hand_to_human",
        "Stop and hand the conversation to a staff member. Use when the customer asks for a "
        "person, is upset, or asks something outside your remit.",
        {"reason": {"type": "string"}},
        ["reason"],
    ),
    "escalate_emergency": proposal_tool(
        "escalate_emergency",
        "Alert the on-call contact immediately. Use for danger to life or property.",
        {"summary": {"type": "string"}},
        ["summary"],
    ),
    "confirm_appointment": proposal_tool(
        "confirm_appointment",
        "The customer picked one of the offered times. Pass the appointment_id shown next to "
        "that time in the offered slots list. Staff approve before it is booked unless the "
        "service is set to auto-confirm.",
        {"appointment_id": {"type": "string"}, "service_code": {"type": "string"}},
        ["appointment_id", "service_code"],
    ),
    "reschedule_appointment": proposal_tool(
        "reschedule_appointment",
        "The customer wants a different time for a confirmed appointment.",
        {"appointment_id": {"type": "string"}, "new_window": {"type": "string"}},
        ["appointment_id", "new_window"],
    ),
    "cancel_appointment": proposal_tool(
        "cancel_appointment",
        "The customer wants to cancel a confirmed appointment.",
        {"appointment_id": {"type": "string"}, "reason": {"type": "string"}},
        ["appointment_id", "reason"],
    ),
    "send_reminder": proposal_tool(
        "send_reminder",
        "Send a reminder about an existing appointment.",
        {"appointment_id": {"type": "string"}, "text": {"type": "string"}},
        ["appointment_id", "text"],
    ),
}


@dataclass(frozen=True)
class PackSpec:
    id: str
    name: str
    system_prompt: str
    tools: list[dict[str, Any]]
    intake_opening: str
    intake: list[IntakeQuestion] = field(default_factory=list)
    workflows: list[WorkflowStep] = field(default_factory=list)
    dashboard: DashboardSpec = field(default_factory=DashboardSpec)
    vocabulary: dict[str, str] = field(default_factory=dict)
    emergency_keywords: tuple[str, ...] = ()
    emergency_reply: str = ""
    emergency_check: EmergencyCheck | None = None
    rule: PackRule | None = None
    high_risk_followup: str = "A member of the team will follow up with you on that directly."
    handoff_notice: str = "Thanks for your message. A member of the team will be in touch shortly."
    service_area_field: str | None = None
    out_of_area_reply: str = ""
    after_intake: AfterIntake = field(default_factory=AfterIntake)
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def sensitive_keys(self) -> frozenset[str]:
        return frozenset(q.key for q in self.intake if q.sensitive)
