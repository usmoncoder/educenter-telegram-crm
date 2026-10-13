"""Centralized Telegram sending.

Every outgoing message (welcome, alerts, announcements, panel replies) goes through
`TelegramSender.send`, which:
  * serializes sends and enforces a minimum interval between them (global rate limit);
  * honours Telegram flood waits globally: after a FloodWait no send is attempted until it expires;
  * reports an unauthorized session via a callback so the worker can update its status;
  * keeps per-chat locks so that classification of our own outgoing messages cannot race
    with the Telegram update for that same message (see InboxService);
  * remembers recently sent automated message IDs as a second safety net for classification.
Delivery bookkeeping (retries, idempotency, persistence) is done by the callers, which use
database rows as the source of truth.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from app.core.logging import get_logger
from app.telegram.types import SendError, SendErrorKind, SentMessage, TelegramGateway

log = get_logger(__name__)


class TelegramSender:
    def __init__(
        self,
        gateway: TelegramGateway,
        *,
        min_interval_seconds: float = 1.0,
        on_unauthorized: Callable[[SendError], Awaitable[None]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._gateway = gateway
        self._min_interval = min_interval_seconds
        self._on_unauthorized = on_unauthorized
        self._clock = clock
        self._send_lock = asyncio.Lock()
        self._last_send = -math.inf
        self._flood_until = 0.0
        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._automated: OrderedDict[int, None] = OrderedDict()

    # ---- per-chat serialization -----------------------------------------------------------
    def chat_lock(self, user_id: int) -> asyncio.Lock:
        lock = self._chat_locks.get(user_id)
        if lock is None:
            if len(self._chat_locks) > 5000:  # prune idle locks
                for key in [k for k, v in self._chat_locks.items() if not v.locked()][:2500]:
                    del self._chat_locks[key]
            lock = self._chat_locks[user_id] = asyncio.Lock()
        return lock

    # ---- automated-message registry -------------------------------------------------------
    def remember_automated(self, message_id: int) -> None:
        self._automated[message_id] = None
        while len(self._automated) > 10000:
            self._automated.popitem(last=False)

    def is_automated(self, message_id: int) -> bool:
        return message_id in self._automated

    # ---- sending ------------------------------------------------------------------------
    def flood_remaining(self) -> int:
        return max(0, math.ceil(self._flood_until - self._clock()))

    async def send(self, peer: int | str, html_text: str, *, link_preview: bool = False) -> SentMessage:
        remaining = self.flood_remaining()
        if remaining:
            raise SendError(SendErrorKind.FLOOD, "flood_wait", "Telegram cheklovi amal qilmoqda", remaining)
        async with self._send_lock:
            wait = self._last_send + self._min_interval - self._clock()
            if wait > 0:
                await asyncio.sleep(wait)
            remaining = self.flood_remaining()
            if remaining:
                raise SendError(SendErrorKind.FLOOD, "flood_wait", "Telegram cheklovi amal qilmoqda", remaining)
            try:
                return await self._gateway.send_html(peer, html_text, link_preview=link_preview)
            except SendError as exc:
                if exc.kind == SendErrorKind.FLOOD and exc.retry_after:
                    self._flood_until = self._clock() + exc.retry_after
                    log.warning("telegram_flood_wait", seconds=exc.retry_after)
                elif exc.kind == SendErrorKind.UNAUTHORIZED and self._on_unauthorized:
                    await self._on_unauthorized(exc)
                raise
            finally:
                self._last_send = self._clock()


def backoff_seconds(attempt: int, *, base: int = 30, cap: int = 1800) -> int:
    """Exponential backoff for transient failures: 30s, 60s, 120s, ... capped at 30 min."""
    return int(min(cap, base * (2 ** max(0, attempt - 1))))
