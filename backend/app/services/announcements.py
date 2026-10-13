"""Scheduled group announcements: persistent scheduling and idempotent delivery.

Data flow (all state in PostgreSQL, so restarts lose nothing):

  campaign (SCHEDULED) --materialize--> run (PENDING, unique per occurrence)
  run (due) --start--> RUNNING + one delivery per target (unique per run+group)
  delivery PENDING --claim (SKIP LOCKED, committed)--> SENDING --Telegram--> SENT | retry | FAILED
  run --when no delivery is pending/sending--> COMPLETED | PARTIAL | FAILED

Guarantees
  * An occurrence is materialized at most once: UNIQUE(campaign_id, scheduled_for).
  * A group receives at most one message per run: UNIQUE(run_id, group_id) and the SENDING
    claim is committed before calling Telegram. A crash during the call leaves SENDING, which
    startup recovery turns into UNKNOWN - visible in history and never re-sent automatically.
  * Multiple worker processes are safe: every claim uses FOR UPDATE SKIP LOCKED. (In practice
    only one worker runs, guarded by a PostgreSQL advisory lock; see workers/main.py.)
  * A failure in one group never blocks others; permanent errors (no permission, banned,
    invalid group) are not retried; transient errors retry with exponential backoff;
    flood waits postpone the delivery without consuming an attempt.
  * Runs that were due while the worker was down longer than `misfire_grace_minutes` are
    marked MISSED instead of being sent late.
"""

from __future__ import annotations

import time
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.enums import CampaignStatus, DeliveryStatus, RunStatus, ScheduleType
from app.db.models import (
    AnnouncementCampaign,
    AnnouncementDelivery,
    AnnouncementRun,
    CampaignTarget,
    TelegramGroup,
)
from app.db.session import SessionFactory, transaction
from app.services.app_settings import SettingsCache
from app.services.recurrence import Schedule, next_occurrence
from app.services.sender import TelegramSender, backoff_seconds
from app.telegram.types import SendError, SendErrorKind

log = get_logger(__name__)

ACTIVE_DELIVERY = (DeliveryStatus.PENDING, DeliveryStatus.SENDING)


def schedule_of(c: AnnouncementCampaign) -> Schedule:
    return Schedule(
        schedule_type=c.schedule_type,
        run_at=c.run_at,
        time_of_day=c.time_of_day,
        weekdays=tuple(c.weekdays or ()),
        start_date=c.start_date,
        end_date=c.end_date,
        timezone=c.timezone,
    )


async def materialize_campaign(session: AsyncSession, c: AnnouncementCampaign, grace: timedelta) -> None:
    """Ensure the next occurrence of a SCHEDULED campaign exists as a PENDING run.
    Completes the campaign when its schedule is exhausted and nothing is in flight."""
    now = utcnow()
    pending = await session.scalar(
        sa.select(sa.func.count())
        .select_from(AnnouncementRun)
        .where(
            AnnouncementRun.campaign_id == c.id,
            AnnouncementRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]),
        )
    )
    if pending:
        next_pending = await session.scalar(
            sa.select(sa.func.min(AnnouncementRun.scheduled_for)).where(
                AnnouncementRun.campaign_id == c.id, AnnouncementRun.status == RunStatus.PENDING
            )
        )
        c.next_run_at = next_pending
        return
    last = await session.scalar(
        sa.select(sa.func.max(AnnouncementRun.scheduled_for)).where(
            AnnouncementRun.campaign_id == c.id, AnnouncementRun.is_manual.is_(False)
        )
    )
    if c.schedule_type == ScheduleType.ONCE:
        if last is not None or c.run_at is None:
            c.status = CampaignStatus.COMPLETED
            c.next_run_at = None
            return
        occurrence = c.run_at  # may be in the past ("send now"): executed immediately
    else:
        baseline = max(last, now - grace) if last else now - grace
        occurrence = next_occurrence(schedule_of(c), baseline)
        if occurrence is None:
            c.status = CampaignStatus.COMPLETED
            c.next_run_at = None
            return
    await session.execute(
        pg_insert(AnnouncementRun)
        .values(campaign_id=c.id, scheduled_for=occurrence, status=RunStatus.PENDING)
        .on_conflict_do_nothing(constraint="uq_announcement_runs_occurrence")
    )
    c.next_run_at = occurrence


async def create_deliveries(session: AsyncSession, run: AnnouncementRun, campaign: AnnouncementCampaign) -> int:
    """Create one delivery per target. Disabled / non-sendable groups are recorded as SKIPPED;
    dry-run campaigns record DRY_RUN without contacting Telegram."""
    targets = (
        await session.execute(
            sa.select(CampaignTarget, TelegramGroup)
            .join(TelegramGroup, TelegramGroup.id == CampaignTarget.group_id)
            .where(CampaignTarget.campaign_id == campaign.id)
            .order_by(CampaignTarget.id)
        )
    ).all()
    now = utcnow()
    for target, group in targets:
        text = (target.custom_text or "").strip() or campaign.default_text
        status = DeliveryStatus.PENDING
        code = message = None
        if not group.is_enabled:
            status, code, message = DeliveryStatus.SKIPPED, "group_disabled", "Guruh e'lonlar uchun o'chirilgan"
        elif not group.is_member or not group.can_send:
            status, code = DeliveryStatus.SKIPPED, "no_permission"
            message = group.permission_note or "Akkaunt bu guruhga yoza olmaydi"
        elif campaign.dry_run:
            status, code, message = DeliveryStatus.DRY_RUN, "dry_run", "Sinov rejimi: xabar yuborilmadi"
        await session.execute(
            pg_insert(AnnouncementDelivery)
            .values(
                run_id=run.id,
                group_id=group.id,
                text=text,
                status=status,
                error_code=code,
                error_message=message,
                next_attempt_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_announcement_deliveries_pair")
        )
    return len(targets)


async def finalize_run(session: AsyncSession, run: AnnouncementRun) -> bool:
    counts = dict(
        (
            await session.execute(
                sa.select(AnnouncementDelivery.status, sa.func.count())
                .where(AnnouncementDelivery.run_id == run.id)
                .group_by(AnnouncementDelivery.status)
            )
        ).all()
    )
    if any(counts.get(s, 0) for s in ACTIVE_DELIVERY):
        return False
    ok = counts.get(DeliveryStatus.SENT, 0) + counts.get(DeliveryStatus.DRY_RUN, 0)
    bad = counts.get(DeliveryStatus.FAILED, 0) + counts.get(DeliveryStatus.UNKNOWN, 0)
    skipped = counts.get(DeliveryStatus.SKIPPED, 0)
    cancelled = counts.get(DeliveryStatus.CANCELLED, 0)
    if cancelled and ok == 0 and bad == 0:
        run.status = RunStatus.CANCELLED
    elif bad == 0 and skipped == 0 and cancelled == 0:
        run.status = RunStatus.COMPLETED
    elif ok == 0:
        run.status = RunStatus.FAILED
    else:
        run.status = RunStatus.PARTIAL
    run.finished_at = utcnow()
    return True


class AnnouncementScheduler:
    def __init__(self, factory: SessionFactory, settings: SettingsCache, sender: TelegramSender) -> None:
        self._factory = factory
        self._settings = settings
        self._sender = sender
        self._last_group_send = 0.0

    async def recover_interrupted(self) -> int:
        async with transaction(self._factory) as s:
            res = await s.execute(
                sa.update(AnnouncementDelivery)
                .where(AnnouncementDelivery.status == DeliveryStatus.SENDING)
                .values(
                    status=DeliveryStatus.UNKNOWN,
                    error_code="interrupted",
                    error_message="Yuborish jarayonida worker to'xtadi; holat noma'lum, qayta yuborilmaydi",
                )
            )
        return res.rowcount or 0

    async def tick(self) -> None:
        settings = await self._settings.get()
        grace = timedelta(minutes=settings.misfire_grace_minutes)
        await self.materialize(grace)
        await self.start_due_runs(grace)
        await self.process_deliveries(settings.announcement_min_interval_seconds, settings.announcement_max_attempts)
        await self.finalize_runs()

    async def materialize(self, grace: timedelta) -> None:
        async with transaction(self._factory) as s:
            campaigns = (
                await s.scalars(
                    sa.select(AnnouncementCampaign)
                    .where(AnnouncementCampaign.status == CampaignStatus.SCHEDULED)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for c in campaigns:
                await materialize_campaign(s, c, grace)

    async def start_due_runs(self, grace: timedelta) -> int:
        now = utcnow()
        started = 0
        async with transaction(self._factory) as s:
            runs = (
                await s.scalars(
                    sa.select(AnnouncementRun)
                    .join(AnnouncementCampaign, AnnouncementCampaign.id == AnnouncementRun.campaign_id)
                    .where(
                        AnnouncementRun.status == RunStatus.PENDING,
                        AnnouncementRun.scheduled_for <= now,
                        AnnouncementCampaign.status == CampaignStatus.SCHEDULED,
                    )
                    .options(selectinload(AnnouncementRun.campaign))
                    .order_by(AnnouncementRun.scheduled_for)
                    .limit(20)
                    .with_for_update(of=AnnouncementRun, skip_locked=True)
                )
            ).all()
            for run in runs:
                if not run.is_manual and now - run.scheduled_for > grace:
                    run.status = RunStatus.MISSED
                    run.finished_at = now
                    log.warning("announcement_run_missed", run_id=run.id, campaign_id=run.campaign_id)
                    continue
                run.status = RunStatus.RUNNING
                run.started_at = now
                run.campaign.last_run_at = now
                await create_deliveries(s, run, run.campaign)
                started += 1
        return started

    async def _claim_delivery(self) -> int | None:
        async with transaction(self._factory) as s:
            delivery_id = await s.scalar(
                sa.select(AnnouncementDelivery.id)
                .join(AnnouncementRun, AnnouncementRun.id == AnnouncementDelivery.run_id)
                .join(AnnouncementCampaign, AnnouncementCampaign.id == AnnouncementRun.campaign_id)
                .where(
                    AnnouncementDelivery.status == DeliveryStatus.PENDING,
                    AnnouncementDelivery.next_attempt_at <= utcnow(),
                    AnnouncementRun.status == RunStatus.RUNNING,
                    # paused / cancelled campaigns stop sending immediately
                    AnnouncementCampaign.status == CampaignStatus.SCHEDULED,
                )
                .order_by(AnnouncementDelivery.next_attempt_at, AnnouncementDelivery.id)
                .limit(1)
                .with_for_update(of=AnnouncementDelivery, skip_locked=True)
            )
            if delivery_id is not None:
                await s.execute(
                    sa.update(AnnouncementDelivery)
                    .where(AnnouncementDelivery.id == delivery_id)
                    .values(status=DeliveryStatus.SENDING, attempts=AnnouncementDelivery.attempts + 1)
                )
        return delivery_id

    async def process_deliveries(self, min_interval: int, max_attempts: int, budget: int = 10) -> int:
        """Send up to `budget` due deliveries, at most one per `min_interval` seconds."""
        sent = 0
        for _ in range(budget):
            if time.monotonic() - self._last_group_send < min_interval:
                break
            if self._sender.flood_remaining():
                break
            delivery_id = await self._claim_delivery()
            if delivery_id is None:
                break
            self._last_group_send = time.monotonic()
            if await self._deliver(delivery_id, max_attempts):
                sent += 1
        return sent

    async def _deliver(self, delivery_id: int, max_attempts: int) -> bool:
        async with self._factory() as s:
            row = (
                await s.execute(
                    sa.select(AnnouncementDelivery, TelegramGroup)
                    .join(TelegramGroup, TelegramGroup.id == AnnouncementDelivery.group_id)
                    .where(AnnouncementDelivery.id == delivery_id)
                )
            ).one()
        delivery, group = row
        now = utcnow()
        try:
            sent = await self._sender.send(group.telegram_id, delivery.text, link_preview=True)
        except SendError as exc:
            values: dict[str, object] = {"error_code": exc.code[:64], "error_message": exc.message[:500]}
            group_update: dict[str, object] | None = None
            if exc.kind == SendErrorKind.FLOOD:
                values.update(
                    status=DeliveryStatus.PENDING,
                    attempts=AnnouncementDelivery.attempts - 1,
                    next_attempt_at=now + timedelta(seconds=exc.retry_after or 60),
                )
            elif exc.kind in (SendErrorKind.TRANSIENT, SendErrorKind.UNAUTHORIZED) and delivery.attempts < max_attempts:
                values.update(
                    status=DeliveryStatus.PENDING,
                    next_attempt_at=now + timedelta(seconds=exc.retry_after or backoff_seconds(delivery.attempts)),
                )
            else:
                values.update(status=DeliveryStatus.FAILED)
                if exc.kind == SendErrorKind.PERMANENT and exc.extra.get("group_permission"):
                    group_update = {"can_send": False, "permission_note": exc.message[:255]}
            async with transaction(self._factory) as s:
                await s.execute(
                    sa.update(AnnouncementDelivery).where(AnnouncementDelivery.id == delivery_id).values(**values)
                )
                if group_update:
                    await s.execute(sa.update(TelegramGroup).where(TelegramGroup.id == group.id).values(**group_update))
            log.warning("announcement_delivery_failed", delivery_id=delivery_id, kind=exc.kind, code=exc.code)
            return False
        async with transaction(self._factory) as s:
            await s.execute(
                sa.update(AnnouncementDelivery)
                .where(AnnouncementDelivery.id == delivery_id)
                .values(
                    status=DeliveryStatus.SENT,
                    telegram_message_id=sent.message_id,
                    sent_at=sent.date,
                    error_code=None,
                    error_message=None,
                )
            )
        log.info("announcement_delivered", delivery_id=delivery_id, group_id=group.id)
        return True

    async def finalize_runs(self) -> int:
        done = 0
        async with transaction(self._factory) as s:
            runs = (
                await s.scalars(
                    sa.select(AnnouncementRun)
                    .where(AnnouncementRun.status == RunStatus.RUNNING)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for run in runs:
                if await finalize_run(s, run):
                    done += 1
        return done
