"""Occurrence computation for announcement campaigns.

Recurring schedules are defined in local wall-clock time ("every Monday at 09:00 in
Asia/Tashkent") and converted to UTC per occurrence, so they stay correct even for time
zones with DST changes (Asia/Tashkent itself has no DST).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.timeutil import ensure_utc
from app.db.enums import ScheduleType


@dataclass(frozen=True)
class Schedule:
    schedule_type: ScheduleType
    run_at: datetime | None = None
    time_of_day: str | None = None  # "HH:MM"
    weekdays: tuple[int, ...] = ()  # 0=Monday .. 6=Sunday
    start_date: datetime | None = None
    end_date: datetime | None = None
    timezone: str = "Asia/Tashkent"


def parse_time_of_day(value: str) -> time:
    hh, mm = value.split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Vaqt noto'g'ri")
    return time(h, m)


def next_occurrence(schedule: Schedule, after: datetime) -> datetime | None:
    """First occurrence strictly after `after` (UTC), or None if the schedule is exhausted."""
    after = ensure_utc(after)
    if schedule.schedule_type == ScheduleType.ONCE:
        if schedule.run_at is None:
            return None
        run_at = ensure_utc(schedule.run_at)
        return run_at if run_at > after else None

    if not schedule.time_of_day:
        return None
    tz = ZoneInfo(schedule.timezone)
    tod = parse_time_of_day(schedule.time_of_day)
    lower = after
    if schedule.start_date is not None:
        lower = max(lower, ensure_utc(schedule.start_date) - timedelta(microseconds=1))
    end = ensure_utc(schedule.end_date) if schedule.end_date else None
    weekdays = set(schedule.weekdays) if schedule.schedule_type == ScheduleType.WEEKLY else set(range(7))
    if not weekdays:
        return None

    local_day: date = lower.astimezone(tz).date()
    for _ in range(0, 370):  # at most ~one year ahead
        if local_day.weekday() in weekdays:
            candidate = datetime.combine(local_day, tod, tzinfo=tz).astimezone(ZoneInfo("UTC"))
            if candidate > lower:
                if end is not None and candidate > end:
                    return None
                return candidate
        local_day += timedelta(days=1)
    return None
