"""Five-minute SLA: breach detection, single alert per incident, retries, restart safety."""

from __future__ import annotations

import sqlalchemy as sa

from app.db.enums import AlertStatus, IncidentStatus
from app.db.models import SlaIncident
from app.services.inbox import InboxService
from app.services.notifications import AlertNotifier, UserbotAlertTransport
from app.services.sla import SlaMonitor
from app.telegram.types import SendError, SendErrorKind
from tests.conftest import set_runtime, tg_msg


class RecordingBot:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, settings, html_text: str) -> None:
        self.sent.append(html_text)


def make(factory, settings_cache, sender):
    inbox = InboxService(factory, settings_cache, sender)
    monitor = SlaMonitor(factory, settings_cache, AlertNotifier(UserbotAlertTransport(sender), RecordingBot()))
    return inbox, monitor


async def incidents(factory) -> list[SlaIncident]:
    async with factory() as s:
        return list((await s.scalars(sa.select(SlaIncident).order_by(SlaIncident.id))).all())


async def test_no_breach_before_deadline(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="me")
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=4))
    assert await monitor.mark_breaches() == 0
    assert await monitor.dispatch_alerts() == 0
    assert gateway.sent == []


async def test_breach_produces_exactly_one_alert(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="-1001234567890")
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=6, text="Narxlar qancha?"))
    await inbox.handle(tg_msg(11, minutes_ago=5.5, text="Javob bering iltimos"))
    assert await monitor.mark_breaches() == 1
    assert await monitor.mark_breaches() == 0  # transition happens once
    assert await monitor.dispatch_alerts() == 1
    assert await monitor.dispatch_alerts() == 0
    # Restarted monitor does not re-alert.
    _, monitor2 = make(factory, settings_cache, sender)
    await monitor2.mark_breaches()
    assert await monitor2.dispatch_alerts() == 0
    assert len(gateway.sent) == 1
    peer, text = gateway.sent[0]
    assert peer == -1001234567890
    assert "Javobsiz murojaat" in text and "Ali Valiyev" in text and "@ali_v" in text
    assert "Narxlar qancha?" in text and "Javobsiz xabarlar: 2" in text
    [inc] = await incidents(factory)
    assert inc.alert_status == AlertStatus.SENT and inc.breached_at == inc.deadline_at


async def test_reply_before_deadline_prevents_alert(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="me")
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=4))
    await inbox.handle(tg_msg(11, outgoing=True, text="Salom"))
    await monitor.mark_breaches()
    await monitor.dispatch_alerts()
    assert gateway.sent == []
    [inc] = await incidents(factory)
    assert inc.status == IncidentStatus.RESOLVED and inc.breached_at is None


async def test_reply_after_breach_before_alert_skips_alert(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="me")
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=7))
    await monitor.mark_breaches()  # queued (PENDING)
    await inbox.handle(tg_msg(11, outgoing=True, text="Kechirasiz, javob"))
    assert await monitor.dispatch_alerts() == 0
    [inc] = await incidents(factory)
    assert inc.status == IncidentStatus.RESOLVED
    assert inc.alert_status == AlertStatus.SKIPPED
    assert inc.breached_at is not None and inc.response_seconds >= 7 * 60 - 5


async def test_automatic_messages_do_not_stop_the_timer(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="me", welcome_enabled=True, welcome_text="Avtomatik ma'lumot")
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=6))
    await inbox.handle(tg_msg(11, outgoing=True, text="Avtomatik ma'lumot", minutes_ago=5.9))
    await monitor.mark_breaches()
    assert await monitor.dispatch_alerts() == 1


async def test_transient_alert_failure_is_retried_permanent_marks_failed(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="me")
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=6))
    await monitor.mark_breaches()
    gateway.errors.append(SendError(SendErrorKind.TRANSIENT, "TimedOutError", "timeout"))
    assert await monitor.dispatch_alerts() == 0
    [inc] = await incidents(factory)
    assert inc.alert_status == AlertStatus.PENDING and inc.alert_attempts == 1
    assert inc.alert_next_attempt_at > inc.updated_at  # backoff scheduled in the future
    # Force the retry time and fail permanently.
    async with factory() as s, s.begin():
        await s.execute(sa.update(SlaIncident).values(alert_next_attempt_at=sa.func.now()))
    gateway.errors.append(SendError(SendErrorKind.PERMANENT, "ChatWriteForbiddenError", "forbidden"))
    await monitor.dispatch_alerts()
    [inc] = await incidents(factory)
    assert inc.alert_status == AlertStatus.FAILED and inc.alert_error == "forbidden"
    assert inc.status == IncidentStatus.OPEN  # still visible as overdue on the dashboard


async def test_missing_alert_chat_fails_cleanly(factory, settings_cache, sender, gateway):
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=6))
    await monitor.mark_breaches()
    await monitor.dispatch_alerts()
    [inc] = await incidents(factory)
    assert inc.alert_status == AlertStatus.FAILED and "sozlanmagan" in inc.alert_error


async def test_alerts_disabled_records_breach_without_sending(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alerts_enabled=False)
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=6))
    await monitor.mark_breaches()
    await monitor.dispatch_alerts()
    [inc] = await incidents(factory)
    assert inc.alert_status == AlertStatus.SKIPPED and inc.breached_at is not None
    assert gateway.sent == []


async def test_bot_channel_used_when_configured(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_channel="bot", alert_chat="12345")
    bot = RecordingBot()
    inbox = InboxService(factory, settings_cache, sender)
    monitor = SlaMonitor(factory, settings_cache, AlertNotifier(UserbotAlertTransport(sender), bot))
    await inbox.handle(tg_msg(10, minutes_ago=6))
    await monitor.mark_breaches()
    await monitor.dispatch_alerts()
    assert len(bot.sent) == 1 and gateway.sent == []


async def test_timeout_change_recalculates_open_deadlines(factory, settings_cache, sender, gateway):
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=3))
    await set_runtime(factory, sla_timeout_minutes=2, alert_chat="me")
    [inc] = await incidents(factory)
    assert (inc.deadline_at - inc.started_at).total_seconds() == 120
    assert await monitor.mark_breaches() == 1


async def test_incidents_survive_restart(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="me")
    inbox, _ = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=6))
    # Worker restarts: brand-new service objects, state comes only from the database.
    from app.services.app_settings import SettingsCache
    from app.services.sender import TelegramSender

    fresh_sender = TelegramSender(gateway, min_interval_seconds=0)
    _, monitor = make(factory, SettingsCache(factory, 0), fresh_sender)
    await monitor.mark_breaches()
    assert await monitor.dispatch_alerts() == 1


async def test_interrupted_alert_is_not_duplicated(factory, settings_cache, sender, gateway):
    await set_runtime(factory, alert_chat="me")
    inbox, monitor = make(factory, settings_cache, sender)
    await inbox.handle(tg_msg(10, minutes_ago=6))
    await monitor.mark_breaches()
    async with factory() as s, s.begin():
        await s.execute(sa.update(SlaIncident).values(alert_status=AlertStatus.SENDING))
    assert await monitor.recover_interrupted() == 1
    assert await monitor.dispatch_alerts() == 0
    assert gateway.sent == []
