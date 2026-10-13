"""Telegram groups and scheduled announcement campaigns."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db.base import Base, TimestampMixin, str_enum
from app.db.enums import CampaignStatus, DeliveryStatus, GroupKind, GroupSource, RunStatus, ScheduleType


class TelegramGroup(TimestampMixin, Base):
    __tablename__ = "telegram_groups"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger, unique=True)  # marked peer id (e.g. -100...)
    title: Mapped[str] = mapped_column(sa.String(255))
    username: Mapped[str | None] = mapped_column(sa.String(64))
    kind: Mapped[GroupKind] = mapped_column(str_enum(GroupKind, "group_kind"))
    source: Mapped[GroupSource] = mapped_column(str_enum(GroupSource, "group_source"))
    participants_count: Mapped[int | None]
    is_member: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    can_send: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    permission_note: Mapped[str | None] = mapped_column(sa.String(255))
    # Explicit opt-in: only enabled groups can be selected as announcement targets.
    is_enabled: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    last_synced_at: Mapped[datetime | None]


class AnnouncementCampaign(TimestampMixin, Base):
    __tablename__ = "announcement_campaigns"
    __table_args__ = (sa.Index("ix_campaigns_status", "status"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(sa.String(160))
    default_text: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[CampaignStatus] = mapped_column(
        str_enum(CampaignStatus, "campaign_status"), default=CampaignStatus.DRAFT
    )
    schedule_type: Mapped[ScheduleType] = mapped_column(str_enum(ScheduleType, "schedule_type"))
    run_at: Mapped[datetime | None]  # ONCE: exact UTC instant
    time_of_day: Mapped[str | None] = mapped_column(sa.String(5))  # DAILY/WEEKLY: "HH:MM" local time
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(sa.SmallInteger))  # WEEKLY: 0=Mon..6=Sun
    start_date: Mapped[datetime | None]  # recurrence window (UTC instants)
    end_date: Mapped[datetime | None]
    timezone: Mapped[str] = mapped_column(sa.String(64), default="Asia/Tashkent")
    dry_run: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    created_by_admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admins.id", ondelete="SET NULL"))
    next_run_at: Mapped[datetime | None]
    last_run_at: Mapped[datetime | None]

    targets: Mapped[list[CampaignTarget]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignTarget.id"
    )


class CampaignTarget(Base):
    __tablename__ = "campaign_targets"
    __table_args__ = (sa.UniqueConstraint("campaign_id", "group_id", name="uq_campaign_targets_pair"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    campaign_id: Mapped[int] = mapped_column(sa.ForeignKey("announcement_campaigns.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(sa.ForeignKey("telegram_groups.id", ondelete="RESTRICT"), index=True)
    custom_text: Mapped[str | None] = mapped_column(sa.Text)  # per-group message; falls back to default_text

    campaign: Mapped[AnnouncementCampaign] = relationship(back_populates="targets")
    group: Mapped[TelegramGroup] = relationship()


class AnnouncementRun(Base):
    """One execution occurrence of a campaign. (campaign_id, scheduled_for) is unique so the
    same occurrence can never be materialized twice, even by concurrent workers."""

    __tablename__ = "announcement_runs"
    __table_args__ = (
        sa.UniqueConstraint("campaign_id", "scheduled_for", name="uq_announcement_runs_occurrence"),
        sa.Index("ix_announcement_runs_due", "status", "scheduled_for"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    campaign_id: Mapped[int] = mapped_column(sa.ForeignKey("announcement_campaigns.id", ondelete="CASCADE"))
    scheduled_for: Mapped[datetime]
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus, "run_status"), default=RunStatus.PENDING)
    is_manual: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    campaign: Mapped[AnnouncementCampaign] = relationship()
    deliveries: Mapped[list[AnnouncementDelivery]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AnnouncementDelivery.id"
    )


class AnnouncementDelivery(Base):
    """One message to one group within a run. (run_id, group_id) unique => idempotent."""

    __tablename__ = "announcement_deliveries"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "group_id", name="uq_announcement_deliveries_pair"),
        sa.Index("ix_announcement_deliveries_due", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(sa.ForeignKey("announcement_runs.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(sa.ForeignKey("telegram_groups.id", ondelete="RESTRICT"), index=True)
    text: Mapped[str] = mapped_column(sa.Text)  # snapshot at execution time
    status: Mapped[DeliveryStatus] = mapped_column(
        str_enum(DeliveryStatus, "delivery_status"), default=DeliveryStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    telegram_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    error_code: Mapped[str | None] = mapped_column(sa.String(64))
    error_message: Mapped[str | None] = mapped_column(sa.String(500))
    sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, server_default=sa.func.now())

    run: Mapped[AnnouncementRun] = relationship(back_populates="deliveries")
    group: Mapped[TelegramGroup] = relationship()
