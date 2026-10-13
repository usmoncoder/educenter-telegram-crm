"""Data minimization: purge old message content and housekeeping rows."""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa

from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.enums import CommandStatus, MessageDirection
from app.db.models import AdminSession, ConnectionEvent, Message, RateLimitHit, WorkerCommand
from app.db.session import SessionFactory, transaction
from app.services.app_settings import SettingsCache

log = get_logger(__name__)


async def run_retention(factory: SessionFactory, settings: SettingsCache) -> dict[str, int]:
    cfg = await settings.get()
    now = utcnow()
    cutoff = now - timedelta(days=cfg.retention_days)
    result: dict[str, int] = {}
    async with transaction(factory) as s:
        r = await s.execute(sa.delete(Message).where(Message.sent_at < cutoff))
        result["messages_deleted"] = r.rowcount or 0
        cleared = 0
        if not cfg.store_message_text:
            r = await s.execute(
                sa.update(Message)
                .where(Message.direction == MessageDirection.IN, Message.text_preview.is_not(None))
                .values(text_preview=None)
            )
            cleared += r.rowcount or 0
        if not cfg.store_operator_text:
            r = await s.execute(
                sa.update(Message)
                .where(Message.direction == MessageDirection.OUT, Message.text_preview.is_not(None))
                .values(text_preview=None)
            )
            cleared += r.rowcount or 0
        result["previews_cleared"] = cleared
        r = await s.execute(sa.delete(RateLimitHit).where(RateLimitHit.created_at < now - timedelta(days=2)))
        result["rate_limit_rows"] = r.rowcount or 0
        r = await s.execute(
            sa.delete(AdminSession).where(
                sa.or_(
                    AdminSession.expires_at < now - timedelta(days=7), AdminSession.revoked_at < now - timedelta(days=7)
                )
            )
        )
        result["sessions"] = r.rowcount or 0
        r = await s.execute(sa.delete(ConnectionEvent).where(ConnectionEvent.created_at < now - timedelta(days=90)))
        result["connection_events"] = r.rowcount or 0
        r = await s.execute(
            sa.delete(WorkerCommand).where(
                WorkerCommand.created_at < now - timedelta(days=30),
                WorkerCommand.status.in_([CommandStatus.DONE, CommandStatus.FAILED]),
            )
        )
        result["worker_commands"] = r.rowcount or 0
    log.info("retention_completed", **result)
    return result
