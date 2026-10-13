"""Persisted worker / Telegram connection status, read by the dashboard."""

from __future__ import annotations

import socket
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.enums import WorkerStatus
from app.db.models import ConnectionEvent, WorkerState
from app.db.session import SessionFactory, transaction

log = get_logger(__name__)


class WorkerStateStore:
    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory
        self._hostname = socket.gethostname()[:128]

    async def _upsert(self, **values: object) -> None:
        values = {"updated_at": utcnow(), **values}
        async with transaction(self._factory) as s:
            await s.execute(
                pg_insert(WorkerState)
                .values(id=1, hostname=self._hostname, **values)
                .on_conflict_do_update(index_elements=[WorkerState.id], set_={"hostname": self._hostname, **values})
            )

    async def set_status(self, status: WorkerStatus, detail: str | None = None, **extra: object) -> None:
        values: dict[str, object] = {"status": status, "status_detail": (detail or None) and detail[:500], **extra}
        if status in (WorkerStatus.ERROR, WorkerStatus.UNAUTHORIZED, WorkerStatus.NOT_CONFIGURED):
            values.update(last_error=(detail or status.value)[:500], last_error_at=utcnow())
        await self._upsert(**values)
        await self.event(status.value, detail)

    async def heartbeat(self, processed_until: datetime | None = None) -> None:
        values: dict[str, object] = {"last_heartbeat_at": utcnow()}
        if processed_until is not None:
            values["processed_until"] = processed_until
        async with transaction(self._factory) as s:
            res = await s.execute(sa.update(WorkerState).where(WorkerState.id == 1).values(**values))
        if not res.rowcount:
            await self._upsert(status=WorkerStatus.STARTING, **values)

    async def get(self) -> WorkerState | None:
        async with self._factory() as s:
            return await s.get(WorkerState, 1)

    async def event(self, event: str, detail: str | None = None) -> None:
        async with transaction(self._factory) as s:
            s.add(ConnectionEvent(event=event[:64], detail=(detail or None) and detail[:500]))
        log.info("connection_event", connection_event=event, detail=detail)
