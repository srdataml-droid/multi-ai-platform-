"""Every action the worker can take, with its parameters and default risk.

Why a registry: the gate, the executors, the pack tool lists and the dashboard
all need to agree on what an action is. This is the one list. Adding an action
means adding it here, giving it an executor, and (optionally) exposing it as a
tool in a pack.

Risk vocabulary:
- low: runs immediately, logged.
- medium: waits for a staff decision.
- high: refused with a reason; the reply tells the customer a person will follow up.

`floor` is the lowest risk a tenant may configure for the kind. Core rules in
`gate.py` can still raise any decision; nothing can lower below the floor.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Risk = Literal["low", "medium", "high"]
RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReplyParams(_Params):
    text: str = Field(min_length=1, max_length=4000)


class HandoffNoticeParams(_Params):
    """Fixed, pack-authored text sent when the model's reply was refused. Never model text."""

    text: str = Field(min_length=1, max_length=1000)


class AskIntakeQuestionParams(_Params):
    question_key: str
    text: str = Field(min_length=1, max_length=2000)


class ExtractFieldsParams(_Params):
    fields: dict[str, str]


class ProposeAppointmentParams(_Params):
    service_code: str
    preferred_window: str = ""
    notes: str = ""


class ScheduleCallbackParams(_Params):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    window: str = Field(min_length=1, max_length=160)


class ConfirmAppointmentParams(_Params):
    appointment_id: str
    service_code: str = ""


class RescheduleAppointmentParams(_Params):
    appointment_id: str
    new_window: str


class CancelAppointmentParams(_Params):
    appointment_id: str
    reason: str = ""


class SendReminderParams(_Params):
    appointment_id: str
    text: str = Field(min_length=1, max_length=2000)


class EscalateEmergencyParams(_Params):
    summary: str


class HandToHumanParams(_Params):
    reason: str


class OutboundFirstContactParams(_Params):
    to: str
    channel: str
    text: str


class WriteToVendorSystemParams(_Params):
    provider: str
    operation: str
    payload: dict[str, Any] = Field(default_factory=dict)


class CollectPaymentParams(_Params):
    amount_minor: int
    currency: str


class QuotePriceParams(_Params):
    service_code: str
    amount_minor: int
    currency: str


class VerifyClaimParams(_Params):
    text: str


class ActionKind(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    params: type[BaseModel]
    default_risk: Risk
    floor: Risk
    description: str


ACTIONS: dict[str, ActionKind] = {
    a.name: a
    for a in (
        ActionKind(
            name="schedule_callback",
            params=ScheduleCallbackParams,
            default_risk="medium",
            floor="medium",
            description="Record a manual callback task after human approval",
        ),
        ActionKind(
            name="reply",
            params=ReplyParams,
            default_risk="low",
            floor="low",
            description="Send the reply text to the customer",
        ),
        ActionKind(
            name="handoff_notice",
            params=HandoffNoticeParams,
            default_risk="low",
            floor="low",
            description="Tell the customer a person will follow up, with fixed pack text",
        ),
        ActionKind(
            name="ask_intake_question",
            params=AskIntakeQuestionParams,
            default_risk="low",
            floor="low",
            description="Ask the next structured intake question",
        ),
        ActionKind(
            name="extract_fields",
            params=ExtractFieldsParams,
            default_risk="low",
            floor="low",
            description="Record facts the customer gave",
        ),
        ActionKind(
            name="propose_appointment",
            params=ProposeAppointmentParams,
            default_risk="medium",
            floor="low",
            description="Create an appointment in proposed state",
        ),
        ActionKind(
            name="confirm_appointment",
            params=ConfirmAppointmentParams,
            default_risk="medium",
            floor="low",
            description="Write to the calendar and confirm to the customer",
        ),
        ActionKind(
            name="reschedule_appointment",
            params=RescheduleAppointmentParams,
            default_risk="medium",
            floor="medium",
            description="Move an appointment",
        ),
        ActionKind(
            name="cancel_appointment",
            params=CancelAppointmentParams,
            default_risk="medium",
            floor="medium",
            description="Cancel an appointment",
        ),
        ActionKind(
            name="send_reminder",
            params=SendReminderParams,
            default_risk="low",
            floor="low",
            description="Reminder for an existing appointment, template text",
        ),
        ActionKind(
            name="escalate_emergency",
            params=EscalateEmergencyParams,
            default_risk="low",
            floor="low",
            description="Alert the on-call contact now",
        ),
        ActionKind(
            name="hand_to_human",
            params=HandToHumanParams,
            default_risk="low",
            floor="low",
            description="Stop the worker on this conversation",
        ),
        ActionKind(
            name="outbound_first_contact",
            params=OutboundFirstContactParams,
            default_risk="high",
            floor="high",
            description="Contact someone who has not contacted us",
        ),
        ActionKind(
            name="write_to_vendor_system",
            params=WriteToVendorSystemParams,
            default_risk="medium",
            floor="medium",
            description="Write into the tenant's system of record",
        ),
        ActionKind(
            name="collect_payment",
            params=CollectPaymentParams,
            default_risk="high",
            floor="high",
            description="Take money",
        ),
        ActionKind(
            name="quote_price",
            params=QuotePriceParams,
            default_risk="high",
            floor="medium",
            description="State a price; medium only with a tenant price list",
        ),
        ActionKind(
            name="verify_claim",
            params=VerifyClaimParams,
            default_risk="medium",
            floor="medium",
            description="A reply claimed a side effect that has no proposal",
        ),
    )
}


def parse_params(kind: str, params: dict[str, Any]) -> BaseModel:
    """Validate params for a kind. KeyError for unknown kinds, ValidationError for bad params."""
    return ACTIONS[kind].params.model_validate(params)


def params_valid(kind: str, params: dict[str, Any]) -> str | None:
    """None if valid, else a short reason."""
    if kind not in ACTIONS:
        return f"unknown action kind {kind!r}"
    try:
        parse_params(kind, params)
    except ValidationError as exc:
        return f"invalid params: {exc.errors()[0].get('msg', 'validation error')}"
    return None
