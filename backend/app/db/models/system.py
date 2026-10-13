"""Application settings, worker state, worker commands and connection event log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.db.base import Base, str_enum
from app.db.enums import CommandStatus, CommandType, WorkerStatus


class AppSettingsRow(Base):
    """Singleton row (id=1) holding validated business settings as JSON."""

    __tablename__ = "app_settings"
    __table_args__ = (sa.CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1, autoincrement=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=sa.text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, server_default=sa.func.now())
    updated_by_admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admins.id", ondelete="SET NULL"))


class WorkerState(Base):
    """Singleton row (id=1) the Telegram worker updates; the dashboard reads it."""

    __tablename__ = "worker_state"
    __table_args__ = (sa.CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1, autoincrement=False)
    status: Mapped[WorkerStatus] = mapped_column(str_enum(WorkerStatus, "worker_status"))
    status_detail: Mapped[str | None] = mapped_column(sa.String(500))
    account_user_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    account_username: Mapped[str | None] = mapped_column(sa.String(64))
    account_name: Mapped[str | None] = mapped_column(sa.String(255))
    hostname: Mapped[str | None] = mapped_column(sa.String(128))
    started_at: Mapped[datetime | None]
    connected_at: Mapped[datetime | None]
    last_heartbeat_at: Mapped[datetime | None]
    # Last moment all updates were known to be processed; used for restart reconciliation.
    processed_until: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(sa.String(500))
    last_error_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, server_default=sa.func.now())


class ConnectionEvent(Base):
    __tablename__ = "connection_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    event: Mapped[str] = mapped_column(sa.String(64))
    detail: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now(), index=True)


class WorkerCommand(Base):
    """Requests from the API to the worker (which owns the Telegram connection)."""

    __tablename__ = "worker_commands"
    __table_args__ = (sa.Index("ix_worker_commands_status", "status", "created_at"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    command: Mapped[CommandType] = mapped_column(str_enum(CommandType, "command_type"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=sa.text("'{}'::jsonb"))
    status: Mapped[CommandStatus] = mapped_column(
        str_enum(CommandStatus, "command_status"), default=CommandStatus.PENDING
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(sa.String(500))
    requested_by_admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admins.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
