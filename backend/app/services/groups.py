"""Persistence of Telegram groups discovered from the account's dialogs or added manually."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.db.enums import GroupSource
from app.db.models import TelegramGroup
from app.telegram.types import GroupInfo


async def upsert_group(session: AsyncSession, info: GroupInfo, source: GroupSource) -> int:
    now = utcnow()
    values = {
        "telegram_id": info.telegram_id,
        "title": info.title[:255],
        "username": info.username,
        "kind": info.kind,
        "participants_count": info.participants_count,
        "is_member": info.is_member,
        "can_send": info.can_send,
        "permission_note": info.permission_note,
        "last_synced_at": now,
    }
    stmt = (
        pg_insert(TelegramGroup)
        .values(source=source, is_enabled=False, **values)
        .on_conflict_do_update(index_elements=[TelegramGroup.telegram_id], set_={**values, "updated_at": now})
        .returning(TelegramGroup.id)
    )
    return int(await session.scalar(stmt))  # type: ignore[arg-type]


async def sync_discovered(session: AsyncSession, groups: list[GroupInfo]) -> dict[str, int]:
    """Upsert discovered groups. Previously discovered groups that no longer appear in the
    dialogs are marked as not-a-member (kept for history, cannot be sent to)."""
    seen = []
    for info in groups:
        await upsert_group(session, info, GroupSource.DISCOVERED)
        seen.append(info.telegram_id)
    stale = await session.execute(
        sa.update(TelegramGroup)
        .where(TelegramGroup.source == GroupSource.DISCOVERED, TelegramGroup.telegram_id.not_in(seen or [0]))
        .values(is_member=False, can_send=False, permission_note="Akkaunt guruhda topilmadi", updated_at=utcnow())
    )
    return {"found": len(groups), "stale": stale.rowcount or 0}
