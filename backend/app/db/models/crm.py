"""Customers, conversations, message metadata, SLA incidents and panel replies (outbox)."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db.base import Base, TimestampMixin, str_enum
from app.db.enums import (
    AlertStatus,
    IncidentStatus,
    MessageDirection,
    MessageSource,
    OutboxStatus,
    Resolution,
    SenderType,
    WelcomeStatus,
)


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        sa.Index("ix_customers_first_seen", "first_seen_at"),
        sa.Index("ix_customers_welcome_due", "welcome_status", "welcome_due_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(sa.BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(sa.String(64), index=True)
    first_name: Mapped[str | None] = mapped_column(sa.String(128))
    last_name: Mapped[str | None] = mapped_column(sa.String(128))
    first_seen_at: Mapped[datetime]
    is_excluded: Mapped[bool] = mapped_column(default=False, server_default=sa.false())

    welcome_status: Mapped[WelcomeStatus] = mapped_column(
        str_enum(WelcomeStatus, "welcome_status"), default=WelcomeStatus.NOT_APPLICABLE
    )
    welcome_due_at: Mapped[datetime | None]
    welcome_trigger_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    welcome_sent_at: Mapped[datetime | None]
    welcome_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    welcome_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    welcome_error: Mapped[str | None] = mapped_column(sa.String(500))

    conversation: Mapped[Conversation | None] = relationship(back_populates="customer", uselist=False)

    @property
    def display_name(self) -> str:
        name = " ".join(p for p in [self.first_name, self.last_name] if p).strip()
        return name or (f"@{self.username}" if self.username else f"ID {self.telegram_user_id}")


class Conversation(TimestampMixin, Base):
    """One private chat between the connected business account and a customer."""

    __tablename__ = "conversations"
    __table_args__ = (sa.Index("ix_conversations_last_message", "last_message_at"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    customer_id: Mapped[int] = mapped_column(sa.ForeignKey("customers.id", ondelete="CASCADE"), unique=True)
    assigned_admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admins.id", ondelete="SET NULL"), index=True)
    last_message_at: Mapped[datetime | None]
    last_incoming_at: Mapped[datetime | None]
    last_outgoing_at: Mapped[datetime | None]
    last_human_reply_at: Mapped[datetime | None]
    # Preview of the latest *customer* message (operator replies are never stored).
    last_message_preview: Mapped[str | None] = mapped_column(sa.String(300))
    last_message_direction: Mapped[MessageDirection | None] = mapped_column(
        str_enum(MessageDirection, "message_direction")
    )
    last_telegram_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)

    customer: Mapped[Customer] = relationship(back_populates="conversation")


class Message(Base):
    """Message metadata. Text is stored only as a truncated preview, only for customer
    messages, only when enabled in settings, and is purged by the retention job."""

    __tablename__ = "messages"
    __table_args__ = (
        sa.UniqueConstraint("conversation_id", "telegram_message_id", name="uq_messages_conv_tgid"),
        sa.Index("ix_messages_conv_sent", "conversation_id", "sent_at"),
        sa.Index("ix_messages_sent_at", "sent_at"),
        sa.Index("ix_messages_tg_id", "telegram_message_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(sa.ForeignKey("conversations.id", ondelete="CASCADE"))
    telegram_message_id: Mapped[int] = mapped_column(sa.BigInteger)
    direction: Mapped[MessageDirection] = mapped_column(str_enum(MessageDirection, "message_direction"))
    sender_type: Mapped[SenderType] = mapped_column(str_enum(SenderType, "sender_type"))
    source: Mapped[MessageSource] = mapped_column(str_enum(MessageSource, "message_source"))
    counts_as_reply: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    is_forwarded: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    has_media: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    text_preview: Mapped[str | None] = mapped_column(sa.String(1000))
    sent_at: Mapped[datetime]  # Telegram message date (UTC)
    recorded_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    edited_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]
    sent_by_admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admins.id", ondelete="SET NULL"))


class SlaIncident(TimestampMixin, Base):
    """A waiting cycle: opened by the first unanswered customer message, closed by the first
    real human reply. At most one open incident per conversation (partial unique index)."""

    __tablename__ = "sla_incidents"
    __table_args__ = (
        sa.Index(
            "uq_sla_incidents_one_open",
            "conversation_id",
            unique=True,
            postgresql_where=sa.text("status = 'open'"),
        ),
        sa.Index("ix_sla_incidents_due", "status", "alert_status", "deadline_at"),
        sa.Index("ix_sla_incidents_started", "started_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(sa.ForeignKey("conversations.id", ondelete="CASCADE"))
    status: Mapped[IncidentStatus] = mapped_column(
        str_enum(IncidentStatus, "incident_status"), default=IncidentStatus.OPEN
    )
    started_at: Mapped[datetime]  # date of the first unanswered customer message
    first_telegram_message_id: Mapped[int] = mapped_column(sa.BigInteger)
    last_customer_message_at: Mapped[datetime]
    customer_message_count: Mapped[int] = mapped_column(default=1, server_default="1")
    timeout_seconds: Mapped[int]
    deadline_at: Mapped[datetime]
    breached_at: Mapped[datetime | None]  # set when the deadline passed without a human reply

    alert_status: Mapped[AlertStatus] = mapped_column(str_enum(AlertStatus, "alert_status"), default=AlertStatus.NONE)
    alert_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    alert_next_attempt_at: Mapped[datetime | None]
    alerted_at: Mapped[datetime | None]
    alert_error: Mapped[str | None] = mapped_column(sa.String(500))

    resolved_at: Mapped[datetime | None]
    resolution: Mapped[Resolution | None] = mapped_column(str_enum(Resolution, "resolution"))
    resolved_by_telegram_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    response_seconds: Mapped[int | None]
    dismissed_by_admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admins.id", ondelete="SET NULL"))

    conversation: Mapped[Conversation] = relationship()


class OutgoingMessage(TimestampMixin, Base):
    """Replies written in the web panel. The API only queues them; the worker sends them
    through the centralized Telegram sender and records the real outcome."""

    __tablename__ = "outgoing_messages"
    __table_args__ = (sa.Index("ix_outgoing_due", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(sa.ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(sa.Text)
    requested_by_admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admins.id", ondelete="SET NULL"))
    status: Mapped[OutboxStatus] = mapped_column(str_enum(OutboxStatus, "outbox_status"), default=OutboxStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    telegram_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    error: Mapped[str | None] = mapped_column(sa.String(500))
    sent_at: Mapped[datetime | None]
