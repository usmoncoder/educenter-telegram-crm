"""Telegram worker process.

    python -m app.workers.main

Responsibilities: own the single Telethon connection, process private-chat updates, and run
the persistent background loops (welcome messages, SLA breaches and alerts, panel replies,
announcements, worker commands, retention, heartbeat).

Concurrency control
  * A PostgreSQL session-level advisory lock guarantees that only one worker process uses the
    Telegram session at a time. A second worker waits in STANDBY and takes over if the first dies
    (the lock is released automatically when its DB connection closes).
  * Independently, every job claim uses SELECT ... FOR UPDATE SKIP LOCKED and commits a
    "sending" state before calling Telegram, so even two active workers would not double-send.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from telethon import TelegramClient

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.timeutil import utcnow
from app.db.enums import WorkerStatus
from app.db.session import SessionFactory, create_engine, create_session_factory
from app.services.announcements import AnnouncementScheduler
from app.services.app_settings import SettingsCache
from app.services.commands import CommandExecutor
from app.services.inbox import InboxService
from app.services.notifications import AlertNotifier, BotApiAlertTransport, UserbotAlertTransport
from app.services.outbox import OutboxDispatcher
from app.services.retention import run_retention
from app.services.sender import TelegramSender
from app.services.sla import SlaMonitor
from app.services.welcome import WelcomeDispatcher
from app.services.worker_state import WorkerStateStore
from app.telegram.client import build_client
from app.telegram.gateway import TelethonGateway
from app.telegram.handlers.private import register_private_handlers
from app.telegram.reconcile import reconcile_since
from app.telegram.types import SendError

log = get_logger("worker")

ADVISORY_LOCK_KEY = 0x45445543  # "EDUC"
RETENTION_INTERVAL = 3600.0
UNAUTHORIZED_RECHECK = 60.0


async def _periodic(name: str, interval: float, fn: Callable[[], Awaitable[object]], stop: asyncio.Event) -> None:
    """Run `fn` every `interval` seconds; failures are logged and never stop the loop."""
    while not stop.is_set():
        try:
            await fn()
        except Exception:  # noqa: BLE001
            log.exception("loop_iteration_failed", loop=name)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


class _ShutdownRequested(Exception):
    """Raised when SIGTERM/SIGINT arrives while a long Telegram call is in progress."""


class WorkerRunner:
    def __init__(self, settings: Settings, engine: AsyncEngine, factory: SessionFactory) -> None:
        self.settings = settings
        self.engine = engine
        self.factory = factory
        self.state = WorkerStateStore(factory)
        self.settings_cache = SettingsCache(factory)
        self.shutdown = asyncio.Event()
        self._client: TelegramClient | None = None
        self._connected_flag = False

    # ------------------------------------------------------------------ lifecycle
    async def run(self) -> None:
        await self.state.set_status(WorkerStatus.STARTING, "Worker ishga tushmoqda", started_at=utcnow())
        if not self.settings.telegram_configured:
            await self.state.set_status(
                WorkerStatus.NOT_CONFIGURED, "TELEGRAM_API_ID / TELEGRAM_API_HASH muhit o'zgaruvchilari kiritilmagan"
            )
            await _periodic("heartbeat", self.settings.worker_heartbeat_seconds, self.state.heartbeat, self.shutdown)
            return
        # Liveness heartbeat for the whole process lifetime (also while connecting or waiting
        # for authorization), so the dashboard can tell "connecting" from "worker is down".
        liveness = asyncio.create_task(
            _periodic("liveness", self.settings.worker_heartbeat_seconds, self.state.heartbeat, self.shutdown)
        )
        attempt = 0
        while not self.shutdown.is_set():
            try:
                outcome = await self._session_cycle()
                attempt = 0 if outcome == "ok" else attempt
            except _ShutdownRequested:
                break
            except Exception as exc:  # noqa: BLE001
                attempt += 1
                log.exception("worker_cycle_failed")
                await self._safe_status(WorkerStatus.ERROR, f"Ulanish xatosi: {type(exc).__name__}")
            if self.shutdown.is_set():
                break
            delay = min(300.0, 5.0 * (2 ** min(attempt, 6)))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.shutdown.wait(), timeout=delay)
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(liveness, timeout=5)
        await self._safe_status(WorkerStatus.STOPPED, "Worker to'xtatildi")

    async def _interruptible[T](self, aw: Awaitable[T]) -> T:
        """Await a (possibly very slow) Telegram call, but give up immediately on shutdown.
        Telethon retries connections for a long time; without this, `docker stop` would wait
        for the retries and then SIGKILL the worker."""
        task = asyncio.ensure_future(aw)
        stop = asyncio.create_task(self.shutdown.wait())
        try:
            await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            raise _ShutdownRequested
        return task.result()

    async def _safe_status(self, status: WorkerStatus, detail: str) -> None:
        try:
            await self.state.set_status(status, detail)
        except Exception:  # noqa: BLE001 - DB may be down
            log.exception("worker_status_update_failed", status=status)

    async def request_reconnect(self) -> None:
        if self._client is not None and self._client.is_connected():
            await self.state.event("reconnect_requested", "Administrator qayta ulanishni so'radi")
            await self._client.disconnect()

    async def _on_unauthorized(self, exc: SendError) -> None:
        await self._safe_status(WorkerStatus.UNAUTHORIZED, exc.message)
        if self._client is not None:
            await self._client.disconnect()

    async def _session_cycle(self) -> str:
        client = build_client(self.settings)
        self._client = client
        c = self._build_components(client)
        # Handlers are registered before connecting so updates replayed by catch_up are processed.
        register_private_handlers(client, c["inbox"])
        try:
            await self.state.set_status(WorkerStatus.STARTING, "Telegramga ulanmoqda…")
            await self._interruptible(client.connect())
            if not await self._interruptible(client.is_user_authorized()):
                await self.state.set_status(
                    WorkerStatus.UNAUTHORIZED,
                    "Telegram akkaunti avtorizatsiya qilinmagan. Serverda auth_cli buyrug'ini bajaring.",
                )
                await client.disconnect()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.shutdown.wait(), timeout=UNAUTHORIZED_RECHECK)
                return "unauthorized"
            return await self._serve(client, c)
        finally:
            if client.is_connected():
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), timeout=10)
            await c["bot_transport"].aclose()
            self._client = None

    def _build_components(self, client: TelegramClient) -> dict:
        gateway = TelethonGateway(client)
        sender = TelegramSender(gateway, min_interval_seconds=1.0, on_unauthorized=self._on_unauthorized)
        inbox = InboxService(self.factory, self.settings_cache, sender)
        bot_token = self.settings.alert_bot_token.get_secret_value() if self.settings.alert_bot_token else None
        bot_transport = BotApiAlertTransport(bot_token)
        notifier = AlertNotifier(UserbotAlertTransport(sender), bot_transport)
        return {
            "gateway": gateway,
            "sender": sender,
            "inbox": inbox,
            "bot_transport": bot_transport,
            "welcome": WelcomeDispatcher(self.factory, self.settings_cache, sender, gateway),
            "sla": SlaMonitor(self.factory, self.settings_cache, notifier),
            "outbox": OutboxDispatcher(self.factory, sender, self.settings_cache),
            "announcements": AnnouncementScheduler(self.factory, self.settings_cache, sender),
            "commands": CommandExecutor(self.factory, gateway, self.settings_cache, notifier, self.request_reconnect),
        }

    async def _serve(self, client: TelegramClient, c: dict) -> str:
        gateway: TelethonGateway = c["gateway"]
        inbox: InboxService = c["inbox"]
        welcome: WelcomeDispatcher = c["welcome"]
        sla: SlaMonitor = c["sla"]
        outbox: OutboxDispatcher = c["outbox"]
        announcements: AnnouncementScheduler = c["announcements"]
        commands: CommandExecutor = c["commands"]

        account = await self._interruptible(gateway.get_account())
        await self.state.set_status(
            WorkerStatus.CONNECTED,
            "Telegramga ulangan",
            account_user_id=account.user_id,
            account_username=account.username,
            account_name=account.name,
            connected_at=utcnow(),
        )
        self._connected_flag = True

        # Crash recovery: anything left "sending" is marked unknown/failed, never re-sent.
        recovered = {
            "welcome": await welcome.recover_interrupted(),
            "alerts": await sla.recover_interrupted(),
            "outbox": await outbox.recover_interrupted(),
            "deliveries": await announcements.recover_interrupted(),
        }
        if any(recovered.values()):
            log.warning("interrupted_sends_recovered", **recovered)

        prior = await self.state.get()
        await self._interruptible(
            reconcile_since(client, self.factory, inbox, prior.processed_until if prior else None)
        )
        await self.state.heartbeat(processed_until=utcnow())

        stop = asyncio.Event()

        async def tick() -> None:
            await welcome.run_once()
            await sla.mark_breaches()
            await sla.dispatch_alerts()
            await outbox.run_once()
            await announcements.tick()
            await commands.run_once()

        async def heartbeat() -> None:
            connected = client.is_connected()
            if connected != self._connected_flag:
                self._connected_flag = connected
                await self.state.set_status(
                    WorkerStatus.CONNECTED if connected else WorkerStatus.DISCONNECTED,
                    "Telegramga qayta ulandi" if connected else "Telegram bilan aloqa uzildi, qayta ulanmoqda",
                )
            # processed_until only advances while connected, so reconciliation covers any gap.
            await self.state.heartbeat(processed_until=utcnow() if connected else None)

        async def retention() -> None:
            await run_retention(self.factory, self.settings_cache)

        tasks = [
            asyncio.create_task(_periodic("tick", self.settings.worker_tick_seconds, tick, stop)),
            asyncio.create_task(_periodic("heartbeat", self.settings.worker_heartbeat_seconds, heartbeat, stop)),
            asyncio.create_task(_periodic("retention", RETENTION_INTERVAL, retention, stop)),
        ]
        disconnected = asyncio.create_task(client.run_until_disconnected())  # type: ignore[arg-type]
        shutdown = asyncio.create_task(self.shutdown.wait())
        try:
            await asyncio.wait({disconnected, shutdown}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.set()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(t, timeout=30)
            shutdown.cancel()
            if client.is_connected():
                await client.disconnect()
            with contextlib.suppress(Exception):
                await disconnected
        if not self.shutdown.is_set():
            current = await self.state.get()
            if current is None or current.status != WorkerStatus.UNAUTHORIZED:
                await self.state.set_status(WorkerStatus.DISCONNECTED, "Telegram bilan aloqa uzildi")
        return "ok"


async def _acquire_single_instance_lock(
    engine: AsyncEngine, state: WorkerStateStore, shutdown: asyncio.Event
) -> AsyncConnection | None:
    conn = await engine.connect()
    while not shutdown.is_set():
        got = await conn.scalar(sa.select(sa.func.pg_try_advisory_lock(ADVISORY_LOCK_KEY)))
        await conn.commit()
        if got:
            return conn
        log.warning("worker_standby", reason="another worker holds the Telegram session lock")
        await state.event("standby", "Boshqa worker Telegram sessiyasini ishlatmoqda")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(shutdown.wait(), timeout=30)
    await conn.close()
    return None


async def amain() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    runner = WorkerRunner(settings, engine, factory)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, runner.shutdown.set)

    lock_conn = await _acquire_single_instance_lock(engine, runner.state, runner.shutdown)
    try:
        if lock_conn is not None:
            await runner.run()
    finally:
        if lock_conn is not None:
            with contextlib.suppress(Exception):
                await lock_conn.execute(sa.select(sa.func.pg_advisory_unlock(ADVISORY_LOCK_KEY)))
                await lock_conn.close()
        await engine.dispose()
        log.info("worker_exited")


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
