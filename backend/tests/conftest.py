"""Test fixtures.

Tests run against a real PostgreSQL database (SKIP LOCKED, partial unique indexes, JSONB and
ON CONFLICT semantics matter). The schema is created with the real Alembic migrations.
Telegram is replaced by `FakeGateway`; no Telegram account or network access is needed.

    TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/educenter_test pytest
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://educenter:educenter@127.0.0.1:55432/educenter_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from app.core.config import Settings  # noqa: E402
from app.core.timeutil import utcnow  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import create_engine, create_session_factory, transaction  # noqa: E402
from app.services.app_settings import RuntimeSettings, SettingsCache, load_settings, save_settings  # noqa: E402
from app.services.sender import TelegramSender  # noqa: E402
from app.telegram.types import (  # noqa: E402
    AccountInfo,
    GroupInfo,
    SendError,
    SentMessage,
    TgMessage,
    TgUser,
)

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(database_url=TEST_DB, environment="test", log_json=False, cors_origins=[])


@pytest.fixture(scope="session", autouse=True)
def migrated_schema() -> None:
    """Recreate the schema from scratch using the real migrations (also tests them)."""
    import asyncio

    async def reset() -> None:
        engine = create_engine(Settings(database_url=TEST_DB))
        async with engine.begin() as conn:
            await conn.execute(sa.text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa.text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())
    env = {**os.environ, "DATABASE_URL": TEST_DB}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True, capture_output=True
    )


@pytest.fixture(scope="session")
async def engine(settings: Settings):
    eng = create_engine(settings)
    yield eng
    await eng.dispose()


@pytest.fixture
async def factory(engine) -> AsyncIterator:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield create_session_factory(engine)


@pytest.fixture
def settings_cache(factory) -> SettingsCache:
    return SettingsCache(factory, ttl_seconds=0)


async def set_runtime(factory, **values) -> RuntimeSettings:
    async with transaction(factory) as s:
        current = await load_settings(s)
        new = RuntimeSettings.model_validate({**current.model_dump(), **values})
        await save_settings(s, new, None)
    return new


# ------------------------------------------------------------------------------ fake Telegram
@dataclass
class FakeGateway:
    next_id: int = 5000
    sent: list[tuple[object, str]] = field(default_factory=list)
    errors: list[SendError] = field(default_factory=list)  # raised by the next send_html calls
    errors_by_peer: dict[object, SendError] = field(default_factory=dict)  # always raised for a peer
    users_with_history: set[int] = field(default_factory=set)
    groups: list[GroupInfo] = field(default_factory=list)
    resolvable: dict[str, GroupInfo] = field(default_factory=dict)

    async def send_html(self, peer, html_text: str, *, link_preview: bool = False) -> SentMessage:
        if peer in self.errors_by_peer:
            raise self.errors_by_peer[peer]
        if self.errors:
            raise self.errors.pop(0)
        self.next_id += 1
        self.sent.append((peer, html_text))
        return SentMessage(message_id=self.next_id, date=utcnow())

    async def has_history_before(self, user_id: int, message_id: int) -> bool:
        return user_id in self.users_with_history

    async def list_groups(self) -> list[GroupInfo]:
        return list(self.groups)

    async def resolve_group(self, identifier: str) -> GroupInfo:
        if identifier in self.resolvable:
            return self.resolvable[identifier]
        from app.telegram.types import SendErrorKind

        raise SendError(SendErrorKind.PERMANENT, "not_found", "Guruh topilmadi")

    async def get_account(self) -> AccountInfo:
        return AccountInfo(user_id=1, username="center", name="Center")


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def sender(gateway) -> TelegramSender:
    return TelegramSender(gateway, min_interval_seconds=0)


CUSTOMER = TgUser(id=111, username="ali_v", first_name="Ali", last_name="Valiyev")


def tg_msg(
    message_id: int,
    *,
    user: TgUser = CUSTOMER,
    outgoing: bool = False,
    text: str = "Salom, kurslar haqida ma'lumot bering",
    minutes_ago: float = 0,
    date: datetime | None = None,
    **kw,
) -> TgMessage:
    return TgMessage(
        message_id=message_id,
        chat_user=user,
        date=date or (utcnow() - timedelta(minutes=minutes_ago)),
        outgoing=outgoing,
        text=text,
        **kw,
    )
