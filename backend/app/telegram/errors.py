"""Map Telethon / network exceptions to `SendError` with Uzbek messages."""

from __future__ import annotations

import asyncio

from telethon import errors as te

from app.telegram.types import SendError, SendErrorKind

_GROUP_PERMISSION = (
    te.ChatWriteForbiddenError,
    te.ChannelPrivateError,
    te.UserBannedInChannelError,
    te.ChatAdminRequiredError,
    te.ChatRestrictedError,
    te.ChatSendPlainForbiddenError,
    te.ChatGuestSendForbiddenError,
)

_UNAUTHORIZED = (
    te.AuthKeyUnregisteredError,
    te.AuthKeyDuplicatedError,
    te.UserDeactivatedBanError,
    te.UserDeactivatedError,
    te.SessionRevokedError,
    te.SessionExpiredError,
    te.AuthKeyError,
    te.UnauthorizedError,
)

_MESSAGES: dict[type[BaseException], str] = {
    te.ChatWriteForbiddenError: "Akkauntga bu guruhga yozish taqiqlangan",
    te.ChannelPrivateError: "Guruh yopiq yoki akkaunt guruhdan chiqarilgan",
    te.UserBannedInChannelError: "Akkaunt bu guruhda bloklangan",
    te.ChatAdminRequiredError: "Bu amal uchun administrator huquqi kerak",
    te.ChatRestrictedError: "Guruh cheklangan",
    te.ChatSendPlainForbiddenError: "Guruhda matnli xabar yuborish taqiqlangan",
    te.ChatGuestSendForbiddenError: "Yozish uchun guruhga a'zo bo'lish kerak",
    te.UserIsBlockedError: "Mijoz akkauntni bloklagan",
    te.InputUserDeactivatedError: "Mijozning akkaunti o'chirilgan",
    te.UserPrivacyRestrictedError: "Foydalanuvchi maxfiylik sozlamalari ruxsat bermaydi",
    te.PeerIdInvalidError: "Chat identifikatori noto'g'ri",
    te.ChatIdInvalidError: "Guruh identifikatori noto'g'ri",
    te.ChannelInvalidError: "Guruh identifikatori noto'g'ri",
    te.UsernameNotOccupiedError: "Bunday username mavjud emas",
    te.UsernameInvalidError: "Username noto'g'ri",
    te.MessageTooLongError: "Xabar Telegram ruxsat etganidan uzun",
    te.MessageEmptyError: "Xabar bo'sh",
}


def classify_exception(exc: BaseException) -> SendError:
    if isinstance(exc, SendError):
        return exc
    code = type(exc).__name__
    if isinstance(exc, te.FloodWaitError):
        return SendError(
            SendErrorKind.FLOOD,
            "flood_wait",
            f"Telegram {exc.seconds} soniya kutishni talab qildi",
            retry_after=int(exc.seconds),
        )
    if isinstance(exc, te.SlowModeWaitError):
        return SendError(
            SendErrorKind.TRANSIENT,
            "slow_mode",
            f"Guruhda sekin rejim: {exc.seconds} soniyadan keyin",
            retry_after=int(exc.seconds),
        )
    if isinstance(exc, te.PeerFloodError):
        return SendError(
            SendErrorKind.FLOOD, "peer_flood", "Telegram akkauntni vaqtincha chekladi (spam cheklovi)", retry_after=3600
        )
    if isinstance(exc, _UNAUTHORIZED):
        return SendError(SendErrorKind.UNAUTHORIZED, code, "Telegram sessiyasi yaroqsiz - qayta kirish kerak")
    if isinstance(exc, _GROUP_PERMISSION):
        return SendError(
            SendErrorKind.PERMANENT, code, _MESSAGES.get(type(exc), str(exc))[:300], extra={"group_permission": True}
        )
    if isinstance(exc, te.MessageTooLongError | te.MessageEmptyError):
        return SendError(SendErrorKind.INVALID_CONTENT, code, _MESSAGES[type(exc)])
    for cls, msg in _MESSAGES.items():
        if isinstance(exc, cls):
            return SendError(SendErrorKind.PERMANENT, code, msg)
    if isinstance(exc, te.ServerError | te.TimedOutError | asyncio.TimeoutError | ConnectionError | OSError):
        return SendError(SendErrorKind.TRANSIENT, code, "Tarmoq yoki Telegram server xatosi")
    if isinstance(exc, te.ForbiddenError):
        return SendError(SendErrorKind.PERMANENT, code, f"Ruxsat yo'q: {exc}"[:300], extra={"group_permission": True})
    if isinstance(exc, te.BadRequestError):
        return SendError(SendErrorKind.PERMANENT, code, f"Telegram so'rovni rad etdi: {exc}"[:300])
    if isinstance(exc, ValueError):
        # Telethon raises ValueError when it cannot resolve a peer from its entity cache.
        return SendError(SendErrorKind.PERMANENT, "peer_unknown", "Chat topilmadi (akkaunt bu chatni ko'rmaydi)")
    if isinstance(exc, te.RPCError):
        return SendError(SendErrorKind.TRANSIENT, code, f"Telegram xatosi: {exc}"[:300])
    return SendError(SendErrorKind.TRANSIENT, code, "Kutilmagan xato")
