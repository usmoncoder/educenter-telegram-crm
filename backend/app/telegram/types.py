"""Library-independent Telegram types.

Domain services depend only on these dataclasses and on the `TelegramGateway` protocol,
so they can be tested without Telethon or a real Telegram account.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

TELEGRAM_SERVICE_USER_ID = 777000  # official "Telegram" notifications account


@dataclass(frozen=True)
class TgUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_bot: bool = False
    is_contact: bool = False
    is_self: bool = False
    is_support: bool = False  # Telegram support / service accounts


@dataclass(frozen=True)
class TgMessage:
    """A private-chat message, normalized. `chat_user` is the other party of the chat
    (the customer), regardless of message direction."""

    message_id: int
    chat_user: TgUser
    date: datetime  # aware UTC
    outgoing: bool
    text: str = ""
    is_forwarded: bool = False
    has_media: bool = False
    is_service: bool = False  # join/pin/call/etc. service messages
    via_business_bot: bool = False  # sent by a connected Telegram Business bot (automation)


@dataclass(frozen=True)
class SentMessage:
    message_id: int
    date: datetime


@dataclass(frozen=True)
class GroupInfo:
    telegram_id: int  # marked peer id
    title: str
    kind: str  # GroupKind value
    username: str | None = None
    participants_count: int | None = None
    is_member: bool = True
    can_send: bool = False
    permission_note: str | None = None


@dataclass(frozen=True)
class AccountInfo:
    user_id: int
    username: str | None
    name: str


class SendErrorKind(StrEnum):
    FLOOD = "flood"  # must wait `retry_after` seconds; not counted as a failed attempt
    TRANSIENT = "transient"  # network/server problem; retry with backoff
    PERMANENT = "permanent"  # permissions, invalid peer, blocked... never retried
    UNAUTHORIZED = "unauthorized"  # session invalid; stop sending until re-login
    INVALID_CONTENT = "invalid_content"  # message too long / empty; never retried


@dataclass
class SendError(Exception):
    kind: SendErrorKind
    code: str
    message: str
    retry_after: int | None = None
    extra: dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.kind}:{self.code}: {self.message}"


class TelegramGateway(Protocol):
    """Operations the domain needs from Telegram."""

    async def send_html(self, peer: int | str, html_text: str, *, link_preview: bool = False) -> SentMessage: ...

    async def has_history_before(self, user_id: int, message_id: int) -> bool:
        """True if the private chat contains any message older than `message_id`."""
        ...

    async def list_groups(self) -> list[GroupInfo]: ...

    async def resolve_group(self, identifier: str) -> GroupInfo: ...

    async def get_account(self) -> AccountInfo: ...
