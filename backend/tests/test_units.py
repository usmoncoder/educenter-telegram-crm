"""Pure unit tests: formatting, recurrence/timezones, security, permissions, error mapping."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from telethon import errors as te

from app.core.logging import redact_value
from app.core.permissions import Perm, has_perm
from app.core.security import hash_password, password_problems, verify_password
from app.core.timeutil import humanize_seconds_uz
from app.db.enums import Role, ScheduleType
from app.services.formatting import parse_message, utf16_len
from app.services.notifications import build_sla_alert, parse_userbot_target
from app.services.recurrence import Schedule, next_occurrence
from app.services.sender import backoff_seconds
from app.telegram.errors import classify_exception
from app.telegram.types import SendErrorKind


# ------------------------------------------------------------------------------ formatting
def test_valid_html_message_parses_to_entities():
    p = parse_message('<b>IELTS</b> kursi: <a href="https://edu.uz">batafsil</a>')
    assert p.ok, p.errors
    assert p.text == "IELTS kursi: batafsil"
    assert {e["type"] for e in p.entities} == {"bold", "link"}
    assert next(e for e in p.entities if e["type"] == "link")["url"] == "https://edu.uz"


@pytest.mark.parametrize(
    ("html", "fragment"),
    [
        ("<script>x</script>", "qo'llab-quvvatlanmaydi"),
        ("<b>yopilmagan", "yopilmagan"),
        ('<a href="javascript:alert(1)">x</a>', "Havola noto'g'ri"),
        ("   ", "bo'sh"),
    ],
)
def test_invalid_html_is_reported(html, fragment):
    p = parse_message(html)
    assert not p.ok
    assert any(fragment in e for e in p.errors)


def test_length_is_measured_in_utf16_units():
    assert utf16_len("😀") == 2
    p = parse_message("😀" * 2049)  # 4098 UTF-16 units > 4096
    assert any("juda uzun" in e for e in p.errors)
    assert parse_message("a" * 4096).ok


# ------------------------------------------------------------------------------ recurrence
def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


def test_once_schedule_future_and_past():
    s = Schedule(ScheduleType.ONCE, run_at=utc(2026, 10, 12, 10, 0))
    assert next_occurrence(s, utc(2026, 10, 12, 9, 0)) == utc(2026, 10, 12, 10, 0)
    assert next_occurrence(s, utc(2026, 10, 12, 10, 0)) is None


def test_daily_schedule_uses_tashkent_wall_clock():
    # 09:00 in Asia/Tashkent (UTC+5) == 04:00 UTC
    s = Schedule(ScheduleType.DAILY, time_of_day="09:00")
    assert next_occurrence(s, utc(2026, 10, 12, 3, 0)) == utc(2026, 10, 12, 4, 0)
    assert next_occurrence(s, utc(2026, 10, 12, 4, 0)) == utc(2026, 10, 13, 4, 0)


def test_daily_schedule_across_local_midnight():
    # 00:30 local == 19:30 UTC of the previous day
    s = Schedule(ScheduleType.DAILY, time_of_day="00:30")
    assert next_occurrence(s, utc(2026, 10, 12, 20, 0)) == utc(2026, 10, 13, 19, 30)


def test_weekly_schedule_selects_weekdays():
    # 2026-10-12 is a Monday. Wednesday(2) and Friday(4) at 18:00 local = 13:00 UTC
    s = Schedule(ScheduleType.WEEKLY, time_of_day="18:00", weekdays=(2, 4))
    first = next_occurrence(s, utc(2026, 10, 12, 0, 0))
    assert first == utc(2026, 10, 14, 13, 0)
    assert next_occurrence(s, first) == utc(2026, 10, 16, 13, 0)


def test_recurrence_window_bounds():
    s = Schedule(
        ScheduleType.DAILY, time_of_day="09:00", start_date=utc(2026, 10, 20, 0, 0), end_date=utc(2026, 10, 21, 18, 0)
    )
    assert next_occurrence(s, utc(2026, 10, 12)) == utc(2026, 10, 20, 4, 0)
    assert next_occurrence(s, utc(2026, 10, 20, 4, 0)) == utc(2026, 10, 21, 4, 0)
    assert next_occurrence(s, utc(2026, 10, 21, 4, 0)) is None


def test_weekly_without_days_never_fires():
    assert next_occurrence(Schedule(ScheduleType.WEEKLY, time_of_day="09:00"), utc(2026, 10, 12)) is None


# ------------------------------------------------------------------------------ security
def test_argon2id_hash_and_verify():
    h = hash_password("Correct-Horse-9!")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "Correct-Horse-9!")
    assert not verify_password(h, "wrong")
    assert not verify_password(None, "anything")


def test_password_policy():
    assert password_problems("Strong-Passw0rd!", "admin") == []
    assert password_problems("short", "admin")
    assert password_problems("alllowercaseletters", "admin")
    assert any("foydalanuvchi" in p for p in password_problems("Xadmin-Passw0rd!", "admin"))


def test_secrets_are_redacted_from_logs(caplog):
    data = {
        "api_hash": "0123456789abcdef0123456789abcdef",
        "password": "hunter2",
        "note": "token 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ in text",
        "url": "postgresql+asyncpg://user:SuperSecret@db:5432/x",
    }
    red = redact_value(data)
    assert red["api_hash"] == "***" and red["password"] == "***"
    assert "AAHdq" not in red["note"]
    assert "SuperSecret" not in red["url"]


def test_stdlib_log_filter_redacts_third_party_messages():
    from app.core.logging import _StdlibRedactFilter

    rec = logging.LogRecord(
        "telethon", logging.INFO, __file__, 1, "hash %s", ("0123456789abcdef0123456789abcdef",), None
    )
    _StdlibRedactFilter().filter(rec)
    assert "0123456789abcdef" not in rec.getMessage()


# ------------------------------------------------------------------------------ permissions
def test_role_permission_matrix():
    assert has_perm(Role.OPERATOR, Perm.CONVERSATIONS_REPLY)
    assert not has_perm(Role.OPERATOR, Perm.CONVERSATIONS_VIEW_ALL)
    assert not has_perm(Role.OPERATOR, Perm.CAMPAIGNS_MANAGE)
    assert not has_perm(Role.OPERATOR, Perm.SETTINGS_MANAGE)
    assert has_perm(Role.ADMIN, Perm.CAMPAIGNS_MANAGE)
    assert not has_perm(Role.ADMIN, Perm.ADMINS_MANAGE)
    assert not has_perm(Role.ADMIN, Perm.SETTINGS_MANAGE)
    assert all(has_perm(Role.SUPER_ADMIN, p) for p in Perm)


# ------------------------------------------------------------------------------ errors / misc
def test_telethon_errors_are_classified():
    flood = classify_exception(te.FloodWaitError(request=None, capture=42))
    assert flood.kind == SendErrorKind.FLOOD and flood.retry_after == 42
    forbidden = classify_exception(te.ChatWriteForbiddenError(request=None))
    assert forbidden.kind == SendErrorKind.PERMANENT and forbidden.extra.get("group_permission")
    assert classify_exception(te.AuthKeyUnregisteredError(request=None)).kind == SendErrorKind.UNAUTHORIZED
    assert classify_exception(ConnectionError()).kind == SendErrorKind.TRANSIENT
    assert classify_exception(te.MessageTooLongError(request=None)).kind == SendErrorKind.INVALID_CONTENT
    assert classify_exception(ValueError("Could not find the input entity")).code == "peer_unknown"


def test_backoff_is_exponential_and_capped():
    assert [backoff_seconds(i) for i in (1, 2, 3)] == [30, 60, 120]
    assert backoff_seconds(50) == 1800


def test_userbot_alert_target_parsing():
    assert parse_userbot_target("me") == "me"
    assert parse_userbot_target("-1001234567890") == -1001234567890
    assert parse_userbot_target("managers") == "@managers"
    assert parse_userbot_target("https://t.me/managers") == "@managers"


def test_alert_text_escapes_customer_content():
    text = build_sla_alert(
        customer_name="<b>Hacker</b>",
        username="ali_v",
        telegram_user_id=111,
        started_at=datetime.now(UTC) - timedelta(minutes=7),
        message_count=2,
        preview="<a href='x'>click</a>",
        include_preview=True,
    )
    assert "&lt;b&gt;Hacker&lt;/b&gt;" in text
    assert "<a href='x'>" not in text
    assert "tg://user?id=111" in text and "7 daqiqa" in text
    assert parse_message(text).ok


def test_humanize_seconds():
    assert humanize_seconds_uz(42) == "42 soniya"
    assert humanize_seconds_uz(360) == "6 daqiqa"
    assert humanize_seconds_uz(3725) == "1 soat 2 daqiqa"
