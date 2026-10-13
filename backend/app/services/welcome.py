"""First-contact automatic information dispatcher.

State machine on `customers.welcome_status` (database is the source of truth):
  PENDING --claim--> SENDING --ok--> SENT
                       |----history found--> EXISTING
                       |----flood/transient--> PENDING (later)
                       |----permanent / too many attempts--> FAILED
  SENDING left behind by a crash --startup recovery--> UNKNOWN   (never re-sent: no duplicates)

Claiming uses `FOR UPDATE SKIP LOCKED` and is committed *before* the Telegram call, so even
two worker processes can never send the same welcome twice.
"""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.enums import MessageDirection, MessageSource, SenderType, WelcomeStatus
from app.db.models import Conversation, Customer, Message
from app.db.session import SessionFactory, transaction
from app.services.app_settings import SettingsCache
from app.services.sender import TelegramSender, backoff_seconds
from app.telegram.types import SendError, SendErrorKind, TelegramGateway

log = get_logger(__name__)

MAX_WELCOME_ATTEMPTS = 5


class WelcomeDispatcher:
    def __init__(
        self,
        factory: SessionFactory,
        settings: SettingsCache,
        sender: TelegramSender,
        gateway: TelegramGateway,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._sender = sender
        self._gateway = gateway

    async def recover_interrupted(self) -> int:
        async with transaction(self._factory) as s:
            res = await s.execute(
                sa.update(Customer)
                .where(Customer.welcome_status == WelcomeStatus.SENDING)
                .values(
                    welcome_status=WelcomeStatus.UNKNOWN,
                    welcome_error="Yuborish jarayonida worker to'xtadi; takroriy yuborilmaydi",
                )
            )
        return res.rowcount or 0

    async def _claim(self, limit: int) -> list[int]:
        async with transaction(self._factory) as s:
            ids = (
                await s.scalars(
                    sa.select(Customer.id)
                    .where(Customer.welcome_status == WelcomeStatus.PENDING, Customer.welcome_due_at <= utcnow())
                    .order_by(Customer.welcome_due_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if ids:
                await s.execute(
                    sa.update(Customer)
                    .where(Customer.id.in_(ids))
                    .values(welcome_status=WelcomeStatus.SENDING, welcome_attempts=Customer.welcome_attempts + 1)
                )
        return list(ids)

    async def run_once(self, limit: int = 10) -> int:
        processed = 0
        for customer_id in await self._claim(limit):
            await self._process(customer_id)
            processed += 1
        return processed

    async def _set(self, customer_id: int, **values: object) -> None:
        async with transaction(self._factory) as s:
            await s.execute(sa.update(Customer).where(Customer.id == customer_id).values(**values))

    async def _process(self, customer_id: int) -> None:
        settings = await self._settings.get()
        async with self._factory() as s:
            customer = await s.get(Customer, customer_id)
            conv = await s.scalar(sa.select(Conversation).where(Conversation.customer_id == customer_id))
        if customer is None or conv is None:
            return
        user_id = customer.telegram_user_id

        if not settings.welcome_enabled or user_id in settings.welcome_excluded_user_ids or customer.is_excluded:
            await self._set(
                customer_id,
                welcome_status=WelcomeStatus.NOT_APPLICABLE,
                welcome_error="Avtomatik javob o'chirilgan yoki mijoz istisno qilingan",
            )
            return
        if conv.last_human_reply_at is not None:
            await self._set(
                customer_id,
                welcome_status=WelcomeStatus.NOT_APPLICABLE,
                welcome_error="Operator avtomatik javobdan oldin javob berdi",
            )
            return

        try:
            trigger = customer.welcome_trigger_message_id
            if settings.welcome_only_new_chats and trigger and await self._gateway.has_history_before(user_id, trigger):
                await self._set(
                    customer_id,
                    welcome_status=WelcomeStatus.EXISTING,
                    welcome_error="Chatda avvalgi yozishmalar bor - yangi mijoz emas",
                )
                return
            async with self._sender.chat_lock(user_id):
                sent = await self._sender.send(
                    user_id, settings.welcome_text, link_preview=settings.welcome_link_preview
                )
                self._sender.remember_automated(sent.message_id)
                async with transaction(self._factory) as s:
                    await s.execute(
                        pg_insert(Message)
                        .values(
                            conversation_id=conv.id,
                            telegram_message_id=sent.message_id,
                            direction=MessageDirection.OUT,
                            sender_type=SenderType.AUTOMATION,
                            source=MessageSource.WELCOME,
                            counts_as_reply=False,
                            sent_at=sent.date,
                        )
                        .on_conflict_do_nothing(constraint="uq_messages_conv_tgid")
                    )
                    await s.execute(
                        sa.update(Customer)
                        .where(Customer.id == customer_id)
                        .values(
                            welcome_status=WelcomeStatus.SENT,
                            welcome_sent_at=sent.date,
                            welcome_message_id=sent.message_id,
                            welcome_error=None,
                        )
                    )
                    c = await s.get(Conversation, conv.id, with_for_update=True)
                    assert c is not None
                    if c.last_outgoing_at is None or sent.date >= c.last_outgoing_at:
                        c.last_outgoing_at = sent.date
                    if c.last_message_at is None or sent.date >= c.last_message_at:
                        c.last_message_at = sent.date
                        c.last_message_direction = MessageDirection.OUT
            log.info("welcome_sent", customer_id=customer_id)
        except SendError as exc:
            await self._handle_error(customer_id, customer.welcome_attempts, exc)

    async def _handle_error(self, customer_id: int, attempts: int, exc: SendError) -> None:
        now = utcnow()
        if exc.kind == SendErrorKind.FLOOD:
            await self._set(
                customer_id,
                welcome_status=WelcomeStatus.PENDING,
                welcome_attempts=Customer.welcome_attempts - 1,
                welcome_due_at=now + timedelta(seconds=exc.retry_after or 60),
                welcome_error=exc.message,
            )
        elif exc.kind in (SendErrorKind.TRANSIENT, SendErrorKind.UNAUTHORIZED) and attempts < MAX_WELCOME_ATTEMPTS:
            delay = exc.retry_after or backoff_seconds(attempts)
            await self._set(
                customer_id,
                welcome_status=WelcomeStatus.PENDING,
                welcome_due_at=now + timedelta(seconds=delay),
                welcome_error=exc.message,
            )
        else:
            await self._set(customer_id, welcome_status=WelcomeStatus.FAILED, welcome_error=exc.message[:500])
        log.warning("welcome_send_failed", customer_id=customer_id, kind=exc.kind, code=exc.code)
