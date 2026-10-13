"""Time helpers. All persisted timestamps are timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Asia/Tashkent")


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Return an aware UTC datetime. Naive values are assumed to already be UTC
    (Telethon returns aware UTC datetimes; this guards against accidental naive input)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_local(dt: datetime, tz: ZoneInfo = DISPLAY_TZ) -> datetime:
    return ensure_utc(dt).astimezone(tz)


def format_local(dt: datetime | None, tz: ZoneInfo = DISPLAY_TZ) -> str:
    if dt is None:
        return "—"
    return to_local(dt, tz).strftime("%d.%m.%Y %H:%M")


def humanize_seconds_uz(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} soat")
    if minutes:
        parts.append(f"{minutes} daqiqa")
    if not hours and (secs or not parts):
        parts.append(f"{secs} soniya")
    return " ".join(parts)
