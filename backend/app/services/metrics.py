"""Dashboard and report metrics, computed from persisted records only."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.timeutil import DISPLAY_TZ, utcnow
from app.db.enums import (
    AlertStatus,
    CampaignStatus,
    DeliveryStatus,
    IncidentStatus,
    Resolution,
    WelcomeStatus,
    WorkerStatus,
)
from app.db.models import (
    AnnouncementCampaign,
    AnnouncementDelivery,
    AnnouncementRun,
    Customer,
    SlaIncident,
    TelegramGroup,
    WorkerState,
)

REPLY_RESOLUTIONS = (Resolution.HUMAN_REPLY, Resolution.PANEL_REPLY)
BUCKETS: list[tuple[str, int, int | None]] = [
    ("1 daqiqagacha", 0, 60),
    ("1–5 daqiqa", 60, 300),
    ("5–15 daqiqa", 300, 900),
    ("15–60 daqiqa", 900, 3600),
    ("1 soatdan ko'p", 3600, None),
]


def local_day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=DISPLAY_TZ).astimezone(ZoneInfo("UTC"))


def today_start_utc() -> datetime:
    return local_day_start(utcnow().astimezone(DISPLAY_TZ).date())


async def worker_status(db: AsyncSession, settings: Settings) -> dict[str, Any]:
    ws = await db.get(WorkerState, 1)
    alive = bool(
        ws
        and ws.last_heartbeat_at
        and utcnow() - ws.last_heartbeat_at < timedelta(seconds=settings.worker_stale_after_seconds)
    )
    if ws is None:
        status: str = "unknown"
    elif not alive and ws.status != WorkerStatus.STOPPED:
        status = "offline"
    else:
        status = ws.status
    return {
        "status": status,
        "status_detail": ws.status_detail if ws else "Worker hali ishga tushmagan",
        "worker_alive": alive,
        "account_user_id": ws.account_user_id if ws else None,
        "account_username": ws.account_username if ws else None,
        "account_name": ws.account_name if ws else None,
        "connected_at": ws.connected_at if ws else None,
        "last_heartbeat_at": ws.last_heartbeat_at if ws else None,
        "last_error": ws.last_error if ws else None,
        "last_error_at": ws.last_error_at if ws else None,
        # Reported by the worker (the API process deliberately has no Telegram credentials).
        # None = the worker has never reported yet, so it is unknown.
        "telegram_configured": None if ws is None else ws.status != WorkerStatus.NOT_CONFIGURED,
    }


async def response_distribution(
    db: AsyncSession, since: datetime, until: datetime | None = None
) -> list[dict[str, Any]]:
    cond = [SlaIncident.resolution.in_(REPLY_RESOLUTIONS), SlaIncident.resolved_at >= since]
    if until is not None:
        cond.append(SlaIncident.resolved_at < until)
    cols = []
    for label, lo, hi in BUCKETS:
        pred = SlaIncident.response_seconds >= lo
        if hi is not None:
            pred = sa.and_(pred, SlaIncident.response_seconds < hi)
        cols.append(sa.func.count().filter(pred).label(label))
    row = (await db.execute(sa.select(*cols).where(*cond))).one()
    return [{"label": label, "count": int(row[i] or 0)} for i, (label, _, _) in enumerate(BUCKETS)]


async def dashboard_summary(db: AsyncSession, settings: Settings) -> dict[str, Any]:
    now = utcnow()
    today = today_start_utc()
    window = now - timedelta(days=30)

    total_customers = await db.scalar(
        sa.select(sa.func.count()).select_from(Customer).where(Customer.is_excluded.is_(False))
    )
    new_today = await db.scalar(sa.select(sa.func.count()).select_from(Customer).where(Customer.first_seen_at >= today))
    open_q = sa.select(sa.func.count()).select_from(SlaIncident).where(SlaIncident.status == IncidentStatus.OPEN)
    unanswered = await db.scalar(open_q)
    overdue = await db.scalar(open_q.where(SlaIncident.deadline_at <= now))
    avg_30d = await db.scalar(
        sa.select(sa.func.avg(SlaIncident.response_seconds)).where(
            SlaIncident.resolution.in_(REPLY_RESOLUTIONS), SlaIncident.resolved_at >= window
        )
    )
    avg_today = await db.scalar(
        sa.select(sa.func.avg(SlaIncident.response_seconds)).where(
            SlaIncident.resolution.in_(REPLY_RESOLUTIONS), SlaIncident.resolved_at >= today
        )
    )
    breached_30d = await db.scalar(
        sa.select(sa.func.count()).select_from(SlaIncident).where(SlaIncident.breached_at >= window)
    )
    resolved_alerts_30d = await db.scalar(
        sa.select(sa.func.count())
        .select_from(SlaIncident)
        .where(
            SlaIncident.alert_status == AlertStatus.SENT,
            SlaIncident.status != IncidentStatus.OPEN,
            SlaIncident.resolved_at >= window,
        )
    )
    alerts_sent_today = await db.scalar(
        sa.select(sa.func.count()).select_from(SlaIncident).where(SlaIncident.alerted_at >= today)
    )
    auto_total = await db.scalar(
        sa.select(sa.func.count()).select_from(Customer).where(Customer.welcome_status == WelcomeStatus.SENT)
    )
    auto_today = await db.scalar(
        sa.select(sa.func.count()).select_from(Customer).where(Customer.welcome_sent_at >= today)
    )
    resolved_30d = await db.scalar(
        sa.select(sa.func.count())
        .select_from(SlaIncident)
        .where(SlaIncident.resolution.in_(REPLY_RESOLUTIONS), SlaIncident.resolved_at >= window)
    )
    within_sla_30d = await db.scalar(
        sa.select(sa.func.count())
        .select_from(SlaIncident)
        .where(
            SlaIncident.resolution.in_(REPLY_RESOLUTIONS),
            SlaIncident.resolved_at >= window,
            SlaIncident.breached_at.is_(None),
        )
    )

    upcoming = (
        await db.execute(
            sa.select(
                AnnouncementCampaign.id,
                AnnouncementCampaign.title,
                AnnouncementCampaign.next_run_at,
                AnnouncementCampaign.dry_run,
            )
            .where(
                AnnouncementCampaign.status == CampaignStatus.SCHEDULED, AnnouncementCampaign.next_run_at.is_not(None)
            )
            .order_by(AnnouncementCampaign.next_run_at)
            .limit(5)
        )
    ).all()
    failures = (
        await db.execute(
            sa.select(
                AnnouncementDelivery.id,
                AnnouncementDelivery.error_message,
                AnnouncementDelivery.updated_at,
                TelegramGroup.title,
                AnnouncementCampaign.title,
            )
            .join(TelegramGroup, TelegramGroup.id == AnnouncementDelivery.group_id)
            .join(AnnouncementRun, AnnouncementRun.id == AnnouncementDelivery.run_id)
            .join(AnnouncementCampaign, AnnouncementCampaign.id == AnnouncementRun.campaign_id)
            .where(AnnouncementDelivery.status.in_([DeliveryStatus.FAILED, DeliveryStatus.UNKNOWN]))
            .order_by(AnnouncementDelivery.updated_at.desc())
            .limit(5)
        )
    ).all()
    welcome_failures = (
        await db.execute(
            sa.select(Customer.id, Customer.first_name, Customer.username, Customer.welcome_error, Customer.updated_at)
            .where(Customer.welcome_status.in_([WelcomeStatus.FAILED, WelcomeStatus.UNKNOWN]))
            .order_by(Customer.updated_at.desc())
            .limit(5)
        )
    ).all()
    alert_failures = await db.scalar(
        sa.select(sa.func.count())
        .select_from(SlaIncident)
        .where(SlaIncident.alert_status == AlertStatus.FAILED, SlaIncident.updated_at >= window)
    )

    errors = [
        {"kind": "announcement", "title": f"{camp} → {grp}", "message": msg, "at": at}
        for _id, msg, at, grp, camp in failures
    ] + [
        {
            "kind": "welcome",
            "title": f"Avto-javob: {fn or ('@' + un if un else '#' + str(cid))}",
            "message": err,
            "at": at,
        }
        for cid, fn, un, err, at in welcome_failures
    ]
    errors.sort(key=lambda e: e["at"] or now, reverse=True)

    return {
        "metrics": {
            "total_customers": int(total_customers or 0),
            "new_customers_today": int(new_today or 0),
            "unanswered": int(unanswered or 0),
            "overdue": int(overdue or 0),
            "avg_response_seconds_30d": round(float(avg_30d), 1) if avg_30d is not None else None,
            "avg_response_seconds_today": round(float(avg_today), 1) if avg_today is not None else None,
            "breached_30d": int(breached_30d or 0),
            "resolved_alerts_30d": int(resolved_alerts_30d or 0),
            "alerts_sent_today": int(alerts_sent_today or 0),
            "alert_failures_30d": int(alert_failures or 0),
            "auto_responses_total": int(auto_total or 0),
            "auto_responses_today": int(auto_today or 0),
            "resolved_30d": int(resolved_30d or 0),
            "within_sla_30d": int(within_sla_30d or 0),
        },
        "distribution_30d": await response_distribution(db, window),
        "telegram": await worker_status(db, settings),
        "upcoming_announcements": [
            {"campaign_id": i, "title": t, "next_run_at": n, "dry_run": d} for i, t, n, d in upcoming
        ],
        "recent_errors": errors[:8],
    }


async def report(db: AsyncSession, date_from: date, date_to: date) -> dict[str, Any]:
    start = local_day_start(date_from)
    end = local_day_start(date_to + timedelta(days=1))
    tz = "Asia/Tashkent"

    def day(col: Any) -> Any:
        return sa.func.date(sa.func.timezone(tz, col))

    async def series(stmt: Any) -> dict[date, Any]:
        return {d: v for d, v in (await db.execute(stmt)).all()}

    new_customers = await series(
        sa.select(day(Customer.first_seen_at), sa.func.count())
        .where(Customer.first_seen_at >= start, Customer.first_seen_at < end)
        .group_by(sa.literal_column("1"))
    )
    incidents = await series(
        sa.select(day(SlaIncident.started_at), sa.func.count())
        .where(SlaIncident.started_at >= start, SlaIncident.started_at < end)
        .group_by(sa.literal_column("1"))
    )
    breaches = await series(
        sa.select(day(SlaIncident.started_at), sa.func.count())
        .where(SlaIncident.started_at >= start, SlaIncident.started_at < end, SlaIncident.breached_at.is_not(None))
        .group_by(sa.literal_column("1"))
    )
    avg_resp = await series(
        sa.select(day(SlaIncident.resolved_at), sa.func.avg(SlaIncident.response_seconds))
        .where(
            SlaIncident.resolved_at >= start,
            SlaIncident.resolved_at < end,
            SlaIncident.resolution.in_(REPLY_RESOLUTIONS),
        )
        .group_by(sa.literal_column("1"))
    )
    welcomes = await series(
        sa.select(day(Customer.welcome_sent_at), sa.func.count())
        .where(Customer.welcome_sent_at >= start, Customer.welcome_sent_at < end)
        .group_by(sa.literal_column("1"))
    )
    sent = await series(
        sa.select(day(AnnouncementDelivery.sent_at), sa.func.count())
        .where(
            AnnouncementDelivery.sent_at >= start,
            AnnouncementDelivery.sent_at < end,
            AnnouncementDelivery.status == DeliveryStatus.SENT,
        )
        .group_by(sa.literal_column("1"))
    )
    failed = await series(
        sa.select(day(AnnouncementDelivery.updated_at), sa.func.count())
        .where(
            AnnouncementDelivery.updated_at >= start,
            AnnouncementDelivery.updated_at < end,
            AnnouncementDelivery.status.in_([DeliveryStatus.FAILED, DeliveryStatus.UNKNOWN]),
        )
        .group_by(sa.literal_column("1"))
    )
    days = []
    d = date_from
    while d <= date_to:
        days.append(
            {
                "date": d.isoformat(),
                "new_customers": int(new_customers.get(d, 0)),
                "incidents": int(incidents.get(d, 0)),
                "breaches": int(breaches.get(d, 0)),
                "avg_response_seconds": round(float(avg_resp[d]), 1) if avg_resp.get(d) is not None else None,
                "welcome_sent": int(welcomes.get(d, 0)),
                "announcements_sent": int(sent.get(d, 0)),
                "announcements_failed": int(failed.get(d, 0)),
            }
        )
        d += timedelta(days=1)

    totals_row = (
        await db.execute(
            sa.select(
                sa.func.count(),
                sa.func.count().filter(SlaIncident.breached_at.is_not(None)),
                sa.func.count().filter(SlaIncident.resolution.in_(REPLY_RESOLUTIONS)),
                sa.func.avg(SlaIncident.response_seconds).filter(SlaIncident.resolution.in_(REPLY_RESOLUTIONS)),
                sa.func.percentile_cont(0.5)
                .within_group(SlaIncident.response_seconds)
                .filter(SlaIncident.resolution.in_(REPLY_RESOLUTIONS)),
                sa.func.max(SlaIncident.response_seconds).filter(SlaIncident.resolution.in_(REPLY_RESOLUTIONS)),
            ).where(SlaIncident.started_at >= start, SlaIncident.started_at < end)
        )
    ).one()
    run_stats = dict(
        (
            await db.execute(
                sa.select(AnnouncementRun.status, sa.func.count())
                .where(AnnouncementRun.scheduled_for >= start, AnnouncementRun.scheduled_for < end)
                .group_by(AnnouncementRun.status)
            )
        ).all()
    )
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "days": days,
        "totals": {
            "incidents": int(totals_row[0] or 0),
            "breaches": int(totals_row[1] or 0),
            "answered": int(totals_row[2] or 0),
            "avg_response_seconds": round(float(totals_row[3]), 1) if totals_row[3] is not None else None,
            "median_response_seconds": round(float(totals_row[4]), 1) if totals_row[4] is not None else None,
            "max_response_seconds": int(totals_row[5]) if totals_row[5] is not None else None,
            "new_customers": sum(x["new_customers"] for x in days),
            "welcome_sent": sum(x["welcome_sent"] for x in days),
            "announcements_sent": sum(x["announcements_sent"] for x in days),
            "announcements_failed": sum(x["announcements_failed"] for x in days),
            "runs": {str(getattr(k, "value", k)): int(v) for k, v in run_stats.items()},
        },
        "distribution": await response_distribution(db, start, end),
    }


def ensure_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = utcnow().astimezone(DISPLAY_TZ).date()
    date_to = date_to or today
    date_from = date_from or (date_to - timedelta(days=13))
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days > 92:
        date_from = date_to - timedelta(days=92)
    return date_from, date_to
