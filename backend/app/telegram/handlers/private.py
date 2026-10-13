"""Telethon event handlers for private chats. They only normalize events and delegate to
InboxService; all business rules live in the services layer."""

from __future__ import annotations

from collections.abc import Callable

from telethon import TelegramClient, events
from telethon.tl import types

from app.core.logging import get_logger
from app.services.inbox import InboxService
from app.telegram.gateway import normalize_message

log = get_logger(__name__)


def register_private_handlers(
    client: TelegramClient, inbox: InboxService, on_activity: Callable[[], None] | None = None
) -> list[tuple[Callable, events.common.EventBuilder]]:
    async def on_new(event: events.NewMessage.Event) -> None:
        try:
            chat = await event.get_chat()
            if not isinstance(chat, types.User):
                return
            result = await inbox.handle(normalize_message(event.message, chat))
            log.debug("private_message_processed", outcome=result.outcome, reason=result.reason)
            if on_activity:
                on_activity()
        except Exception:  # noqa: BLE001 - a bad event must never kill the update loop
            log.exception("private_message_handler_failed", message_id=getattr(event.message, "id", None))

    async def on_edit(event: events.MessageEdited.Event) -> None:
        try:
            chat = await event.get_chat()
            if isinstance(chat, types.User):
                await inbox.mark_edited(normalize_message(event.message, chat))
        except Exception:  # noqa: BLE001
            log.exception("edit_handler_failed")

    async def on_delete(event: events.MessageDeleted.Event) -> None:
        # chat_id is set only for channel/supergroup deletions; private-chat deletions carry
        # bare message ids (unique per account), which is all we can match on.
        if event.chat_id is not None:
            return
        try:
            await inbox.mark_deleted(list(event.deleted_ids or []))
        except Exception:  # noqa: BLE001
            log.exception("delete_handler_failed")

    handlers: list[tuple[Callable, events.common.EventBuilder]] = [
        (on_new, events.NewMessage(func=lambda e: e.is_private)),
        (on_edit, events.MessageEdited(func=lambda e: e.is_private)),
        (on_delete, events.MessageDeleted()),
    ]
    for cb, builder in handlers:
        client.add_event_handler(cb, builder)
    return handlers
