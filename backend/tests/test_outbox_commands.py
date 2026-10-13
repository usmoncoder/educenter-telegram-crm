"""Panel replies (outbox) and worker commands."""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa

from app.core.timeutil import utcnow
from app.db.enums import CommandStatus, CommandType, IncidentStatus, OutboxStatus, Resolution, SenderType
from app.db.models import Conversation, Message, OutgoingMessage, SlaIncident, TelegramGroup, WorkerCommand
from app.db.session import transaction
from app.services.commands import CommandExecutor
from app.services.inbox import InboxService
from app.services.notifications import AlertNotifier, UserbotAlertTransport
from app.services.outbox import OutboxDispatcher
from app.telegram.types import GroupInfo, SendError, SendErrorKind
from tests.conftest import CUSTOMER, set_runtime, tg_msg


async def queue_reply(factory, text="Salom! Kurs narxi 500 000 so'm.") -> int:
    async with transaction(factory) as s:
        conv_id = await s.scalar(sa.select(Conversation.id))
        o = OutgoingMessage(conversation_id=conv_id, text=text, status=OutboxStatus.QUEUED)
        s.add(o)
        await s.flush()
        return o.id


async def test_panel_reply_is_sent_recorded_and_resolves_incident(factory, settings_cache, sender, gateway):
    inbox = InboxService(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=2))
    oid = await queue_reply(factory)
    outbox = OutboxDispatcher(factory, sender, settings_cache)
    assert await outbox.run_once() == 1
    assert await outbox.run_once() == 0
    assert gateway.sent == [(CUSTOMER.id, "Salom! Kurs narxi 500 000 so'm.")]
    async with factory() as s:
        out = await s.get(OutgoingMessage, oid)
        inc = await s.scalar(sa.select(SlaIncident))
        msg = await s.scalar(sa.select(Message).where(Message.telegram_message_id == out.telegram_message_id))
    assert out.status == OutboxStatus.SENT and out.sent_at is not None
    assert inc.status == IncidentStatus.RESOLVED and inc.resolution == Resolution.PANEL_REPLY
    assert msg.sender_type == SenderType.OPERATOR and msg.counts_as_reply
    # The Telegram update for the same message arrives later: recognized as already recorded.
    res = await inbox.handle(tg_msg(out.telegram_message_id, outgoing=True, text="x"))
    assert res.outcome == "duplicate"


async def test_operator_reply_text_stored_only_when_enabled(factory, settings_cache, sender, gateway):
    # Default: operator reply text is not stored (data minimization).
    inbox = InboxService(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=2))
    oid = await queue_reply(factory, text="Narxi 500 000 so'm, ertaga keling.")
    await OutboxDispatcher(factory, sender, settings_cache).run_once()
    async with factory() as s:
        out = await s.get(OutgoingMessage, oid)
        msg = await s.scalar(sa.select(Message).where(Message.telegram_message_id == out.telegram_message_id))
    assert msg.text_preview is None

    # Super Admin enables storing operator text: the next reply keeps a truncated preview.
    await set_runtime(factory, store_operator_text=True)
    await inbox.handle(tg_msg(11, minutes_ago=1))
    oid2 = await queue_reply(factory, text="Albatta, 14:00 da kutamiz.")
    await OutboxDispatcher(factory, sender, settings_cache).run_once()
    async with factory() as s:
        out2 = await s.get(OutgoingMessage, oid2)
        msg2 = await s.scalar(sa.select(Message).where(Message.telegram_message_id == out2.telegram_message_id))
    assert msg2.text_preview == "Albatta, 14:00 da kutamiz."


async def test_panel_reply_failure_is_reported_not_faked(factory, settings_cache, sender, gateway):
    inbox = InboxService(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=2))
    oid = await queue_reply(factory)
    gateway.errors.append(SendError(SendErrorKind.PERMANENT, "UserIsBlockedError", "Mijoz akkauntni bloklagan"))
    await OutboxDispatcher(factory, sender, settings_cache).run_once()
    async with factory() as s:
        out = await s.get(OutgoingMessage, oid)
        inc = await s.scalar(sa.select(SlaIncident))
    assert out.status == OutboxStatus.FAILED and out.error == "Mijoz akkauntni bloklagan"
    assert inc.status == IncidentStatus.OPEN


async def executor(factory, settings_cache, sender, gateway, reconnect_calls: list | None = None) -> CommandExecutor:
    async def reconnect() -> None:
        if reconnect_calls is not None:
            reconnect_calls.append(1)

    notifier = AlertNotifier(UserbotAlertTransport(sender), UserbotAlertTransport(sender))
    return CommandExecutor(factory, gateway, settings_cache, notifier, reconnect)


async def add_command(factory, command, payload=None, created_at=None) -> int:
    async with transaction(factory) as s:
        c = WorkerCommand(command=command, payload=payload or {})
        if created_at:
            c.created_at = created_at
        s.add(c)
        await s.flush()
        return c.id


async def get_command(factory, cid) -> WorkerCommand:
    async with factory() as s:
        return await s.get(WorkerCommand, cid)


async def test_sync_groups_upserts_and_marks_departed_groups(factory, settings_cache, sender, gateway):
    gateway.groups = [
        GroupInfo(-1001, "IELTS guruhi", "supergroup", "ielts_uz", 120, True, True, None),
        GroupInfo(-1002, "Kanal", "channel", None, 10, True, False, "Kanalga faqat adminlar yoza oladi"),
    ]
    ex = await executor(factory, settings_cache, sender, gateway)
    cid = await add_command(factory, CommandType.SYNC_GROUPS)
    await ex.run_once()
    cmd = await get_command(factory, cid)
    assert cmd.status == CommandStatus.DONE and cmd.result == {"found": 2, "stale": 0}
    async with factory() as s:
        groups = {g.telegram_id: g for g in (await s.scalars(sa.select(TelegramGroup))).all()}
    assert groups[-1001].can_send and not groups[-1001].is_enabled  # explicit opt-in required
    assert not groups[-1002].can_send
    # The account leaves a group -> next sync marks it as non-member.
    gateway.groups = gateway.groups[:1]
    await add_command(factory, CommandType.SYNC_GROUPS)
    await ex.run_once()
    async with factory() as s:
        g = await s.scalar(sa.select(TelegramGroup).where(TelegramGroup.telegram_id == -1002))
    assert g.is_member is False


async def test_resolve_group_success_and_failure(factory, settings_cache, sender, gateway):
    gateway.resolvable["@ok_group"] = GroupInfo(-1009, "Ok", "supergroup", "ok_group", 5, True, True, None)
    ex = await executor(factory, settings_cache, sender, gateway)
    ok = await add_command(factory, CommandType.RESOLVE_GROUP, {"identifier": "@ok_group"})
    bad = await add_command(factory, CommandType.RESOLVE_GROUP, {"identifier": "@nope"})
    await ex.run_once()
    assert (await get_command(factory, ok)).status == CommandStatus.DONE
    failed = await get_command(factory, bad)
    assert failed.status == CommandStatus.FAILED and failed.error == "Guruh topilmadi"


async def test_test_alert_reconnect_and_expiry(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="me")
    calls: list = []
    ex = await executor(factory, settings_cache, sender, gateway, calls)
    t = await add_command(factory, CommandType.TEST_ALERT)
    r = await add_command(factory, CommandType.RECONNECT)
    old = await add_command(factory, CommandType.SYNC_GROUPS, created_at=utcnow() - timedelta(hours=1))
    await ex.run_once()
    assert (await get_command(factory, t)).status == CommandStatus.DONE
    assert gateway.sent and gateway.sent[0][0] == "me"
    assert (await get_command(factory, r)).status == CommandStatus.DONE and calls == [1]
    assert (await get_command(factory, old)).status == CommandStatus.FAILED
