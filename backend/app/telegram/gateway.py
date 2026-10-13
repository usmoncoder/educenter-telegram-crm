"""Telethon implementation of `TelegramGateway` plus message normalization helpers."""

from __future__ import annotations

import re

from telethon import TelegramClient, utils
from telethon import errors as te
from telethon.tl import types
from telethon.tl.functions.channels import GetParticipantRequest

from app.core.timeutil import ensure_utc
from app.db.enums import GroupKind
from app.telegram.errors import classify_exception
from app.telegram.types import (
    AccountInfo,
    GroupInfo,
    SendError,
    SendErrorKind,
    SentMessage,
    TgMessage,
    TgUser,
)


def user_from_entity(user: types.User) -> TgUser:
    return TgUser(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        is_bot=bool(user.bot),
        is_contact=bool(user.contact),
        is_self=bool(user.is_self),
        is_support=bool(user.support),
    )


def normalize_message(message: types.Message | types.MessageService, chat_user: types.User) -> TgMessage:
    is_service = isinstance(message, types.MessageService)
    return TgMessage(
        message_id=message.id,
        chat_user=user_from_entity(chat_user),
        date=ensure_utc(message.date),
        outgoing=bool(message.out),
        text="" if is_service else (message.message or ""),
        is_forwarded=(not is_service) and message.fwd_from is not None,
        has_media=(not is_service) and message.media is not None,
        is_service=is_service,
        via_business_bot=(not is_service) and getattr(message, "via_business_bot_id", None) is not None,
    )


def _banned(rights: types.ChatBannedRights | None) -> bool:
    return bool(rights and (rights.send_messages or rights.send_plain))


def analyze_group(entity: types.Chat | types.Channel) -> GroupInfo | None:
    """Best-effort permission analysis from the entity flags Telegram returns for the account."""
    peer_id = utils.get_peer_id(entity)
    if isinstance(entity, types.Chat):
        if entity.deactivated or entity.migrated_to is not None:
            return None
        member = not entity.left
        is_admin = bool(entity.creator or entity.admin_rights)
        can_send = member and (is_admin or not _banned(entity.default_banned_rights))
        note = None if can_send else ("Akkaunt guruh a'zosi emas" if not member else "Guruhda yozish cheklangan")
        return GroupInfo(
            peer_id, entity.title, GroupKind.GROUP, None, entity.participants_count, member, can_send, note
        )
    if isinstance(entity, types.Channel):
        member = not entity.left
        if entity.megagroup or entity.gigagroup:
            is_admin = bool(entity.creator or entity.admin_rights)
            if not member:
                can_send, note = False, "Akkaunt guruh a'zosi emas"
            elif _banned(entity.banned_rights):
                can_send, note = False, "Akkaunt guruhda cheklangan"
            elif not is_admin and (_banned(entity.default_banned_rights) or entity.gigagroup):
                can_send, note = False, "Guruhda faqat adminlar yoza oladi"
            else:
                can_send, note = True, ("Sekin rejim yoqilgan" if entity.slowmode_enabled else None)
            kind = GroupKind.SUPERGROUP
        else:
            rights = entity.admin_rights
            can_send = member and bool(entity.creator or (rights and rights.post_messages))
            note = None if can_send else "Kanalga faqat post huquqi bor adminlar yoza oladi"
            kind = GroupKind.CHANNEL
        return GroupInfo(
            peer_id, entity.title, kind, entity.username, entity.participants_count, member, can_send, note
        )
    return None


_TME = re.compile(r"^(?:https?://)?(?:t|telegram)\.me/(?P<rest>[^?#]+)", re.IGNORECASE)


class TelethonGateway:
    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    async def send_html(self, peer: int | str, html_text: str, *, link_preview: bool = False) -> SentMessage:
        try:
            msg = await self.client.send_message(peer, html_text, parse_mode="html", link_preview=link_preview)
        except Exception as exc:  # noqa: BLE001 - every failure becomes a classified SendError
            raise classify_exception(exc) from exc
        return SentMessage(message_id=msg.id, date=ensure_utc(msg.date))

    async def has_history_before(self, user_id: int, message_id: int) -> bool:
        try:
            older = await self.client.get_messages(user_id, limit=1, max_id=message_id)
        except Exception as exc:  # noqa: BLE001
            raise classify_exception(exc) from exc
        return len(older) > 0

    async def list_groups(self) -> list[GroupInfo]:
        out: list[GroupInfo] = []
        try:
            async for dialog in self.client.iter_dialogs(ignore_migrated=True):
                entity = dialog.entity
                if isinstance(entity, types.Chat | types.Channel):
                    info = analyze_group(entity)
                    if info is not None and info.is_member:
                        out.append(info)
        except Exception as exc:  # noqa: BLE001
            raise classify_exception(exc) from exc
        return out

    async def resolve_group(self, identifier: str) -> GroupInfo:
        ident = identifier.strip()
        m = _TME.match(ident)
        if m:
            rest = m.group("rest").strip("/")
            if rest.startswith("+") or rest.startswith("joinchat/"):
                raise SendError(
                    SendErrorKind.PERMANENT,
                    "invite_link",
                    "Taklif havolasi qabul qilinmaydi: avval akkauntni guruhga qo'shing, "
                    "so'ng guruh username yoki ID sini kiriting",
                )
            ident = rest.split("/")[0]
        target: int | str = int(ident) if ident.lstrip("-").isdigit() else ident.lstrip("@")
        try:
            entity = await self.client.get_entity(target)
        except Exception as exc:  # noqa: BLE001
            if isinstance(target, int):
                # Not in the entity cache yet: refresh dialogs once and retry.
                try:
                    await self.client.get_dialogs()
                    entity = await self.client.get_entity(target)
                except Exception as exc2:  # noqa: BLE001
                    raise classify_exception(exc2) from exc2
            else:
                raise classify_exception(exc) from exc
        if not isinstance(entity, types.Chat | types.Channel):
            raise SendError(SendErrorKind.PERMANENT, "not_a_group", "Bu identifikator guruh yoki kanalga tegishli emas")
        info = analyze_group(entity)
        if info is None:
            raise SendError(SendErrorKind.PERMANENT, "group_unavailable", "Guruh faol emas yoki ko'chirilgan")
        if isinstance(entity, types.Channel):
            try:
                await self.client(GetParticipantRequest(entity, types.InputPeerSelf()))
            except te.UserNotParticipantError:
                raise SendError(
                    SendErrorKind.PERMANENT, "not_member", "Akkaunt bu guruh a'zosi emas - avval guruhga qo'shiling"
                )
            except Exception as exc:  # noqa: BLE001
                raise classify_exception(exc) from exc
        if not info.is_member:
            raise SendError(SendErrorKind.PERMANENT, "not_member", "Akkaunt bu guruh a'zosi emas")
        return info

    async def get_account(self) -> AccountInfo:
        me = await self.client.get_me()
        name = " ".join(p for p in [me.first_name, me.last_name] if p) or (me.username or str(me.id))
        return AccountInfo(user_id=me.id, username=me.username, name=name)
