"""Announcement campaign management (API side). Execution is in services/announcements.py."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.timeutil import DISPLAY_TZ, ensure_utc, utcnow
from app.db.enums import CampaignStatus, DeliveryStatus, RunStatus, ScheduleType
from app.db.models import (
    Admin,
    AnnouncementCampaign,
    AnnouncementDelivery,
    AnnouncementRun,
    CampaignTarget,
    TelegramGroup,
)
from app.schemas.api import CampaignIn, CampaignOut, RunOut, TargetOut
from app.services.announcements import schedule_of
from app.services.formatting import parse_message
from app.services.recurrence import next_occurrence

EDITABLE = {CampaignStatus.DRAFT, CampaignStatus.SCHEDULED, CampaignStatus.PAUSED}


def _local_day_start(d: date | None) -> datetime | None:
    return None if d is None else datetime.combine(d, time.min, tzinfo=DISPLAY_TZ).astimezone(ZoneInfo("UTC"))


def _local_day_end(d: date | None) -> datetime | None:
    return None if d is None else datetime.combine(d, time(23, 59, 59), tzinfo=DISPLAY_TZ).astimezone(ZoneInfo("UTC"))


def _to_local_date(dt: datetime | None) -> date | None:
    return None if dt is None else ensure_utc(dt).astimezone(DISPLAY_TZ).date()


async def _load(db: AsyncSession, campaign_id: int, *, lock: bool = False) -> AnnouncementCampaign:
    q = (
        sa.select(AnnouncementCampaign)
        .where(AnnouncementCampaign.id == campaign_id)
        .options(selectinload(AnnouncementCampaign.targets).selectinload(CampaignTarget.group))
    )
    if lock:
        q = q.with_for_update(of=AnnouncementCampaign)
    c = await db.scalar(q)
    if c is None:
        raise NotFoundError("E'lon topilmadi")
    return c


async def campaign_out(db: AsyncSession, c: AnnouncementCampaign) -> CampaignOut:
    last_status = await db.scalar(
        sa.select(AnnouncementRun.status)
        .where(AnnouncementRun.campaign_id == c.id, AnnouncementRun.status.not_in([RunStatus.PENDING]))
        .order_by(AnnouncementRun.scheduled_for.desc())
        .limit(1)
    )
    return CampaignOut(
        id=c.id,
        title=c.title,
        default_text=c.default_text,
        status=c.status,
        schedule_type=c.schedule_type,
        run_at=c.run_at,
        time_of_day=c.time_of_day,
        weekdays=list(c.weekdays or []),
        start_date=_to_local_date(c.start_date),
        end_date=_to_local_date(c.end_date),
        dry_run=c.dry_run,
        next_run_at=c.next_run_at,
        last_run_at=c.last_run_at,
        created_at=c.created_at,
        updated_at=c.updated_at,
        targets=[
            TargetOut(
                group_id=t.group_id,
                group_title=t.group.title,
                group_can_send=t.group.can_send and t.group.is_member,
                group_enabled=t.group.is_enabled,
                custom_text=t.custom_text,
            )
            for t in c.targets
        ],
        last_run_status=last_status,
    )


async def _validate(db: AsyncSession, data: CampaignIn) -> None:
    errors: list[str] = []
    default_ok = bool(data.default_text.strip())
    if default_ok:
        parsed = parse_message(data.default_text)
        errors += [f"Asosiy matn: {e}" for e in parsed.errors]
    groups = {
        g.id: g
        for g in (
            await db.scalars(sa.select(TelegramGroup).where(TelegramGroup.id.in_([t.group_id for t in data.targets])))
        ).all()
    }
    for t in data.targets:
        g = groups.get(t.group_id)
        if g is None:
            errors.append(f"Guruh #{t.group_id} topilmadi")
            continue
        if not g.is_enabled:
            errors.append(f'"{g.title}" guruhi e\'lonlar uchun yoqilmagan')
        custom = (t.custom_text or "").strip()
        if custom:
            errors += [f'"{g.title}" matni: {e}' for e in parse_message(custom).errors]
        elif not default_ok:
            errors.append(f"\"{g.title}\" uchun matn yo'q (asosiy matn ham bo'sh)")
    if errors:
        raise ValidationAppError("; ".join(dict.fromkeys(errors)), code="invalid_campaign")


def _apply(c: AnnouncementCampaign, data: CampaignIn) -> None:
    c.title = data.title
    c.default_text = data.default_text
    c.schedule_type = data.schedule_type
    c.run_at = ensure_utc(data.run_at) if data.run_at and data.schedule_type == ScheduleType.ONCE else None
    c.time_of_day = data.time_of_day if data.schedule_type != ScheduleType.ONCE else None
    c.weekdays = data.weekdays if data.schedule_type == ScheduleType.WEEKLY else None
    c.start_date = _local_day_start(data.start_date) if data.schedule_type != ScheduleType.ONCE else None
    c.end_date = _local_day_end(data.end_date) if data.schedule_type != ScheduleType.ONCE else None
    c.dry_run = data.dry_run
    c.timezone = "Asia/Tashkent"


async def create_campaign(db: AsyncSession, data: CampaignIn, actor: Admin) -> AnnouncementCampaign:
    await _validate(db, data)
    c = AnnouncementCampaign(status=CampaignStatus.DRAFT, created_by_admin_id=actor.id)
    _apply(c, data)
    c.targets = [
        CampaignTarget(group_id=t.group_id, custom_text=(t.custom_text or "").strip() or None) for t in data.targets
    ]
    db.add(c)
    await db.flush()
    return await _load(db, c.id)


async def update_campaign(db: AsyncSession, campaign_id: int, data: CampaignIn) -> AnnouncementCampaign:
    c = await _load(db, campaign_id, lock=True)
    if c.status not in EDITABLE:
        raise ConflictError("Yakunlangan yoki bekor qilingan e'lonni tahrirlab bo'lmaydi")
    await _validate(db, data)
    _apply(c, data)
    existing = {t.group_id: t for t in c.targets}
    wanted = {t.group_id: t for t in data.targets}
    for gid, t in list(existing.items()):
        if gid not in wanted:
            c.targets.remove(t)
    for gid, t in wanted.items():
        custom = (t.custom_text or "").strip() or None
        if gid in existing:
            existing[gid].custom_text = custom
        else:
            c.targets.append(CampaignTarget(group_id=gid, custom_text=custom))
    # Pending (not yet started) occurrences are dropped and re-materialized from the new schedule.
    await db.execute(
        sa.delete(AnnouncementRun).where(
            AnnouncementRun.campaign_id == c.id, AnnouncementRun.status == RunStatus.PENDING
        )
    )
    c.next_run_at = None
    await db.flush()
    db.expire(c)
    return await _load(db, c.id)


def _require_confirmation(c: AnnouncementCampaign, confirm: bool) -> None:
    if len(c.targets) > 1 and not confirm:
        raise ValidationAppError(
            f"Xabar {len(c.targets)} ta guruhga yuboriladi. Tasdiqlash talab qilinadi.", code="confirmation_required"
        )


def preview_next_run(c: AnnouncementCampaign) -> datetime | None:
    if c.schedule_type == ScheduleType.ONCE:
        return c.run_at or utcnow()
    return next_occurrence(schedule_of(c), utcnow())


async def activate(db: AsyncSession, campaign_id: int, confirm: bool) -> AnnouncementCampaign:
    c = await _load(db, campaign_id, lock=True)
    if c.status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED):
        raise ConflictError("Faqat qoralama yoki to'xtatilgan e'lonni faollashtirish mumkin")
    _require_confirmation(c, confirm)
    if c.schedule_type == ScheduleType.ONCE:
        if c.run_at is None:
            c.run_at = utcnow()  # no time chosen = send as soon as possible
        elif c.run_at < utcnow() - timedelta(minutes=1):
            raise ValidationAppError(
                "Yuborish vaqti o'tib ketgan. Yangi vaqt tanlang yoki «Hozir yuborish»dan foydalaning"
            )
    if c.schedule_type != ScheduleType.ONCE and preview_next_run(c) is None:
        raise ValidationAppError("Jadval bo'yicha kelajakda yuborish vaqti yo'q (tugash sanasini tekshiring)")
    c.status = CampaignStatus.SCHEDULED
    c.next_run_at = preview_next_run(c)
    return c


async def pause(db: AsyncSession, campaign_id: int) -> AnnouncementCampaign:
    c = await _load(db, campaign_id, lock=True)
    if c.status != CampaignStatus.SCHEDULED:
        raise ConflictError("Faqat faol e'lonni to'xtatish mumkin")
    c.status = CampaignStatus.PAUSED
    return c


async def resume(db: AsyncSession, campaign_id: int) -> AnnouncementCampaign:
    c = await _load(db, campaign_id, lock=True)
    if c.status != CampaignStatus.PAUSED:
        raise ConflictError("Faqat to'xtatilgan e'lonni davom ettirish mumkin")
    c.status = CampaignStatus.SCHEDULED
    return c


async def cancel(db: AsyncSession, campaign_id: int) -> AnnouncementCampaign:
    c = await _load(db, campaign_id, lock=True)
    if c.status in (CampaignStatus.COMPLETED, CampaignStatus.CANCELLED):
        raise ConflictError("E'lon allaqachon yakunlangan")
    c.status = CampaignStatus.CANCELLED
    c.next_run_at = None
    run_ids = sa.select(AnnouncementRun.id).where(AnnouncementRun.campaign_id == c.id).scalar_subquery()
    await db.execute(
        sa.update(AnnouncementDelivery)
        .where(AnnouncementDelivery.run_id.in_(run_ids), AnnouncementDelivery.status == DeliveryStatus.PENDING)
        .values(status=DeliveryStatus.CANCELLED, error_message="E'lon bekor qilindi")
    )
    await db.execute(
        sa.update(AnnouncementRun)
        .where(AnnouncementRun.campaign_id == c.id, AnnouncementRun.status == RunStatus.PENDING)
        .values(status=RunStatus.CANCELLED, finished_at=utcnow())
    )
    return c


async def send_now(db: AsyncSession, campaign_id: int, confirm: bool) -> AnnouncementCampaign:
    """Queue an immediate manual run. For a draft one-time campaign this activates it."""
    c = await _load(db, campaign_id, lock=True)
    if c.status in (CampaignStatus.COMPLETED, CampaignStatus.CANCELLED):
        raise ConflictError("Yakunlangan yoki bekor qilingan e'lonni yuborib bo'lmaydi")
    _require_confirmation(c, confirm)
    if c.schedule_type == ScheduleType.ONCE:
        if c.status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED):
            raise ConflictError("Bir martalik e'lon allaqachon rejalashtirilgan")
        c.run_at = utcnow()
        c.status = CampaignStatus.SCHEDULED
        await db.execute(
            sa.delete(AnnouncementRun).where(
                AnnouncementRun.campaign_id == c.id, AnnouncementRun.status == RunStatus.PENDING
            )
        )
        c.next_run_at = c.run_at
        return c
    if c.status != CampaignStatus.SCHEDULED:
        raise ConflictError("Takroriy e'lonni darhol yuborish uchun avval uni faollashtiring")
    db.add(AnnouncementRun(campaign_id=c.id, scheduled_for=utcnow(), status=RunStatus.PENDING, is_manual=True))
    return c


async def list_runs(db: AsyncSession, campaign_id: int, limit: int = 30) -> list[RunOut]:
    runs = (
        await db.scalars(
            sa.select(AnnouncementRun)
            .where(AnnouncementRun.campaign_id == campaign_id)
            .order_by(AnnouncementRun.scheduled_for.desc())
            .limit(limit)
        )
    ).all()
    counts: dict[int, dict[str, int]] = {r.id: {} for r in runs}
    if runs:
        for run_id, status, n in (
            await db.execute(
                sa.select(AnnouncementDelivery.run_id, AnnouncementDelivery.status, sa.func.count())
                .where(AnnouncementDelivery.run_id.in_(list(counts)))
                .group_by(AnnouncementDelivery.run_id, AnnouncementDelivery.status)
            )
        ).all():
            counts[run_id][str(status.value if hasattr(status, "value") else status)] = n
    return [
        RunOut(
            id=r.id,
            scheduled_for=r.scheduled_for,
            status=r.status,
            is_manual=r.is_manual,
            started_at=r.started_at,
            finished_at=r.finished_at,
            counts=counts[r.id],
        )
        for r in runs
    ]
