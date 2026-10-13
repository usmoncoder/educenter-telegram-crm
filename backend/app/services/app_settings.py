"""Business settings editable from the admin panel, persisted as one validated JSON row."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.db.enums import IncidentStatus
from app.db.models import AppSettingsRow, SlaIncident
from app.db.session import SessionFactory
from app.services.formatting import parse_message


class RuntimeSettings(BaseModel):
    # --- First-contact automatic information -------------------------------------------
    # Disabled by default: the system must never invent course info; an admin writes it first.
    welcome_enabled: bool = False
    welcome_text: str = Field(default="", max_length=20000)
    welcome_delay_seconds: int = Field(default=0, ge=0, le=3600)
    # Only greet chats with no earlier history (prevents greeting existing contacts on first install).
    welcome_only_new_chats: bool = True
    welcome_link_preview: bool = False
    welcome_excluded_user_ids: list[int] = Field(default_factory=list, max_length=5000)

    # --- Monitoring scope ----------------------------------------------------------------
    monitor_excluded_user_ids: list[int] = Field(default_factory=list, max_length=5000)
    # Private chats with people saved in the account's contacts are treated as non-business.
    ignore_contacts: bool = True

    # --- SLA ---------------------------------------------------------------------------
    sla_enabled: bool = True
    sla_timeout_minutes: int = Field(default=5, ge=1, le=1440)
    count_forwarded_as_reply: bool = False

    # --- Administrator alerts ------------------------------------------------------------
    alerts_enabled: bool = True
    alert_channel: Literal["userbot", "bot"] = "userbot"
    # userbot: "me" (Saved Messages), "@username" or a numeric chat id such as -1001234567890.
    # bot: numeric chat id(s) separated by commas (the bot must be able to message them).
    alert_chat: str = Field(default="", max_length=500)
    alert_include_preview: bool = True

    # --- Privacy / retention ---------------------------------------------------------------
    store_message_text: bool = True
    # When enabled, operator reply text is also kept (truncated preview). Off by default so the
    # system stays data-minimal; only a Super Admin can turn it on from Settings.
    store_operator_text: bool = False
    preview_length: int = Field(default=200, ge=0, le=1000)
    retention_days: int = Field(default=90, ge=7, le=3650)

    # --- Announcements -------------------------------------------------------------------
    announcement_min_interval_seconds: int = Field(default=5, ge=1, le=600)
    announcement_max_attempts: int = Field(default=5, ge=1, le=20)
    misfire_grace_minutes: int = Field(default=60, ge=1, le=10080)

    # --- Access ------------------------------------------------------------------------------
    operators_see_unassigned: bool = True

    @field_validator("welcome_excluded_user_ids", "monitor_excluded_user_ids")
    @classmethod
    def _dedupe(cls, v: list[int]) -> list[int]:
        return sorted({int(x) for x in v if int(x) > 0})

    @field_validator("alert_chat")
    @classmethod
    def _alert_chat(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _check(self) -> RuntimeSettings:
        if self.welcome_enabled:
            parsed = parse_message(self.welcome_text)
            if not parsed.ok:
                raise ValueError("Avtomatik javob matni: " + "; ".join(parsed.errors))
        if self.alerts_enabled and self.alert_channel == "bot" and self.alert_chat:
            for part in self.alert_chat.split(","):
                part = part.strip()
                if not part.lstrip("-").isdigit():
                    raise ValueError("Bot orqali ogohlantirish uchun chat ID raqam bo'lishi kerak")
        return self

    @property
    def sla_timeout_seconds(self) -> int:
        return self.sla_timeout_minutes * 60


async def load_settings(session: AsyncSession) -> RuntimeSettings:
    row = await session.get(AppSettingsRow, 1)
    if row is None:
        return RuntimeSettings()
    # model_construct-free validation: stored data was validated on save, but defaults for
    # newly added fields must apply, and an old invalid welcome text must not crash the worker.
    try:
        return RuntimeSettings.model_validate(row.data)
    except ValueError:
        data = dict(row.data)
        data["welcome_enabled"] = False
        return RuntimeSettings.model_validate(data)


async def save_settings(session: AsyncSession, new: RuntimeSettings, admin_id: int | None) -> RuntimeSettings:
    """Persist settings. If the SLA timeout changed, open incidents that have not alerted yet
    get their deadline recalculated so the new policy applies immediately."""
    old = await load_settings(session)
    stmt = (
        pg_insert(AppSettingsRow)
        .values(id=1, data=new.model_dump(mode="json"), version=1, updated_by_admin_id=admin_id)
        .on_conflict_do_update(
            index_elements=[AppSettingsRow.id],
            set_={
                "data": new.model_dump(mode="json"),
                "version": AppSettingsRow.version + 1,
                "updated_at": utcnow(),
                "updated_by_admin_id": admin_id,
            },
        )
    )
    await session.execute(stmt)
    if old.sla_timeout_minutes != new.sla_timeout_minutes:
        await session.execute(
            sa.update(SlaIncident)
            .where(SlaIncident.status == IncidentStatus.OPEN, SlaIncident.alerted_at.is_(None))
            .values(
                timeout_seconds=new.sla_timeout_seconds,
                deadline_at=SlaIncident.started_at + timedelta(seconds=new.sla_timeout_seconds),
                updated_at=utcnow(),
            )
        )
    return new


class SettingsCache:
    """Short-lived cache used by the worker so hot paths don't hit the DB for every message."""

    def __init__(self, factory: SessionFactory, ttl_seconds: float = 5.0) -> None:
        self._factory = factory
        self._ttl = ttl_seconds
        self._value: RuntimeSettings | None = None
        self._loaded_at = 0.0

    async def get(self) -> RuntimeSettings:
        if self._value is None or time.monotonic() - self._loaded_at > self._ttl:
            async with self._factory() as session:
                self._value = await load_settings(session)
            self._loaded_at = time.monotonic()
        return self._value

    def invalidate(self) -> None:
        self._value = None
