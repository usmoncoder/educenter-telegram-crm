"""Validation and preview of Telegram HTML-formatted messages.

Uses Telethon's own HTML parser (the same one used when sending) so the preview, the
length check and the real message are consistent. Telethon silently drops unknown or
unclosed tags and accepts any link scheme, so an extra strict pass reports those problems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from telethon.extensions import html as tl_html

TELEGRAM_TEXT_LIMIT = 4096
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "s", "del", "code", "pre", "a", "blockquote"}
ALLOWED_LINK_SCHEMES = ("https://", "http://", "tg://", "mailto:")

_ENTITY_NAMES = {
    "MessageEntityBold": "bold",
    "MessageEntityItalic": "italic",
    "MessageEntityUnderline": "underline",
    "MessageEntityStrike": "strike",
    "MessageEntityCode": "code",
    "MessageEntityPre": "pre",
    "MessageEntityTextUrl": "link",
    "MessageEntityBlockquote": "blockquote",
}


@dataclass
class FormattedMessage:
    text: str
    entities: list[dict[str, Any]] = field(default_factory=list)
    length: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class _StrictChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"<{tag}> tegi qo'llab-quvvatlanmaydi")
            return
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if not href.lower().startswith(ALLOWED_LINK_SCHEMES):
                self.errors.append(f"Havola noto'g'ri: \"{href[:60]}\" (https:// bilan boshlanishi kerak)")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_TAGS:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> tegi noto'g'ri joyda yopilgan")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()

    def close(self) -> None:
        super().close()
        for tag in self.stack:
            self.errors.append(f"<{tag}> tegi yopilmagan")


def utf16_len(text: str) -> int:
    """Telegram measures message length in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def parse_message(html_text: str, *, limit: int = TELEGRAM_TEXT_LIMIT) -> FormattedMessage:
    errors: list[str] = []
    checker = _StrictChecker()
    try:
        checker.feed(html_text)
        checker.close()
    except Exception:  # noqa: BLE001 - HTMLParser can raise on pathological input
        errors.append("Matn formatlashini o'qib bo'lmadi")
    errors.extend(dict.fromkeys(checker.errors))  # de-duplicate, keep order

    text, entities = tl_html.parse(html_text)
    length = utf16_len(text)
    if not text.strip():
        errors.append("Xabar matni bo'sh bo'lmasligi kerak")
    if length > limit:
        errors.append(f"Xabar juda uzun: {length} belgi (ruxsat etilgan: {limit})")

    out_entities = []
    for ent in entities:
        kind = _ENTITY_NAMES.get(type(ent).__name__)
        if not kind:
            continue
        item: dict[str, Any] = {"type": kind, "offset": ent.offset, "length": ent.length}
        if kind == "link":
            item["url"] = ent.url
        out_entities.append(item)
    return FormattedMessage(text=text, entities=out_entities, length=length, errors=errors)


def plain_text(html_text: str) -> str:
    return tl_html.parse(html_text)[0]
