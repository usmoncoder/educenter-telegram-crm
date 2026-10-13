"""Restart reconciliation.

Telethon's `catch_up` replays updates missed while offline, but Telegram only guarantees a
bounded gap. As a second, independent safety net the worker re-reads private dialogs that
changed since `worker_state.processed_until` and feeds those messages (oldest first) through
the same idempotent InboxService. Duplicates are ignored by UNIQUE(conversation, message_id).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import sqlalchemy as sa
from telethon import TelegramClient
from telethon.tl import types

from app.core.logging import get_logger
from app.core.timeutil import ensure_utc
from app.db.models import Conversation, Customer
from app.db.session import SessionFactory
from app.services.inbox import InboxService
from app.telegram.gateway import normalize_message

log = get_logger(__name__)

MAX_DIALOGS = 300
MAX_MESSAGES_PER_DIALOG = 200
SAFETY_MARGIN = timedelta(minutes=2)


async def reconcile_since(
    client: TelegramClient, factory: SessionFactory, inbox: InboxService, since: datetime | None
) -> int:
    if since is None:
        log.info("reconcile_skipped_first_start")
        return 0
    since = ensure_utc(since) - SAFETY_MARGIN
    processed = 0
    async for dialog in client.iter_dialogs(limit=MAX_DIALOGS):
        if dialog.date is None or ensure_utc(dialog.date) < since:
            break  # dialogs are ordered by last activity
        entity = dialog.entity
        if not isinstance(entity, types.User) or entity.bot or entity.is_self:
            continue
        async with factory() as s:
            last_known = await s.scalar(
                sa.select(Conversation.last_telegram_message_id)
                .join(Customer, Customer.id == Conversation.customer_id)
                .where(Customer.telegram_user_id == entity.id)
            )
        kwargs = {"min_id": last_known} if last_known else {"offset_date": since}
        try:
            async for message in client.iter_messages(entity, limit=MAX_MESSAGES_PER_DIALOG, reverse=True, **kwargs):
                if not isinstance(message, types.Message | types.MessageService):
                    continue
                if ensure_utc(message.date) < since and not last_known:
                    continue
                await inbox.handle(normalize_message(message, entity))
                processed += 1
        except Exception:  # noqa: BLE001 - one dialog must not block the others
            log.exception("reconcile_dialog_failed", user_id=entity.id)
    log.info("reconcile_completed", messages=processed)
    return processed
