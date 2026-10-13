"""Replies written in the web panel.

The API queues an `OutgoingMessage` (status QUEUED) and returns immediately; it never claims
the reply was sent. The worker claims it (SENDING, committed first), sends it through the
centralized sender while holding the chat lock, records it as a human operator reply (which
resolves the open SLA incident) and marks it SENT - or FAILED / retried with backoff.
"""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.enums import MessageDirection, MessageSource, OutboxStatus, Resolution, SenderType
from app.db.models import Conversation, Customer, Message, OutgoingMessage
from app.db.session import SessionFactory, transaction
from app.services.app_settings import SettingsCache
from app.services.inbox import _truncate, resolve_open_incident
from app.services.sender import TelegramSender, backoff_seconds
from app.telegram.types import SendError, SendErrorKind

log = get_logger(__name__)

MAX_OUTBOX_ATTEMPTS = 5


class OutboxDispatcher:
    def __init__(self, factory: SessionFactory, sender: TelegramSender, settings: SettingsCache) -> None:
        self._factory = factory
        self._sender = sender
        self._settings = settings

    async def recover_interrupted(self) -> int:
        async with transaction(self._factory) as s:
            res = await s.execute(
                sa.update(OutgoingMessage)
                .where(OutgoingMessage.status == OutboxStatus.SENDING)
                .values(status=OutboxStatus.UNKNOWN, error="Yuborish jarayonida worker to'xtadi; Telegramda tekshiring")
            )
        return res.rowcount or 0

    async def _claim(self, limit: int) -> list[int]:
        async with transaction(self._factory) as s:
            ids = (
                await s.scalars(
                    sa.select(OutgoingMessage.id)
                    .where(OutgoingMessage.status == OutboxStatus.QUEUED, OutgoingMessage.next_attempt_at <= utcnow())
                    .order_by(OutgoingMessage.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if ids:
                await s.execute(
                    sa.update(OutgoingMessage)
                    .where(OutgoingMessage.id.in_(ids))
                    .values(status=OutboxStatus.SENDING, attempts=OutgoingMessage.attempts + 1)
                )
        return list(ids)

    async def run_once(self, limit: int = 10) -> int:
        n = 0
        for oid in await self._claim(limit):
            await self._send(oid)
            n += 1
        return n

    async def _send(self, outgoing_id: int) -> None:
        async with self._factory() as s:
            row = (
                await s.execute(
                    sa.select(OutgoingMessage, Conversation, Customer)
                    .join(Conversation, Conversation.id == OutgoingMessage.conversation_id)
                    .join(Customer, Customer.id == Conversation.customer_id)
                    .where(OutgoingMessage.id == outgoing_id)
                )
            ).one()
        out, conv, customer = row
        user_id = customer.telegram_user_id
        settings = await self._settings.get()
        try:
            async with self._sender.chat_lock(user_id):
                sent = await self._sender.send(user_id, out.text, link_preview=False)
                async with transaction(self._factory) as s:
                    await s.execute(
                        pg_insert(Message)
                        .values(
                            conversation_id=conv.id,
                            telegram_message_id=sent.message_id,
                            direction=MessageDirection.OUT,
                            sender_type=SenderType.OPERATOR,
                            source=MessageSource.PANEL,
                            counts_as_reply=True,
                            text_preview=(
                                _truncate(out.text, settings.preview_length) if settings.store_operator_text else None
                            ),
                            sent_at=sent.date,
                            sent_by_admin_id=out.requested_by_admin_id,
                        )
                        .on_conflict_do_nothing(constraint="uq_messages_conv_tgid")
                    )
                    c = await s.get(Conversation, conv.id, with_for_update=True)
                    assert c is not None
                    for attr in ("last_outgoing_at", "last_human_reply_at"):
                        if getattr(c, attr) is None or sent.date >= getattr(c, attr):
                            setattr(c, attr, sent.date)
                    if c.last_message_at is None or sent.date >= c.last_message_at:
                        c.last_message_at = sent.date
                        c.last_message_direction = MessageDirection.OUT
                    c.last_telegram_message_id = max(c.last_telegram_message_id or 0, sent.message_id)
                    await resolve_open_incident(
                        s,
                        conv.id,
                        reply_message_id=sent.message_id,
                        reply_date=sent.date,
                        resolution=Resolution.PANEL_REPLY,
                    )
                    await s.execute(
                        sa.update(OutgoingMessage)
                        .where(OutgoingMessage.id == outgoing_id)
                        .values(
                            status=OutboxStatus.SENT, telegram_message_id=sent.message_id, sent_at=sent.date, error=None
                        )
                    )
            log.info("panel_reply_sent", outgoing_id=outgoing_id, conversation_id=conv.id)
        except SendError as exc:
            now = utcnow()
            values: dict[str, object] = {"error": exc.message[:500]}
            if exc.kind == SendErrorKind.FLOOD:
                values.update(
                    status=OutboxStatus.QUEUED,
                    attempts=OutgoingMessage.attempts - 1,
                    next_attempt_at=now + timedelta(seconds=exc.retry_after or 60),
                )
            elif (
                exc.kind in (SendErrorKind.TRANSIENT, SendErrorKind.UNAUTHORIZED) and out.attempts < MAX_OUTBOX_ATTEMPTS
            ):
                values.update(
                    status=OutboxStatus.QUEUED,
                    next_attempt_at=now + timedelta(seconds=exc.retry_after or backoff_seconds(out.attempts)),
                )
            else:
                values.update(status=OutboxStatus.FAILED)
            async with transaction(self._factory) as s:
                await s.execute(sa.update(OutgoingMessage).where(OutgoingMessage.id == outgoing_id).values(**values))
            log.warning("panel_reply_failed", outgoing_id=outgoing_id, kind=exc.kind, code=exc.code)
