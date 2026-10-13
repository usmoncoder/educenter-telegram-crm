from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPERATOR = "operator"


class WelcomeStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"  # feature disabled / excluded when customer first appeared
    PENDING = "pending"  # queued, waiting for optional delay
    SENDING = "sending"  # claimed by worker; Telegram call in progress
    SENT = "sent"
    FAILED = "failed"
    EXISTING = "existing"  # chat already had history before the CRM saw it -> not a new customer
    UNKNOWN = "unknown"  # worker stopped mid-send; never auto-resent to avoid duplicates


class MessageDirection(StrEnum):
    IN = "in"
    OUT = "out"


class SenderType(StrEnum):
    CUSTOMER = "customer"
    OPERATOR = "operator"  # a real human reply (Telegram app or web panel)
    AUTOMATION = "automation"  # welcome message or other automated sends


class MessageSource(StrEnum):
    TELEGRAM = "telegram"  # observed through Telegram updates
    WELCOME = "welcome"
    PANEL = "panel"


class IncidentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertStatus(StrEnum):
    NONE = "none"  # deadline not reached yet
    PENDING = "pending"  # deadline passed, alert queued
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # alerts disabled / resolved before sending


class Resolution(StrEnum):
    HUMAN_REPLY = "human_reply"
    PANEL_REPLY = "panel_reply"
    DISMISSED = "dismissed"


class GroupKind(StrEnum):
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class GroupSource(StrEnum):
    DISCOVERED = "discovered"
    MANUAL = "manual"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ScheduleType(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"  # every delivery sent (or dry-run)
    PARTIAL = "partial"  # some deliveries failed
    FAILED = "failed"  # all deliveries failed
    MISSED = "missed"  # worker was down longer than the misfire grace period
    CANCELLED = "cancelled"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"
    UNKNOWN = "unknown"  # worker crashed after starting the Telegram call; not retried (no duplicates)
    CANCELLED = "cancelled"


class OutboxStatus(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    UNKNOWN = "unknown"


class WorkerStatus(StrEnum):
    STARTING = "starting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNAUTHORIZED = "unauthorized"
    NOT_CONFIGURED = "not_configured"
    STANDBY = "standby"  # another worker holds the Telegram session lock
    ERROR = "error"
    STOPPED = "stopped"


class CommandType(StrEnum):
    SYNC_GROUPS = "sync_groups"
    RESOLVE_GROUP = "resolve_group"
    RECONNECT = "reconnect"
    TEST_ALERT = "test_alert"


class CommandStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
