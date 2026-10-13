"""Administrator alert delivery.

Two channels are supported:
  * "userbot" - the connected account sends the alert to a chat (a management group,
    a channel, "@username" or "me" = Saved Messages). Note: the account owner gets no push
    notification for messages they send themselves; use a group with other admins or the bot channel.
  * "bot" - a separate Telegram bot (ALERT_BOT_TOKEN) sends the alert through the HTTPS Bot API,
    which produces normal push notifications for the admins who started the bot.
"""

from __future__ import annotations

import html
from typing import Protocol

import httpx

from app.core.logging import get_logger
from app.core.timeutil import format_local, humanize_seconds_uz, utcnow
from app.services.app_settings import RuntimeSettings
from app.services.sender import TelegramSender
from app.telegram.types import SendError, SendErrorKind

log = get_logger(__name__)


class AlertTransport(Protocol):
    async def send(self, settings: RuntimeSettings, html_text: str) -> None: ...


def parse_userbot_target(target: str) -> int | str:
    target = target.strip()
    if target.lower() in {"me", "self", "saved"}:
        return "me"
    if target.lstrip("-").isdigit():
        return int(target)
    if target.startswith("https://t.me/"):
        target = target.removeprefix("https://t.me/")
    return target if target.startswith("@") else f"@{target}"


class UserbotAlertTransport:
    def __init__(self, sender: TelegramSender) -> None:
        self._sender = sender

    async def send(self, settings: RuntimeSettings, html_text: str) -> None:
        if not settings.alert_chat:
            raise SendError(SendErrorKind.PERMANENT, "alert_chat_missing", "Ogohlantirish chati sozlanmagan")
        await self._sender.send(parse_userbot_target(settings.alert_chat), html_text, link_preview=False)


class BotApiAlertTransport:
    API = "https://api.telegram.org"

    def __init__(self, token: str | None, client: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=15)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send(self, settings: RuntimeSettings, html_text: str) -> None:
        if not self._token:
            raise SendError(SendErrorKind.PERMANENT, "bot_token_missing", "ALERT_BOT_TOKEN sozlanmagan")
        chats = [c.strip() for c in settings.alert_chat.split(",") if c.strip()]
        if not chats:
            raise SendError(SendErrorKind.PERMANENT, "alert_chat_missing", "Ogohlantirish chati sozlanmagan")
        delivered = 0
        last_error: SendError | None = None
        for chat_id in chats:
            try:
                await self._send_one(chat_id, html_text)
                delivered += 1
            except SendError as exc:
                last_error = exc
                log.warning("bot_alert_failed", chat_id=chat_id, code=exc.code)
        if delivered == 0 and last_error is not None:
            raise last_error

    async def _send_one(self, chat_id: str, html_text: str) -> None:
        url = f"{self.API}/bot{self._token}/sendMessage"
        try:
            resp = await self._client.post(
                url,
                json={
                    "chat_id": int(chat_id),
                    "text": html_text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
        except httpx.HTTPError as exc:
            raise SendError(SendErrorKind.TRANSIENT, "bot_network", f"Bot API tarmoq xatosi: {type(exc).__name__}")
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code == 200 and data.get("ok"):
            return
        desc = str(data.get("description") or resp.status_code)[:300]
        if resp.status_code == 429:
            retry = int((data.get("parameters") or {}).get("retry_after") or 30)
            raise SendError(SendErrorKind.FLOOD, "bot_flood", desc, retry_after=retry)
        if resp.status_code >= 500:
            raise SendError(SendErrorKind.TRANSIENT, "bot_server_error", desc)
        if resp.status_code == 401:
            raise SendError(SendErrorKind.PERMANENT, "bot_unauthorized", "Bot tokeni noto'g'ri")
        raise SendError(SendErrorKind.PERMANENT, "bot_rejected", desc)


class AlertNotifier:
    def __init__(self, userbot: AlertTransport, bot: AlertTransport) -> None:
        self._userbot = userbot
        self._bot = bot

    async def send(self, settings: RuntimeSettings, html_text: str) -> None:
        transport = self._bot if settings.alert_channel == "bot" else self._userbot
        await transport.send(settings, html_text)


def build_sla_alert(
    *,
    customer_name: str,
    username: str | None,
    telegram_user_id: int,
    started_at,
    message_count: int,
    preview: str | None,
    include_preview: bool,
) -> str:
    esc = html.escape
    elapsed = (utcnow() - started_at).total_seconds()
    lines = [
        "⚠️ <b>Javobsiz murojaat</b>",
        "",
        f'Mijoz: <a href="tg://user?id={telegram_user_id}">{esc(customer_name)}</a>',
        f"Username: @{esc(username)}" if username else "Username: —",
        f"Telegram ID: <code>{telegram_user_id}</code>",
        f"Murojaat vaqti: {format_local(started_at)}",
        f"Javobsiz: <b>{humanize_seconds_uz(elapsed)}</b>",
        f"Javobsiz xabarlar: {message_count}",
        "Holat: operator javobi kutilmoqda",
    ]
    if include_preview and preview:
        lines += ["", f"Xabar: <i>{esc(preview)}</i>"]
    if username:
        lines += ["", f"Suhbatni ochish: https://t.me/{esc(username)}"]
    return "\n".join(lines)


def build_test_alert() -> str:
    return (
        "✅ <b>Sinov ogohlantirishi</b>\n\nEduCenter CRM ogohlantirishlari shu chatga yetib keladi.\n"
        f"Vaqt: {format_local(utcnow())}"
    )
