"""Kinds the gate knows but nothing can run yet. Registered so a proposal of these
kinds can never fall into a void: if one is ever approved, it fails loudly with a
row that says why, and a person sees it."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from novaxis_core.executors import ExecResult, executor
from novaxis_core.models import ActionProposal, Tenant


@executor("outbound_first_contact")
def outbound_first_contact(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    raise NotImplementedError("first contact is composed and sent by a person (Phase 2)")


@executor("write_to_vendor_system")
def write_to_vendor_system(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    raise NotImplementedError(
        "bookings reach a vendor diary through the calendar or the booking bridge, "
        "not through this action"
    )


@executor("collect_payment")
def collect_payment(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    raise NotImplementedError(
        "payments are taken by staff in the payment provider, never by the worker"
    )


@executor("quote_price")
def quote_price(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    raise NotImplementedError("prices are quoted by staff; the worker has no price list yet")
