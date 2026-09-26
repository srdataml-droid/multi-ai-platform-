"""Appointment executors. Real implementations arrive with the calendar in Chunk 8;
until then they are registered so the gate can route to them and they fail loudly."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from novaxis_core.executors import ExecResult, executor
from novaxis_core.models import ActionProposal, Tenant


def _pending(kind: str) -> ExecResult:
    raise NotImplementedError(f"{kind} arrives in Chunk 8 (scheduling)")


@executor("propose_appointment")
def propose_appointment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    return _pending("propose_appointment")


@executor("confirm_appointment")
def confirm_appointment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    return _pending("confirm_appointment")


@executor("reschedule_appointment")
def reschedule_appointment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    return _pending("reschedule_appointment")


@executor("cancel_appointment")
def cancel_appointment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    return _pending("cancel_appointment")
