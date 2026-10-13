"""Executes commands queued by the API for the worker (which owns the Telegram connection)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.enums import CommandStatus, CommandType, GroupSource
from app.db.models import WorkerCommand
from app.db.session import SessionFactory, transaction
from app.services.app_settings import SettingsCache
from app.services.groups import sync_discovered, upsert_group
from app.services.notifications import AlertNotifier, build_test_alert
from app.telegram.types import SendError, TelegramGateway

log = get_logger(__name__)

COMMAND_EXPIRY = timedelta(minutes=15)


class CommandExecutor:
    def __init__(
        self,
        factory: SessionFactory,
        gateway: TelegramGateway,
        settings: SettingsCache,
        notifier: AlertNotifier,
        request_reconnect: Callable[[], Awaitable[None]],
    ) -> None:
        self._factory = factory
        self._gateway = gateway
        self._settings = settings
        self._notifier = notifier
        self._request_reconnect = request_reconnect

    async def _claim(self) -> WorkerCommand | None:
        async with transaction(self._factory) as s:
            cmd = await s.scalar(
                sa.select(WorkerCommand)
                .where(WorkerCommand.status == CommandStatus.PENDING)
                .order_by(WorkerCommand.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if cmd is None:
                return None
            if utcnow() - cmd.created_at > COMMAND_EXPIRY:
                cmd.status = CommandStatus.FAILED
                cmd.error = "Muddati o'tdi: worker o'z vaqtida bajara olmadi"
                cmd.finished_at = utcnow()
                return cmd
            cmd.status = CommandStatus.RUNNING
            cmd.started_at = utcnow()
            return cmd

    async def run_once(self, limit: int = 5) -> int:
        n = 0
        for _ in range(limit):
            cmd = await self._claim()
            if cmd is None:
                break
            if cmd.status == CommandStatus.RUNNING:
                await self._execute(cmd)
            n += 1
        return n

    async def _finish(self, cmd_id: int, *, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        async with transaction(self._factory) as s:
            await s.execute(
                sa.update(WorkerCommand)
                .where(WorkerCommand.id == cmd_id)
                .values(
                    status=CommandStatus.FAILED if error else CommandStatus.DONE,
                    result=result,
                    error=error[:500] if error else None,
                    finished_at=utcnow(),
                )
            )

    async def _execute(self, cmd: WorkerCommand) -> None:
        try:
            if cmd.command == CommandType.SYNC_GROUPS:
                groups = await self._gateway.list_groups()
                async with transaction(self._factory) as s:
                    result = await sync_discovered(s, groups)
                await self._finish(cmd.id, result=result)
            elif cmd.command == CommandType.RESOLVE_GROUP:
                info = await self._gateway.resolve_group(str(cmd.payload.get("identifier", "")))
                async with transaction(self._factory) as s:
                    group_id = await upsert_group(s, info, GroupSource.MANUAL)
                await self._finish(
                    cmd.id, result={"group_id": group_id, "title": info.title, "can_send": info.can_send}
                )
            elif cmd.command == CommandType.TEST_ALERT:
                await self._notifier.send(await self._settings.get(), build_test_alert())
                await self._finish(cmd.id, result={"sent": True})
            elif cmd.command == CommandType.RECONNECT:
                await self._finish(cmd.id, result={"reconnecting": True})
                await self._request_reconnect()
            else:
                await self._finish(cmd.id, error=f"Noma'lum buyruq: {cmd.command}")
        except SendError as exc:
            await self._finish(cmd.id, error=exc.message)
        except Exception as exc:  # noqa: BLE001
            log.exception("worker_command_failed", command=cmd.command)
            await self._finish(cmd.id, error=f"Kutilmagan xato: {type(exc).__name__}")
