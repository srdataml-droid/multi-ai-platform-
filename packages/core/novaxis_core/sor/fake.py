"""In-memory calendar for tests and offline demos. Behaves like a real one:
bookings occupy time, double booking the same slot fails, refs are stable per
idempotency key."""

from __future__ import annotations

from datetime import datetime

from novaxis_core.sor.base import Busy, ExternalRef, Health, Slot, overlaps


class FakeCalendar:
    provider = "fake"

    def __init__(self) -> None:
        self.events: dict[str, tuple[Slot, str]] = {}
        self._by_key: dict[str, str] = {}
        self.calls: list[str] = []
        self.healthy = True

    def busy(
        self, calendar_ref: str | None, window_start: datetime, window_end: datetime
    ) -> list[Busy]:
        self.calls.append("busy")
        return [
            Busy(s.starts_at, s.ends_at)
            for s, _ in self.events.values()
            if overlaps(s.starts_at, s.ends_at, window_start, window_end)
        ]

    def create_booking(
        self,
        calendar_ref: str | None,
        slot: Slot,
        summary: str,
        description: str,
        idempotency_key: str,
        details: dict[str, str] | None = None,
    ) -> ExternalRef:
        self.calls.append("create")
        if idempotency_key in self._by_key:
            return ExternalRef(self.provider, self._by_key[idempotency_key])
        for s, _ in self.events.values():
            if overlaps(s.starts_at, s.ends_at, slot.starts_at, slot.ends_at):
                raise RuntimeError("slot already booked in calendar")
        ref = f"evt-{len(self.events) + 1}"
        self.events[ref] = (slot, summary)
        self._by_key[idempotency_key] = ref
        return ExternalRef(self.provider, ref)

    def update_booking(self, ref: ExternalRef, slot: Slot) -> None:
        self.calls.append("update")
        summary = self.events[ref.ref][1]
        self.events[ref.ref] = (slot, summary)

    def cancel_booking(self, ref: ExternalRef) -> None:
        self.calls.append("cancel")
        self.events.pop(ref.ref, None)

    def health(self) -> Health:
        return Health(self.healthy, "fake")
