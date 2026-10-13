"""Structured logging with secret redaction.

All log events pass through `redact_processor`, which masks values of sensitive keys
(api_hash, password, code, session, token, ...) and known secret patterns in strings.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "api_hash",
    "telegram_api_hash",
    "password",
    "new_password",
    "current_password",
    "password_hash",
    "code",
    "phone_code",
    "session",
    "session_string",
    "token",
    "csrf_token",
    "bot_token",
    "alert_bot_token",
    "authorization",
    "cookie",
    "set-cookie",
    "database_url",
}

# Bot tokens look like 123456:ABC-DEF...; hex API hashes are 32 hex chars.
_PATTERNS = [
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\b[a-f0-9]{32}\b"),
    re.compile(r"(postgres(?:ql)?(?:\+asyncpg)?://[^:/\s]+:)[^@\s]+@"),
]


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        out = value
        for pat in _PATTERNS:
            out = pat.sub(lambda m: f"{m.group(1)}***@", out) if pat.groups else pat.sub("***", out)
        return out
    if isinstance(value, dict):
        return {k: ("***" if str(k).lower() in SENSITIVE_KEYS else redact_value(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(redact_value(v) for v in value)
    return value


def redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***"
        else:
            event_dict[key] = redact_value(event_dict[key])
    return event_dict


class _StdlibRedactFilter(logging.Filter):
    """Redacts secrets from third-party (stdlib) log records such as Telethon's."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.msg, str):
            return True  # structlog event dicts are already redacted by redact_processor
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        record.msg = redact_value(msg)
        record.args = ()
        return True


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        redact_processor,
    ]
    renderer: Any = structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer(colors=False)
    structlog.configure(
        processors=[
            *shared,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(_StdlibRedactFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Telethon is chatty at INFO; keep warnings and above.
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
