"""Request/response models for the admin API."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.enums import (
    AlertStatus,
    CampaignStatus,
    CommandStatus,
    CommandType,
    DeliveryStatus,
    GroupKind,
    GroupSource,
    IncidentStatus,
    MessageDirection,
    MessageSource,
    OutboxStatus,
    Resolution,
    Role,
    RunStatus,
    ScheduleType,
    SenderType,
    WelcomeStatus,
    WorkerStatus,
)
from app.schemas.common import ORM

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,64}$")


# ----------------------------------------------------------------------------- auth / admins
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class AdminOut(ORM):
    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class MeOut(BaseModel):
    admin: AdminOut
    permissions: list[str]
    csrf_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class AdminCreate(BaseModel):
    username: str
    full_name: str = Field(default="", max_length=128)
    role: Role
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError("Login 3-64 belgi: lotin harflari, raqam, '_', '.', '-'")
        return v


class AdminUpdate(BaseModel):
    username: str | None = None
    full_name: str | None = Field(default=None, max_length=128)
    role: Role | None = None
    is_active: bool | None = None

    @field_validator("username")
    @classmethod
    def _username(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError("Login 3-64 belgi: lotin harflari, raqam, '_', '.', '-'")
        return v


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=256)


# ----------------------------------------------------------------------------- customers / chats
class CustomerOut(ORM):
    id: int
    telegram_user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    display_name: str
    first_seen_at: datetime
    is_excluded: bool
    welcome_status: WelcomeStatus
    welcome_sent_at: datetime | None
    welcome_error: str | None


class ConversationOut(BaseModel):
    id: int
    customer: CustomerOut
    assigned_admin_id: int | None
    assigned_admin_name: str | None
    last_message_at: datetime | None
    last_incoming_at: datetime | None
    last_outgoing_at: datetime | None
    last_human_reply_at: datetime | None
    last_message_preview: str | None
    last_message_direction: MessageDirection | None
    sla_state: Literal["ok", "waiting", "overdue"]
    open_incident_id: int | None
    waiting_since: datetime | None
    deadline_at: datetime | None


class MessageOut(ORM):
    id: int
    telegram_message_id: int
    direction: MessageDirection
    sender_type: SenderType
    source: MessageSource
    counts_as_reply: bool
    is_forwarded: bool
    has_media: bool
    text_preview: str | None
    sent_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None
    sent_by_admin_id: int | None


class IncidentOut(BaseModel):
    id: int
    conversation_id: int
    customer: CustomerOut
    status: IncidentStatus
    started_at: datetime
    last_customer_message_at: datetime
    customer_message_count: int
    deadline_at: datetime
    breached_at: datetime | None
    alert_status: AlertStatus
    alerted_at: datetime | None
    alert_error: str | None
    resolved_at: datetime | None
    resolution: Resolution | None
    response_seconds: int | None
    first_message_preview: str | None
    overdue: bool


class CustomerDetailOut(BaseModel):
    customer: CustomerOut
    conversation: ConversationOut | None
    incidents: list[IncidentOut]
    message_count: int


class ReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class OutgoingOut(ORM):
    id: int
    conversation_id: int
    text: str
    status: OutboxStatus
    attempts: int
    error: str | None
    created_at: datetime
    sent_at: datetime | None
    requested_by_admin_id: int | None


class AssignRequest(BaseModel):
    admin_id: int | None


class ExcludeRequest(BaseModel):
    excluded: bool


# ----------------------------------------------------------------------------- formatting
class PreviewRequest(BaseModel):
    text: str = Field(max_length=20000)


class PreviewOut(BaseModel):
    text: str
    entities: list[dict[str, Any]]
    length: int
    limit: int
    errors: list[str]


class AutoReplyOut(BaseModel):
    welcome_enabled: bool
    welcome_text: str
    welcome_delay_seconds: int
    welcome_only_new_chats: bool
    welcome_link_preview: bool
    welcome_excluded_user_ids: list[int]
    stats: dict[str, int]


class AutoReplyUpdate(BaseModel):
    welcome_enabled: bool
    welcome_text: str = Field(max_length=20000)
    welcome_delay_seconds: int = Field(ge=0, le=3600)
    welcome_only_new_chats: bool
    welcome_link_preview: bool
    welcome_excluded_user_ids: list[int] = Field(default_factory=list, max_length=5000)


# ----------------------------------------------------------------------------- groups / campaigns
class GroupOut(ORM):
    id: int
    telegram_id: int
    title: str
    username: str | None
    kind: GroupKind
    source: GroupSource
    participants_count: int | None
    is_member: bool
    can_send: bool
    permission_note: str | None
    is_enabled: bool
    last_synced_at: datetime | None


class GroupUpdate(BaseModel):
    is_enabled: bool


class ManualGroupRequest(BaseModel):
    identifier: str = Field(min_length=2, max_length=200)


class CommandOut(ORM):
    id: int
    command: CommandType
    status: CommandStatus
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class TargetIn(BaseModel):
    group_id: int
    custom_text: str | None = Field(default=None, max_length=20000)


class CampaignIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    default_text: str = Field(max_length=20000)
    schedule_type: ScheduleType
    run_at: datetime | None = None  # ONCE (aware datetime; null = as soon as activated)
    time_of_day: str | None = None  # DAILY / WEEKLY, "HH:MM" in Asia/Tashkent
    weekdays: list[int] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    dry_run: bool = False
    targets: list[TargetIn] = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Sarlavha kiritilishi shart")
        return v

    @field_validator("time_of_day")
    @classmethod
    def _tod(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("Vaqt HH:MM formatida bo'lishi kerak")
        return v

    @field_validator("weekdays")
    @classmethod
    def _wd(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("Hafta kunlari 0 (dushanba) dan 6 (yakshanba) gacha")
        return sorted(set(v))

    @model_validator(mode="after")
    def _schedule(self) -> CampaignIn:
        if self.schedule_type == ScheduleType.ONCE:
            if self.run_at is not None and self.run_at.tzinfo is None:
                raise ValueError("Vaqt mintaqasi ko'rsatilishi kerak")
        else:
            if not self.time_of_day:
                raise ValueError("Takroriy e'lon uchun vaqt kiritilishi shart")
            if self.schedule_type == ScheduleType.WEEKLY and not self.weekdays:
                raise ValueError("Haftalik e'lon uchun kamida bitta kun tanlang")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas")
        ids = [t.group_id for t in self.targets]
        if len(ids) != len(set(ids)):
            raise ValueError("Bitta guruh ikki marta tanlangan")
        return self


class TargetOut(BaseModel):
    group_id: int
    group_title: str
    group_can_send: bool
    group_enabled: bool
    custom_text: str | None


class CampaignOut(BaseModel):
    id: int
    title: str
    default_text: str
    status: CampaignStatus
    schedule_type: ScheduleType
    run_at: datetime | None
    time_of_day: str | None
    weekdays: list[int]
    start_date: date | None
    end_date: date | None
    dry_run: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    targets: list[TargetOut]
    last_run_status: RunStatus | None = None


class ConfirmRequest(BaseModel):
    confirm: bool = False


class DeliveryOut(BaseModel):
    id: int
    run_id: int
    campaign_id: int
    campaign_title: str
    group_id: int
    group_title: str
    status: DeliveryStatus
    attempts: int
    error_code: str | None
    error_message: str | None
    sent_at: datetime | None
    scheduled_for: datetime
    created_at: datetime
    text: str


class RunOut(BaseModel):
    id: int
    scheduled_for: datetime
    status: RunStatus
    is_manual: bool
    started_at: datetime | None
    finished_at: datetime | None
    counts: dict[str, int]


# ----------------------------------------------------------------------------- telegram / system
class WorkerStatusOut(BaseModel):
    status: WorkerStatus | Literal["unknown", "offline"]
    status_detail: str | None
    worker_alive: bool
    account_user_id: int | None
    account_username: str | None
    account_name: str | None
    connected_at: datetime | None
    last_heartbeat_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    telegram_configured: bool | None


class ConnectionEventOut(ORM):
    id: int
    event: str
    detail: str | None
    created_at: datetime


class AuditOut(ORM):
    id: int
    actor_admin_id: int | None
    actor_username: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict[str, Any]
    ip: str | None
    created_at: datetime
