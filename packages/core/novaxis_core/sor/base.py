"""The system-of-record contract: where the business's real diary lives.

Phase 1 ships Google Calendar and a business-hours fallback. Chunk 11 adds the
pilot's vendor. The worker only ever talks to this interface, so a vendor swap is
one adapter file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class Slot:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class Busy:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class ExternalRef:
    provider: str
    ref: str


@dataclass(frozen=True)
class Health:
    ok: bool
    detail: str = ""


class SystemOfRecord(Protocol):
    """`details` on create_booking carries what a person needs to re-key the booking by hand
    (service code and name, customer name and phone). Calendars with an API may ignore it."""

    provider: str

    def busy(
        self, calendar_ref: str | None, window_start: datetime, window_end: datetime
    ) -> list[Busy]: ...

    def create_booking(
        self,
        calendar_ref: str | None,
        slot: Slot,
        summary: str,
        description: str,
        idempotency_key: str,
        details: dict[str, str] | None = None,
    ) -> ExternalRef: ...

    def update_booking(self, ref: ExternalRef, slot: Slot) -> None: ...

    def cancel_booking(self, ref: ExternalRef) -> None: ...

    def health(self) -> Health: ...


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def as_dict(slot: Slot) -> dict[str, Any]:
    return {"starts_at": slot.starts_at.isoformat(), "ends_at": slot.ends_at.isoformat()}
