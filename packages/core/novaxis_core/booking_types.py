"""Booking types: what a business books, for whom, and what it asks first.

A business with no booking types asks every customer its trade's standard questions
(packs/<trade>/intake.yaml) and books the service the pack maps them to. A business with
booking types (Settings > Booking types) gets, per conversation:

- only the types for this customer: `new` (never had a confirmed booking), `existing`
  (has had one) or `anyone`;
- when more than one fits, a first question (`booking_type_question`, "What can we help
  you with?") whose options are those types' names; the answer picks the type;
- that type's own questions, then the booking request for its service.

Everything the assistant, the agent API and the answer-recording step know about intake
comes from `intake_for`, so they can never disagree about what to ask.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.models import Appointment, Conversation, Tenant
from novaxis_core.packspec import IntakeQuestion, PackSpec

TYPE_KEY = "booking_type"


@dataclass(frozen=True)
class Intake:
    questions: list[IntakeQuestion]
    action: str  # what happens when every answer is in (propose_appointment, ...)
    service_code: str  # the service to book; "" = not known yet
    window_from: str  # the answer that says when the customer wants the visit
    area_from: str | None  # the answer checked against the service area
    type_name: str | None  # the booking type chosen, when the business has types


def is_existing_customer(session: Session, contact_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(Appointment.id)
            .where(Appointment.contact_id == contact_id, Appointment.status == "confirmed")
            .limit(1)
        )
        is not None
    )


def _pack_service(pack: PackSpec, plain: dict[str, Any]) -> str:
    ai = pack.after_intake
    if ai.service_code_from:
        value = str(plain.get(ai.service_code_from, "")).strip().lower()
        for k, v in ai.service_code_map.items():
            if k.lower() == value:
                return v
    return ai.default_service_code


def _first_of(questions: list[IntakeQuestion], kind: str) -> str | None:
    return next((q.key for q in questions if q.type == kind), None)


def intake_for(
    session: Session, tenant: Tenant, pack: PackSpec, conv: Conversation, plain: dict[str, Any]
) -> Intake:
    types: list[dict[str, Any]] = tenant.settings.get("booking_types") or []
    if not types:
        return Intake(
            questions=list(pack.intake),
            action=pack.after_intake.action,
            service_code=_pack_service(pack, plain),
            window_from=pack.after_intake.window_from,
            area_from=pack.service_area_field,
            type_name=None,
        )
    existing = is_existing_customer(session, conv.contact_id)
    fits = [
        t for t in types if t.get("who", "anyone") in ("anyone", "existing" if existing else "new")
    ]
    allowed = fits or types  # a customer no type is meant for can still pick one
    picked = str(plain.get(TYPE_KEY, "")).strip().lower()
    chosen = next((t for t in allowed if t["name"].strip().lower() == picked), None)
    if chosen is None and len(allowed) == 1:
        chosen = allowed[0]
    pick = (
        []
        if len(allowed) == 1
        else [
            IntakeQuestion(
                key=TYPE_KEY,
                ask=str(
                    tenant.settings.get("booking_type_question") or "What can we help you with?"
                ),
                type="choice",
                choices=[t["name"] for t in allowed],
            )
        ]
    )
    if chosen is None:
        return Intake(pick, "propose_appointment", "", "preferred_window", None, None)
    questions = pick + [IntakeQuestion(**q) for q in chosen["questions"]]
    return Intake(
        questions=questions,
        action="propose_appointment",
        service_code=str(chosen["service_code"]),
        window_from=_first_of(questions, "window") or "preferred_window",
        area_from=pack.service_area_field
        if any(q.key == pack.service_area_field for q in questions)
        else _first_of(questions, "postcode"),
        type_name=str(chosen["name"]),
    )


def starter_type(pack: PackSpec, services: list[dict[str, Any]]) -> dict[str, Any]:
    """A booking type made from the trade's standard questions, for a business to start
    from and edit (Settings > Booking types > Start from our standard questions)."""
    default = pack.after_intake.default_service_code
    codes = [s["code"] for s in services]
    return {
        "name": "New enquiry",
        "who": "anyone",
        "service_code": default if default in codes else (codes[0] if codes else default),
        "questions": [
            {
                "key": q.key,
                "ask": q.ask,
                "type": q.type,
                "choices": list(q.choices),
                "required": q.required,
            }
            for q in pack.intake
        ],
    }
