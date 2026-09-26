"""Resolve the tenant's system of record: the vendor bridge if connected (the vendor's diary
is the real one), else a connected calendar, else business hours."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.credentials import seal, unseal
from novaxis_core.models import Integration, Tenant
from novaxis_core.sor.base import Busy, ExternalRef, Health, Slot, SystemOfRecord, overlaps
from novaxis_core.sor.business_hours import BusinessHoursCalendar
from novaxis_core.sor.google_calendar import GoogleCalendar

_override: Callable[[Tenant], SystemOfRecord] | None = None


def set_sor_override(fn: Callable[[Tenant], SystemOfRecord] | None) -> None:
    """Tests and offline demos plug in a FakeCalendar for every tenant."""
    global _override
    _override = fn


def system_of_record(session: Session, tenant: Tenant) -> SystemOfRecord:
    if _override is not None:
        return _override(tenant)
    from novaxis_core.bridge import BookingBridge, bridge_integration

    bridge = bridge_integration(session)
    if bridge is not None:
        return BookingBridge(session, tenant, bridge)
    integ = session.scalar(
        select(Integration).where(
            Integration.provider == "google_calendar", Integration.health != "disconnected"
        )
    )
    if integ is None:
        return BusinessHoursCalendar()
    tokens = unseal(integ.encrypted_credentials)

    def save(updated: dict[str, Any]) -> None:
        integ.encrypted_credentials = seal(updated)
        session.flush()

    return GoogleCalendar(tokens, save)


__all__ = [
    "Busy",
    "ExternalRef",
    "Health",
    "Slot",
    "SystemOfRecord",
    "overlaps",
    "set_sor_override",
    "system_of_record",
]
