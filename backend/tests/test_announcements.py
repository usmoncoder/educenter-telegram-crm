"""Group announcements: persistence, idempotency, concurrency, retries, misfires, state machine."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import sqlalchemy as sa

from app.core.timeutil import utcnow
from app.db.enums import CampaignStatus, DeliveryStatus, GroupKind, GroupSource, RunStatus, ScheduleType
from app.db.models import (
    Admin,
    AnnouncementCampaign,
    AnnouncementDelivery,
    AnnouncementRun,
    CampaignTarget,
    TelegramGroup,
)
from app.db.session import transaction
from app.schemas.api import CampaignIn, TargetIn
from app.services import campaigns as svc
from app.services.announcements import AnnouncementScheduler
from app.services.sender import TelegramSender
from app.telegram.types import SendError, SendErrorKind
from tests.conftest import set_runtime


async def seed_groups(factory, n: int = 2, **overrides) -> list[int]:
    ids = []
    async with transaction(factory) as s:
        for i in range(n):
            g = TelegramGroup(
                telegram_id=-1000000000000 - i,
                title=f"Guruh {i + 1}",
                kind=GroupKind.SUPERGROUP,
                source=GroupSource.DISCOVERED,
                is_member=True,
                can_send=True,
                is_enabled=True,
                **overrides,
            )
            s.add(g)
            await s.flush()
            ids.append(g.id)
    return ids


async def make_campaign(
    factory,
    group_ids,
    *,
    schedule_type=ScheduleType.ONCE,
    run_at=None,
    dry_run=False,
    activate=True,
    texts=None,
    **extra,
) -> int:
    async with transaction(factory) as s:
        admin = Admin(username="a", full_name="A", password_hash="x", role="super_admin")
        s.add(admin)
        await s.flush()
        body = CampaignIn(
            title="Yangi guruhlar",
            default_text="<b>Qabul ochiq!</b>",
            schedule_type=schedule_type,
            run_at=run_at,
            dry_run=dry_run,
            targets=[TargetIn(group_id=g, custom_text=(texts or {}).get(g)) for g in group_ids],
            **extra,
        )
        c = await svc.create_campaign(s, body, admin)
        if activate:
            await svc.activate(s, c.id, confirm=True)
        return c.id


async def run_all(scheduler: AnnouncementScheduler, rounds: int = 3) -> None:
    for _ in range(rounds):
        await scheduler.tick()


async def deliveries(factory) -> list[AnnouncementDelivery]:
    async with factory() as s:
        return list((await s.scalars(sa.select(AnnouncementDelivery).order_by(AnnouncementDelivery.id))).all())


async def campaign(factory, cid) -> AnnouncementCampaign:
    async with factory() as s:
        return await s.get(AnnouncementCampaign, cid)


def scheduler(factory, settings_cache, sender) -> AnnouncementScheduler:
    return AnnouncementScheduler(factory, settings_cache, sender)


async def test_once_campaign_sends_each_group_once_and_completes(factory, settings_cache, sender, gateway):
    await set_runtime(factory, announcement_min_interval_seconds=1)
    g1, g2 = await seed_groups(factory, 2)
    cid = await make_campaign(factory, [g1, g2], texts={g2: "<i>Maxsus matn</i>"})
    sch = scheduler(factory, settings_cache, sender)
    await sch.tick()
    sch._last_group_send = 0  # skip the inter-group pause in tests
    await sch.tick()
    await sch.tick()
    assert sorted(t for _, t in gateway.sent) == ["<b>Qabul ochiq!</b>", "<i>Maxsus matn</i>"]
    assert {d.status for d in await deliveries(factory)} == {DeliveryStatus.SENT}
    assert (await campaign(factory, cid)).status == CampaignStatus.COMPLETED
    # More ticks / a restarted scheduler never resend.
    await run_all(scheduler(factory, settings_cache, TelegramSender(gateway, min_interval_seconds=0)))
    assert len(gateway.sent) == 2


async def test_concurrent_schedulers_do_not_double_send(factory, settings_cache, gateway):
    await set_runtime(factory, announcement_min_interval_seconds=1)
    ids = await seed_groups(factory, 6)
    await make_campaign(factory, ids)
    a = scheduler(factory, settings_cache, TelegramSender(gateway, min_interval_seconds=0))
    b = scheduler(factory, settings_cache, TelegramSender(gateway, min_interval_seconds=0))
    for _ in range(12):
        a._last_group_send = b._last_group_send = 0
        await asyncio.gather(a.tick(), b.tick())
    peers = [p for p, _ in gateway.sent]
    assert len(peers) == 6 and len(set(peers)) == 6


async def test_dry_run_sends_nothing(factory, settings_cache, sender, gateway):
    g1, g2 = await seed_groups(factory, 2)
    cid = await make_campaign(factory, [g1, g2], dry_run=True)
    await run_all(scheduler(factory, settings_cache, sender))
    assert gateway.sent == []
    assert {d.status for d in await deliveries(factory)} == {DeliveryStatus.DRY_RUN}
    async with factory() as s:
        run = await s.scalar(sa.select(AnnouncementRun))
    assert run.status == RunStatus.COMPLETED
    assert (await campaign(factory, cid)).status == CampaignStatus.COMPLETED


async def test_permanent_failure_in_one_group_does_not_block_others(factory, settings_cache, sender, gateway):
    await set_runtime(factory, announcement_min_interval_seconds=1)
    g1, g2 = await seed_groups(factory, 2)
    gateway.errors_by_peer[-1000000000000] = SendError(
        SendErrorKind.PERMANENT, "ChatWriteForbiddenError", "Yozish taqiqlangan", extra={"group_permission": True}
    )
    await make_campaign(factory, [g1, g2])
    sch = scheduler(factory, settings_cache, sender)
    for _ in range(4):
        sch._last_group_send = 0
        await sch.tick()
    by_group = {d.group_id: d for d in await deliveries(factory)}
    assert by_group[g1].status == DeliveryStatus.FAILED and by_group[g1].attempts == 1
    assert by_group[g2].status == DeliveryStatus.SENT
    async with factory() as s:
        g = await s.get(TelegramGroup, g1)
        run = await s.scalar(sa.select(AnnouncementRun))
    assert g.can_send is False and g.permission_note == "Yozish taqiqlangan"
    assert run.status == RunStatus.PARTIAL


async def test_flood_wait_postpones_without_consuming_attempts(factory, settings_cache, sender, gateway):
    (g1,) = await seed_groups(factory, 1)
    await make_campaign(factory, [g1])
    gateway.errors.append(SendError(SendErrorKind.FLOOD, "flood_wait", "wait", retry_after=300))
    await scheduler(factory, settings_cache, sender).tick()
    [d] = await deliveries(factory)
    assert d.status == DeliveryStatus.PENDING and d.attempts == 0
    assert d.next_attempt_at > utcnow() + timedelta(seconds=250)
    assert sender.flood_remaining() > 0  # global pause honoured


async def test_transient_errors_retry_with_backoff_then_fail(factory, settings_cache, sender, gateway):
    await set_runtime(factory, announcement_max_attempts=2)
    (g1,) = await seed_groups(factory, 1)
    await make_campaign(factory, [g1])
    sch = scheduler(factory, settings_cache, sender)
    for attempt in (1, 2):
        gateway.errors.append(SendError(SendErrorKind.TRANSIENT, "TimedOutError", "timeout"))
        sch._last_group_send = 0
        await sch.tick()
        [d] = await deliveries(factory)
        assert d.attempts == attempt
        async with factory() as s, s.begin():
            await s.execute(sa.update(AnnouncementDelivery).values(next_attempt_at=sa.func.now()))
    [d] = await deliveries(factory)
    assert d.status == DeliveryStatus.FAILED
    assert gateway.sent == []


async def test_missed_run_beyond_grace_is_not_sent(factory, settings_cache, sender, gateway):
    await set_runtime(factory, misfire_grace_minutes=10)
    (g1,) = await seed_groups(factory, 1)
    cid = await make_campaign(factory, [g1], run_at=utcnow() + timedelta(minutes=1))
    async with factory() as s, s.begin():  # the worker was down: occurrence now 2 hours old
        await s.execute(sa.update(AnnouncementCampaign).values(run_at=utcnow() - timedelta(hours=2)))
    await run_all(scheduler(factory, settings_cache, sender))
    assert gateway.sent == []
    async with factory() as s:
        run = await s.scalar(sa.select(AnnouncementRun))
    assert run.status == RunStatus.MISSED
    assert (await campaign(factory, cid)).status == CampaignStatus.COMPLETED


async def test_future_once_campaign_waits(factory, settings_cache, sender, gateway):
    (g1,) = await seed_groups(factory, 1)
    cid = await make_campaign(factory, [g1], run_at=utcnow() + timedelta(hours=3))
    await run_all(scheduler(factory, settings_cache, sender))
    assert gateway.sent == []
    c = await campaign(factory, cid)
    assert c.status == CampaignStatus.SCHEDULED and c.next_run_at > utcnow()


async def test_pause_stops_and_resume_continues(factory, settings_cache, sender, gateway):
    await set_runtime(factory, announcement_min_interval_seconds=600)
    g1, g2 = await seed_groups(factory, 2)
    cid = await make_campaign(factory, [g1, g2])
    sch = scheduler(factory, settings_cache, sender)
    await sch.tick()  # first group sent; second waits for the inter-group interval
    assert len(gateway.sent) == 1
    async with transaction(factory) as s:
        await svc.pause(s, cid)
    sch._last_group_send = 0
    await sch.tick()
    assert len(gateway.sent) == 1  # paused: nothing more goes out
    async with transaction(factory) as s:
        await svc.resume(s, cid)
    sch._last_group_send = 0
    await sch.tick()
    assert len(gateway.sent) == 2


async def test_cancel_cancels_pending_deliveries(factory, settings_cache, sender, gateway):
    await set_runtime(factory, announcement_min_interval_seconds=600)
    g1, g2 = await seed_groups(factory, 2)
    cid = await make_campaign(factory, [g1, g2])
    sch = scheduler(factory, settings_cache, sender)
    await sch.tick()
    async with transaction(factory) as s:
        await svc.cancel(s, cid)
    sch._last_group_send = 0
    await run_all(sch)
    assert len(gateway.sent) == 1
    statuses = sorted(d.status for d in await deliveries(factory))
    assert statuses == [DeliveryStatus.CANCELLED, DeliveryStatus.SENT]
    async with factory() as s:
        run = await s.scalar(sa.select(AnnouncementRun))
    assert run.status == RunStatus.PARTIAL and run.finished_at is not None


async def test_daily_campaign_materializes_next_occurrence(factory, settings_cache, sender, gateway):
    (g1,) = await seed_groups(factory, 1)
    cid = await make_campaign(factory, [g1], schedule_type=ScheduleType.DAILY, time_of_day="09:00")
    sch = scheduler(factory, settings_cache, sender)
    await sch.tick()
    async with factory() as s:
        runs = (await s.scalars(sa.select(AnnouncementRun))).all()
    assert len(runs) == 1 and runs[0].status == RunStatus.PENDING
    assert runs[0].scheduled_for > utcnow()
    # Materializing again never duplicates the occurrence (unique constraint + pending check).
    await sch.tick()
    async with factory() as s:
        assert await s.scalar(sa.select(sa.func.count()).select_from(AnnouncementRun)) == 1
    # Manual "send now" on a recurring campaign creates an extra immediate run.
    async with transaction(factory) as s:
        await svc.send_now(s, cid, confirm=True)
    await run_all(sch)
    assert len(gateway.sent) == 1


async def test_disabled_or_forbidden_groups_are_skipped(factory, settings_cache, sender, gateway):
    g1, g2 = await seed_groups(factory, 2)
    await make_campaign(factory, [g1, g2])
    async with factory() as s, s.begin():
        await s.execute(sa.update(TelegramGroup).where(TelegramGroup.id == g1).values(is_enabled=False))
        await s.execute(sa.update(TelegramGroup).where(TelegramGroup.id == g2).values(can_send=False))
    await run_all(scheduler(factory, settings_cache, sender))
    assert gateway.sent == []
    assert {d.status for d in await deliveries(factory)} == {DeliveryStatus.SKIPPED}
    async with factory() as s:
        run = await s.scalar(sa.select(AnnouncementRun))
    assert run.status == RunStatus.FAILED


async def test_interrupted_delivery_becomes_unknown_and_is_not_resent(factory, settings_cache, sender, gateway):
    (g1,) = await seed_groups(factory, 1)
    await make_campaign(factory, [g1])
    sch = scheduler(factory, settings_cache, sender)
    await sch.materialize(timedelta(hours=1))
    await sch.start_due_runs(timedelta(hours=1))
    async with factory() as s, s.begin():
        await s.execute(sa.update(AnnouncementDelivery).values(status=DeliveryStatus.SENDING))
    assert await sch.recover_interrupted() == 1
    await run_all(sch)
    assert gateway.sent == []
    [d] = await deliveries(factory)
    assert d.status == DeliveryStatus.UNKNOWN


async def test_multi_group_activation_requires_confirmation(factory):
    from app.core.errors import ValidationAppError

    g1, g2 = await seed_groups(factory, 2)
    cid = await make_campaign(factory, [g1, g2], activate=False)
    async with transaction(factory) as s:
        try:
            await svc.activate(s, cid, confirm=False)
        except ValidationAppError as exc:
            assert exc.code == "confirmation_required"
        else:
            raise AssertionError("confirmation was not required")


async def test_campaign_validation_rejects_disabled_group_and_bad_html(factory):
    from app.core.errors import ValidationAppError

    g_on, g_off = await seed_groups(factory, 2)
    async with factory() as s, s.begin():
        await s.execute(sa.update(TelegramGroup).where(TelegramGroup.id == g_off).values(is_enabled=False))
        admin = Admin(username="u", full_name="", password_hash="x", role="admin")
        s.add(admin)
    cases = [("<b>yopilmagan", g_on, "yopilmagan"), ("ok", g_off, "yoqilmagan")]
    for text, group_id, expected in cases:
        try:
            async with transaction(factory) as s:
                admin = await s.scalar(sa.select(Admin))
                body = CampaignIn(
                    title="t", default_text=text, schedule_type=ScheduleType.ONCE, targets=[TargetIn(group_id=group_id)]
                )
                await svc.create_campaign(s, body, admin)
        except ValidationAppError as exc:
            assert expected in exc.message
        else:
            raise AssertionError("invalid campaign accepted")
    async with factory() as s:
        assert await s.scalar(sa.select(sa.func.count()).select_from(CampaignTarget)) == 0
