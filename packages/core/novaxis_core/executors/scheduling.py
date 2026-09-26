"""Appointment executors. propose offers held slots; confirm writes the booking;
reschedule moves it; cancel releases it. All go through the system of record and
are idempotent on the proposal id."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from novaxis_core import scheduling
from novaxis_core.executors import ExecResult, conversation_id_of, executor
from novaxis_core.models import ActionProposal, Appointment, Contact, Conversation, Tenant
from novaxis_core.pack_registry import resolve_pack
from novaxis_core.sor import system_of_record


def _appt(session: Session, params: Any) -> Appointment | None:
    try:
        return session.get(Appointment, uuid.UUID(str(params.appointment_id)))
    except ValueError:
        return None


@executor("propose_appointment")
def propose_appointment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    conv = session.get(Conversation, conversation_id_of(proposal))
    if conv is None:
        return ExecResult(False, {}, "conversation not found")
    contact = session.get(Contact, conv.contact_id)
    if contact is None:
        return ExecResult(False, {}, "contact not found")
    sor = system_of_record(session, tenant)
    location = scheduling.location_for(session, tenant)
    tz = scheduling.tz_for(tenant, location)
    window = scheduling.parse_window(params.preferred_window or "this week", tz)
    slots = scheduling.availability(session, tenant, sor, params.service_code, window)
    widened = False
    if not slots:
        window = scheduling.widen(window)
        slots = scheduling.availability(session, tenant, sor, params.service_code, window)
        widened = True
    held = scheduling.hold(session, tenant, contact, conv, params.service_code, slots, proposal.id)
    svc_name = scheduling._service(tenant, params.service_code).get("name", params.service_code)
    text = scheduling.offer_text(tenant, tz, held, str(svc_name), widened)
    scheduling._enqueue_send(session, tenant, conv, text)
    return ExecResult(
        True, {"offered": len(held), "window": window.label, "service_code": params.service_code}
    )


@executor("confirm_appointment")
def confirm_appointment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    appt = _appt(session, params)
    if appt is None:
        return ExecResult(False, {}, "appointment not found")
    sor = system_of_record(session, tenant)
    appt = scheduling.confirm(session, tenant, sor, resolve_pack(tenant.pack_id), appt, proposal.id)
    return ExecResult(
        True,
        {
            "appointment_id": str(appt.id),
            "external_ref": appt.external_ref or "",
            "starts_at": appt.starts_at.isoformat(),
        },
    )


@executor("reschedule_appointment")
def reschedule_appointment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    appt = _appt(session, params)
    if appt is None:
        return ExecResult(False, {}, "appointment not found")
    sor = system_of_record(session, tenant)
    appt = scheduling.reschedule(
        session, tenant, sor, resolve_pack(tenant.pack_id), appt, params.new_window
    )
    return ExecResult(
        True, {"appointment_id": str(appt.id), "starts_at": appt.starts_at.isoformat()}
    )


@executor("cancel_appointment")
def cancel_appointment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    appt = _appt(session, params)
    if appt is None:
        return ExecResult(False, {}, "appointment not found")
    sor = system_of_record(session, tenant)
    scheduling.cancel(session, tenant, sor, appt, params.reason or "cancelled")
    return ExecResult(True, {"appointment_id": str(appt.id)})
