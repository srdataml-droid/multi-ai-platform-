"""Nothing is sent to customers overnight (20:00 to 08:00 business time)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from novaxis_core.quiet_hours import before_if_quiet, is_quiet, later_if_quiet

LON = ZoneInfo("Europe/London")


def at(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=LON).astimezone(UTC)


def test_quiet_window() -> None:
    assert is_quiet(at(2026, 11, 4, 23), LON)
    assert is_quiet(at(2026, 11, 4, 7, 59), LON)
    assert not is_quiet(at(2026, 11, 4, 8), LON)
    assert not is_quiet(at(2026, 11, 4, 19, 59), LON)


def test_a_late_night_follow_up_waits_for_the_morning() -> None:
    assert later_if_quiet(at(2026, 11, 4, 23, 30), LON) == at(2026, 11, 5, 8)
    assert later_if_quiet(at(2026, 11, 5, 3), LON) == at(2026, 11, 5, 8)
    assert later_if_quiet(at(2026, 11, 5, 14), LON) == at(2026, 11, 5, 14)


def test_an_early_reminder_moves_to_the_morning_if_still_in_time() -> None:
    appt = at(2026, 11, 5, 9)
    assert before_if_quiet(at(2026, 11, 5, 7), LON, appt) == at(2026, 11, 5, 8)


def test_a_reminder_for_a_dawn_job_goes_the_evening_before() -> None:
    appt = at(2026, 11, 5, 7, 30)
    assert before_if_quiet(at(2026, 11, 5, 5, 30), LON, appt) == at(2026, 11, 4, 19, 59)
