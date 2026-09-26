"""No calendar connected: the diary is the tenant's business hours minus our own
appointments. Good enough for a pilot; the tenant sees every booking in the
dashboard and connects a calendar when they want it mirrored."""

from __future__ import annotations

from datetime import datetime

from novaxis_core.sor.base import Busy, ExternalRef, Health, Slot


class BusinessHoursCalendar:
    provider = "business_hours"

    def busy(
        self, calendar_ref: str | None, window_start: datetime, window_end: datetime
    ) -> list[Busy]:
        return []  # local appointments are subtracted by the scheduler itself

    def create_booking(
        self,
        calendar_ref: str | None,
        slot: Slot,
        summary: str,
        description: str,
        idempotency_key: str,
        details: dict[str, str] | None = None,
    ) -> ExternalRef:
        return ExternalRef(self.provider, f"local:{idempotency_key}")

    def update_booking(self, ref: ExternalRef, slot: Slot) -> None:
        return None

    def cancel_booking(self, ref: ExternalRef) -> None:
        return None

    def health(self) -> Health:
        return Health(True, "using business hours; no calendar connected")
