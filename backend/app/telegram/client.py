"""Telethon client construction and session-file protection.

The session is Telethon's standard SQLite session file. It stores the MTProto auth key and
the entity cache (needed to message users by ID after a restart) and the update state used
for `catch_up`. It is equivalent to a logged-in device: it is created with 0600 permissions
in a 0700 directory, kept on a private Docker volume, and excluded from git.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.core.config import Settings


def secure_session_dir(settings: Settings) -> Path:
    path = settings.telegram_session_dir
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(PermissionError):
        os.chmod(path, 0o700)
    return path


def secure_session_file(settings: Settings) -> None:
    for suffix in (".session", ".session-journal"):
        f = settings.session_path.with_name(settings.session_path.name + suffix)
        if f.exists():
            with contextlib.suppress(PermissionError):
                os.chmod(f, 0o600)


def session_file_exists(settings: Settings) -> bool:
    return settings.session_path.with_name(settings.session_path.name + ".session").exists()


def build_client(settings: Settings, *, catch_up: bool = True) -> TelegramClient:
    if not settings.telegram_configured:
        raise RuntimeError("TELEGRAM_API_ID va TELEGRAM_API_HASH sozlanmagan")
    assert settings.telegram_api_hash is not None
    # A StringSession (from env) wins over the on-disk file session: used on hosts without a
    # persistent disk. Otherwise fall back to the standard SQLite file session on the volume.
    session: str | StringSession
    if settings.telegram_session_string is not None:
        session = StringSession(settings.telegram_session_string.get_secret_value())
    else:
        secure_session_dir(settings)
        session = str(settings.session_path)
    client = TelegramClient(
        session,
        int(settings.telegram_api_id),  # type: ignore[arg-type]
        settings.telegram_api_hash.get_secret_value(),
        device_model=settings.telegram_device_model,
        system_version="Linux",
        app_version="1.0",
        lang_code="uz",
        system_lang_code="uz",
        auto_reconnect=True,
        connection_retries=10,
        retry_delay=5,
        request_retries=3,
        # Short waits are slept automatically for internal calls; message sending goes through
        # TelegramSender, which turns longer FloodWaits into persisted retry times.
        flood_sleep_threshold=10,
        catch_up=catch_up,
        sequential_updates=False,
    )
    secure_session_file(settings)
    return client
