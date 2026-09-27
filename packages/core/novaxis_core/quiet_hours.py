"""No messages to customers overnight. Follow-ups and reminders are timed as "24 hours
later" or "2 hours before"; this moves any that would land in quiet hours (business local
time) to the nearest reasonable moment."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from novaxis_core.settings import get_settings


def _hm(text: str) -> time:
    h, m = (int(x) for x in text.split(":"))
    return time(h, m)


def is_quiet(when: datetime, tz: ZoneInfo) -> bool:
    s = get_settings()
    start, end = _hm(s.quiet_hours_start), _hm(s.quiet_hours_end)
    t = when.astimezone(tz).time()
    return t >= start or t < end if start > end else start <= t < end


def _morning_after(when: datetime, tz: ZoneInfo) -> datetime:
    local = when.astimezone(tz)
    end = _hm(get_settings().quiet_hours_end)
    day = local.date() if local.time() < end else local.date() + timedelta(days=1)
    return datetime.combine(day, end, tz).astimezone(when.tzinfo)


def _evening_before(when: datetime, tz: ZoneInfo) -> datetime:
    local = when.astimezone(tz)
    start = _hm(get_settings().quiet_hours_start)
    day = local.date() if local.time() >= start else local.date() - timedelta(days=1)
    return (datetime.combine(day, start, tz) - timedelta(minutes=1)).astimezone(when.tzinfo)


def later_if_quiet(when: datetime, tz: ZoneInfo) -> datetime:
    """For follow-ups: wait for the morning."""
    return _morning_after(when, tz) if is_quiet(when, tz) else when


def before_if_quiet(when: datetime, tz: ZoneInfo, deadline: datetime) -> datetime:
    """For reminders that must arrive before `deadline`: the morning if that is still in
    time, otherwise the evening before."""
    if not is_quiet(when, tz):
        return when
    morning = _morning_after(when, tz)
    return morning if morning < deadline else _evening_before(when, tz)
