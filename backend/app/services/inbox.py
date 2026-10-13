"""Inbox processing: records private conversations, queues first-contact messages,
opens/updates SLA incidents and resolves them when a real human reply is observed.

Classification rules for outgoing messages in a monitored private chat
------------------------------------------------------------------------
An outgoing message counts as a *human reply* (resolves the open SLA incident) unless:
  * it was sent by this system (welcome message) - recorded by the sender before the
    Telegram update is processed, guarded by the per-chat lock;
  * it was sent through a connected Telegram Business bot (`via_business_bot_id`);
  * its text is identical to the configured automatic first-contact message;
  * it is a forwarded message and `count_forwarded_as_reply` is disabled;
  * it is a service message (pins, calls, ...).
Edits never count as replies (only new messages are processed). Deleting a reply does not
reopen a resolved incident - the customer has already been answered once.

SLA policy for multiple customer messages
-----------------------------------------
One open incident per conversation. The incident starts at the *first* unanswered customer
message and its deadline does not move when the customer sends more messages (the customer
has been waiting since the first one). Further messages only update the counters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.timeutil import ensure_utc, utcnow
from app.db.enums import (
    AlertStatus,
    IncidentStatus,
    MessageDirection,
    MessageSource,
    Resolution,
    SenderType,
    WelcomeStatus,
)
from app.db.models import Conversation, Customer, Message, SlaIncident
from app.db.session import SessionFactory, transaction
from app.services.app_settings import RuntimeSettings, SettingsCache
from app.services.formatting import plain_text
from app.services.sender import TelegramSender
from app.telegram.types import TELEGRAM_SERVICE_USER_ID, TgMessage

log = get_logger(__name__)


class IngestOutcome(StrEnum):
    IGNORED = "ignored"
    DUPLICATE = "duplicate"
    INCOMING = "incoming"
    HUMAN_REPLY = "human_reply"
    AUTOMATED = "automated"
    NOT_A_REPLY = "not_a_reply"


@dataclass
class IngestResult:
    outcome: IngestOutcome
    reason: str | None = None
    new_customer: bool = False
    incident_id: int | None = None
    resolved_incident_id: int | None = None


def _truncate(text: str, limit: int) -> str | None:
    text = " ".join(text.split())
    if limit <= 0 or not text:
        return None
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def resolve_open_incident(
    session: AsyncSession,
    conversation_id: int,
    *,
    reply_message_id: int,
    reply_date,
    resolution: Resolution,
) -> int | None:
    """Resolve the conversation's open incident if `reply_message_id` is newer than the
    message that opened it. Returns the resolved incident id."""
    incident = await session.scalar(
        sa.select(SlaIncident)
        .where(SlaIncident.conversation_id == conversation_id, SlaIncident.status == IncidentStatus.OPEN)
        .with_for_update()
    )
    if incident is None or reply_message_id <= incident.first_telegram_message_id:
        return None
    reply_date = ensure_utc(reply_date)
    incident.status = IncidentStatus.RESOLVED
    incident.resolution = resolution
    incident.resolved_at = reply_date
    incident.resolved_by_telegram_message_id = reply_message_id
    incident.response_seconds = max(0, int((reply_date - incident.started_at).total_seconds()))
    if incident.alert_status in (AlertStatus.NONE, AlertStatus.PENDING):
        # Answered before an alert went out: nothing to send. A breach is still recorded
        # if the deadline had already passed.
        if reply_date > incident.deadline_at and incident.breached_at is None:
            incident.breached_at = incident.deadline_at
        incident.alert_status = AlertStatus.SKIPPED if incident.breached_at else AlertStatus.NONE
    return incident.id


class InboxService:
    def __init__(self, factory: SessionFactory, settings: SettingsCache, sender: TelegramSender) -> None:
        self._factory = factory
        self._settings = settings
        self._sender = sender

    async def handle(self, msg: TgMessage) -> IngestResult:
        user = msg.chat_user
        if msg.is_service:
            return IngestResult(IngestOutcome.IGNORED, "service_message")
        if user.is_self or user.is_bot or user.is_support or user.id == TELEGRAM_SERVICE_USER_ID:
            return IngestResult(IngestOutcome.IGNORED, "non_customer_chat")
        settings = await self._settings.get()
        async with self._sender.chat_lock(user.id):
            if msg.outgoing:
                return await self._handle_outgoing(msg, settings)
            return await self._handle_incoming(msg, settings)

    # ---------------------------------------------------------------------------------------
    async def _handle_incoming(self, msg: TgMessage, settings: RuntimeSettings) -> IngestResult:
        user = msg.chat_user
        date = ensure_utc(msg.date)
        async with transaction(self._factory) as s:
            customer = await s.scalar(sa.select(Customer).where(Customer.telegram_user_id == user.id).with_for_update())
            new_customer = False
            if customer is None:
                if user.id in settings.monitor_excluded_user_ids:
                    return IngestResult(IngestOutcome.IGNORED, "excluded")
                if settings.ignore_contacts and user.is_contact:
                    return IngestResult(IngestOutcome.IGNORED, "personal_contact")
                inserted = await s.scalar(
                    pg_insert(Customer)
                    .values(
                        telegram_user_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        first_seen_at=date,
                        welcome_status=WelcomeStatus.NOT_APPLICABLE,
                    )
                    .on_conflict_do_nothing(index_elements=[Customer.telegram_user_id])
                    .returning(Customer.id)
                )
                customer = await s.scalar(
                    sa.select(Customer).where(Customer.telegram_user_id == user.id).with_for_update()
                )
                assert customer is not None
                new_customer = inserted is not None
            else:
                if customer.is_excluded or user.id in settings.monitor_excluded_user_ids:
                    return IngestResult(IngestOutcome.IGNORED, "excluded")
                for attr in ("username", "first_name", "last_name"):
                    value = getattr(user, attr)
                    if value is not None and getattr(customer, attr) != value:
                        setattr(customer, attr, value)

            conv = await self._get_or_create_conversation(s, customer.id)

            preview = _truncate(msg.text, settings.preview_length) if settings.store_message_text else None
            msg_row_id = await s.scalar(
                pg_insert(Message)
                .values(
                    conversation_id=conv.id,
                    telegram_message_id=msg.message_id,
                    direction=MessageDirection.IN,
                    sender_type=SenderType.CUSTOMER,
                    source=MessageSource.TELEGRAM,
                    counts_as_reply=False,
                    is_forwarded=msg.is_forwarded,
                    has_media=msg.has_media,
                    text_preview=preview,
                    sent_at=date,
                )
                .on_conflict_do_nothing(constraint="uq_messages_conv_tgid")
                .returning(Message.id)
            )
            if msg_row_id is None:
                return IngestResult(IngestOutcome.DUPLICATE, "already_recorded")

            if conv.last_incoming_at is None or date >= conv.last_incoming_at:
                conv.last_incoming_at = date
            if conv.last_message_at is None or date >= conv.last_message_at:
                conv.last_message_at = date
                conv.last_message_direction = MessageDirection.IN
                conv.last_message_preview = preview or ("[media]" if msg.has_media else None)
            conv.last_telegram_message_id = max(conv.last_telegram_message_id or 0, msg.message_id)

            if new_customer:
                if settings.welcome_enabled and user.id not in settings.welcome_excluded_user_ids:
                    customer.welcome_status = WelcomeStatus.PENDING
                    customer.welcome_due_at = utcnow() + timedelta(seconds=settings.welcome_delay_seconds)
                    customer.welcome_trigger_message_id = msg.message_id
                else:
                    customer.welcome_status = WelcomeStatus.NOT_APPLICABLE

            incident_id = None
            if settings.sla_enabled:
                incident_id = await self._open_or_update_incident(s, conv, msg.message_id, date, settings)

        log.info(
            "incoming_message_recorded",
            customer_id=customer.id,
            conversation_id=conv.id,
            new_customer=new_customer,
            incident_id=incident_id,
        )
        return IngestResult(IngestOutcome.INCOMING, new_customer=new_customer, incident_id=incident_id)

    async def _get_or_create_conversation(self, s: AsyncSession, customer_id: int) -> Conversation:
        query = sa.select(Conversation).where(Conversation.customer_id == customer_id).with_for_update()
        conv = await s.scalar(query)
        if conv is None:
            # Insert only when missing (ON CONFLICT would consume an identity value on every message).
            await s.execute(
                pg_insert(Conversation)
                .values(customer_id=customer_id)
                .on_conflict_do_nothing(index_elements=[Conversation.customer_id])
            )
            conv = await s.scalar(query)
        assert conv is not None
        return conv

    async def _open_or_update_incident(
        self, s: AsyncSession, conv: Conversation, message_id: int, date, settings: RuntimeSettings
    ) -> int | None:
        if conv.last_human_reply_at is not None and date < conv.last_human_reply_at:
            return None  # already answered (out-of-order processing during reconciliation)
        incident = await s.scalar(
            sa.select(SlaIncident)
            .where(SlaIncident.conversation_id == conv.id, SlaIncident.status == IncidentStatus.OPEN)
            .with_for_update()
        )
        if incident is not None:
            incident.customer_message_count += 1
            if date > incident.last_customer_message_at:
                incident.last_customer_message_at = date
            return incident.id
        incident = SlaIncident(
            conversation_id=conv.id,
            status=IncidentStatus.OPEN,
            started_at=date,
            first_telegram_message_id=message_id,
            last_customer_message_at=date,
            customer_message_count=1,
            timeout_seconds=settings.sla_timeout_seconds,
            deadline_at=date + timedelta(seconds=settings.sla_timeout_seconds),
            alert_status=AlertStatus.NONE,
        )
        s.add(incident)
        await s.flush()
        return incident.id

    # ---------------------------------------------------------------------------------------
    def _is_automated(self, msg: TgMessage, settings: RuntimeSettings) -> bool:
        if msg.via_business_bot or self._sender.is_automated(msg.message_id):
            return True
        if settings.welcome_text.strip():
            template = plain_text(settings.welcome_text).strip()
            if template and msg.text.strip() == template:
                return True
        return False

    async def _handle_outgoing(self, msg: TgMessage, settings: RuntimeSettings) -> IngestResult:
        user = msg.chat_user
        date = ensure_utc(msg.date)
        async with transaction(self._factory) as s:
            customer = await s.scalar(sa.select(Customer).where(Customer.telegram_user_id == user.id))
            if customer is None or customer.is_excluded or user.id in settings.monitor_excluded_user_ids:
                # Chats initiated by the operator (no customer message yet) are not monitored.
                return IngestResult(IngestOutcome.IGNORED, "not_monitored")
            conv = await self._get_or_create_conversation(s, customer.id)
            existing = await s.scalar(
                sa.select(Message.id).where(
                    Message.conversation_id == conv.id, Message.telegram_message_id == msg.message_id
                )
            )
            if existing is not None:
                return IngestResult(IngestOutcome.DUPLICATE, "already_recorded")

            automated = self._is_automated(msg, settings)
            counts = not automated and (not msg.is_forwarded or settings.count_forwarded_as_reply)
            await s.execute(
                pg_insert(Message)
                .values(
                    conversation_id=conv.id,
                    telegram_message_id=msg.message_id,
                    direction=MessageDirection.OUT,
                    sender_type=SenderType.AUTOMATION if automated else SenderType.OPERATOR,
                    source=MessageSource.TELEGRAM,
                    counts_as_reply=counts,
                    is_forwarded=msg.is_forwarded,
                    has_media=msg.has_media,
                    # Operator reply text is kept only when a Super Admin enabled it; automated
                    # (welcome) messages are never stored here.
                    text_preview=(
                        _truncate(msg.text, settings.preview_length)
                        if settings.store_operator_text and not automated
                        else None
                    ),
                    sent_at=date,
                )
                .on_conflict_do_nothing(constraint="uq_messages_conv_tgid")
            )
            if conv.last_outgoing_at is None or date >= conv.last_outgoing_at:
                conv.last_outgoing_at = date
            if conv.last_message_at is None or date >= conv.last_message_at:
                conv.last_message_at = date
                conv.last_message_direction = MessageDirection.OUT
            conv.last_telegram_message_id = max(conv.last_telegram_message_id or 0, msg.message_id)
            resolved = None
            if counts:
                if conv.last_human_reply_at is None or date >= conv.last_human_reply_at:
                    conv.last_human_reply_at = date
                resolved = await resolve_open_incident(
                    s,
                    conv.id,
                    reply_message_id=msg.message_id,
                    reply_date=date,
                    resolution=Resolution.HUMAN_REPLY,
                )
        if automated:
            return IngestResult(IngestOutcome.AUTOMATED)
        if not counts:
            return IngestResult(IngestOutcome.NOT_A_REPLY, "forwarded")
        log.info("human_reply_recorded", conversation_id=conv.id, resolved_incident_id=resolved)
        return IngestResult(IngestOutcome.HUMAN_REPLY, resolved_incident_id=resolved)

    # ---------------------------------------------------------------------------------------
    async def mark_deleted(self, message_ids: list[int]) -> int:
        """Telegram reports deletions in private chats only by message id (unique per account)."""
        if not message_ids:
            return 0
        async with transaction(self._factory) as s:
            result = await s.execute(
                sa.update(Message)
                .where(Message.telegram_message_id.in_(message_ids), Message.deleted_at.is_(None))
                .values(deleted_at=utcnow())
            )
        return result.rowcount or 0

    async def mark_edited(self, msg: TgMessage) -> None:
        """Edits never count as replies; only the edit time (and customer preview) is updated."""
        settings = await self._settings.get()
        async with transaction(self._factory) as s:
            row = await s.scalar(
                sa.select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .join(Customer, Customer.id == Conversation.customer_id)
                .where(Customer.telegram_user_id == msg.chat_user.id, Message.telegram_message_id == msg.message_id)
            )
            if row is None:
                return
            row.edited_at = utcnow()
            if row.direction == MessageDirection.IN and settings.store_message_text:
                row.text_preview = _truncate(msg.text, settings.preview_length)
