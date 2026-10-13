"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-12 14:26:31.034585
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "super_admin", "admin", "operator", name="role", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admins")),
        sa.UniqueConstraint("username", name=op.f("uq_admins_username")),
    )
    op.create_table(
        "connection_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connection_events")),
    )
    op.create_index(op.f("ix_connection_events_created_at"), "connection_events", ["created_at"], unique=False)
    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_excluded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "welcome_status",
            sa.Enum(
                "not_applicable",
                "pending",
                "sending",
                "sent",
                "failed",
                "existing",
                "unknown",
                name="welcome_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("welcome_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("welcome_trigger_message_id", sa.BigInteger(), nullable=True),
        sa.Column("welcome_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("welcome_message_id", sa.BigInteger(), nullable=True),
        sa.Column("welcome_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("welcome_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("telegram_user_id", name=op.f("uq_customers_telegram_user_id")),
    )
    op.create_index("ix_customers_first_seen", "customers", ["first_seen_at"], unique=False)
    op.create_index(op.f("ix_customers_username"), "customers", ["username"], unique=False)
    op.create_index("ix_customers_welcome_due", "customers", ["welcome_status", "welcome_due_at"], unique=False)
    op.create_table(
        "rate_limit_hits",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_limit_hits")),
    )
    op.create_index(op.f("ix_rate_limit_hits_created_at"), "rate_limit_hits", ["created_at"], unique=False)
    op.create_index("ix_rate_limit_hits_key_created", "rate_limit_hits", ["key", "created_at"], unique=False)
    op.create_table(
        "telegram_groups",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "group",
                "supergroup",
                "channel",
                name="group_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum("discovered", "manual", name="group_source", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("participants_count", sa.Integer(), nullable=True),
        sa.Column("is_member", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("can_send", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("permission_note", sa.String(length=255), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_groups")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_telegram_groups_telegram_id")),
    )
    op.create_table(
        "worker_state",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "starting",
                "connected",
                "disconnected",
                "unauthorized",
                "not_configured",
                "standby",
                "error",
                "stopped",
                name="worker_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("status_detail", sa.String(length=500), nullable=True),
        sa.Column("account_user_id", sa.BigInteger(), nullable=True),
        sa.Column("account_username", sa.String(length=64), nullable=True),
        sa.Column("account_name", sa.String(length=255), nullable=True),
        sa.Column("hostname", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_worker_state_singleton")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_state")),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admins.id"], name=op.f("fk_admin_sessions_admin_id_admins"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_sessions")),
    )
    op.create_index(op.f("ix_admin_sessions_admin_id"), "admin_sessions", ["admin_id"], unique=False)
    op.create_index(op.f("ix_admin_sessions_expires_at"), "admin_sessions", ["expires_at"], unique=False)
    op.create_table(
        "announcement_campaigns",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("default_text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "scheduled",
                "paused",
                "completed",
                "cancelled",
                name="campaign_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "schedule_type",
            sa.Enum(
                "once", "daily", "weekly", name="schedule_type", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_of_day", sa.String(length=5), nullable=True),
        sa.Column("weekdays", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"],
            ["admins.id"],
            name=op.f("fk_announcement_campaigns_created_by_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcement_campaigns")),
    )
    op.create_index("ix_campaigns_status", "announcement_campaigns", ["status"], unique=False)
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column(
            "data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by_admin_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_app_settings_singleton")),
        sa.ForeignKeyConstraint(
            ["updated_by_admin_id"],
            ["admins.id"],
            name=op.f("fk_app_settings_updated_by_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_settings")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("actor_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_username", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_admin_id"], ["admins.id"], name=op.f("fk_audit_events_actor_admin_id_admins"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_action_created", "audit_events", ["action", "created_at"], unique=False)
    op.create_index(op.f("ix_audit_events_actor_admin_id"), "audit_events", ["actor_admin_id"], unique=False)
    op.create_index(op.f("ix_audit_events_created_at"), "audit_events", ["created_at"], unique=False)
    op.create_table(
        "conversations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("assigned_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_incoming_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outgoing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_human_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(length=300), nullable=True),
        sa.Column(
            "last_message_direction",
            sa.Enum("in", "out", name="message_direction", native_enum=False, create_constraint=True, length=32),
            nullable=True,
        ),
        sa.Column("last_telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_admin_id"],
            ["admins.id"],
            name=op.f("fk_conversations_assigned_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_conversations_customer_id_customers"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("customer_id", name=op.f("uq_conversations_customer_id")),
    )
    op.create_index(op.f("ix_conversations_assigned_admin_id"), "conversations", ["assigned_admin_id"], unique=False)
    op.create_index("ix_conversations_last_message", "conversations", ["last_message_at"], unique=False)
    op.create_table(
        "worker_commands",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "command",
            sa.Enum(
                "sync_groups",
                "resolve_group",
                "reconnect",
                "test_alert",
                name="command_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "done",
                "failed",
                name="command_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("requested_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["requested_by_admin_id"],
            ["admins.id"],
            name=op.f("fk_worker_commands_requested_by_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_commands")),
    )
    op.create_index("ix_worker_commands_status", "worker_commands", ["status", "created_at"], unique=False)
    op.create_table(
        "announcement_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "partial",
                "failed",
                "missed",
                "cancelled",
                name="run_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("is_manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["announcement_campaigns.id"],
            name=op.f("fk_announcement_runs_campaign_id_announcement_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcement_runs")),
        sa.UniqueConstraint("campaign_id", "scheduled_for", name="uq_announcement_runs_occurrence"),
    )
    op.create_index("ix_announcement_runs_due", "announcement_runs", ["status", "scheduled_for"], unique=False)
    op.create_table(
        "campaign_targets",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("custom_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["announcement_campaigns.id"],
            name=op.f("fk_campaign_targets_campaign_id_announcement_campaigns"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["telegram_groups.id"],
            name=op.f("fk_campaign_targets_group_id_telegram_groups"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaign_targets")),
        sa.UniqueConstraint("campaign_id", "group_id", name="uq_campaign_targets_pair"),
    )
    op.create_index(op.f("ix_campaign_targets_group_id"), "campaign_targets", ["group_id"], unique=False)
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("in", "out", name="message_direction", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column(
            "sender_type",
            sa.Enum(
                "customer",
                "operator",
                "automation",
                name="sender_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "telegram",
                "welcome",
                "panel",
                name="message_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("counts_as_reply", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_forwarded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("has_media", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("text_preview", sa.String(length=1000), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_by_admin_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sent_by_admin_id"], ["admins.id"], name=op.f("fk_messages_sent_by_admin_id_admins"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("conversation_id", "telegram_message_id", name="uq_messages_conv_tgid"),
    )
    op.create_index("ix_messages_conv_sent", "messages", ["conversation_id", "sent_at"], unique=False)
    op.create_index("ix_messages_sent_at", "messages", ["sent_at"], unique=False)
    op.create_index("ix_messages_tg_id", "messages", ["telegram_message_id"], unique=False)
    op.create_table(
        "outgoing_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("requested_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "sending",
                "sent",
                "failed",
                "unknown",
                name="outbox_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_outgoing_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_admin_id"],
            ["admins.id"],
            name=op.f("fk_outgoing_messages_requested_by_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outgoing_messages")),
    )
    op.create_index("ix_outgoing_due", "outgoing_messages", ["status", "next_attempt_at"], unique=False)
    op.create_index(
        op.f("ix_outgoing_messages_conversation_id"), "outgoing_messages", ["conversation_id"], unique=False
    )
    op.create_table(
        "sla_incidents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "resolved",
                "dismissed",
                name="incident_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("last_customer_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_message_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("breached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "alert_status",
            sa.Enum(
                "none",
                "pending",
                "sending",
                "sent",
                "failed",
                "skipped",
                name="alert_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("alert_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("alert_next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_error", sa.String(length=500), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolution",
            sa.Enum(
                "human_reply",
                "panel_reply",
                "dismissed",
                name="resolution",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("resolved_by_telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("response_seconds", sa.Integer(), nullable=True),
        sa.Column("dismissed_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_sla_incidents_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dismissed_by_admin_id"],
            ["admins.id"],
            name=op.f("fk_sla_incidents_dismissed_by_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_incidents")),
    )
    op.create_index("ix_sla_incidents_due", "sla_incidents", ["status", "alert_status", "deadline_at"], unique=False)
    op.create_index("ix_sla_incidents_started", "sla_incidents", ["started_at"], unique=False)
    op.create_index(
        "uq_sla_incidents_one_open",
        "sla_incidents",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "announcement_deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sending",
                "sent",
                "failed",
                "skipped",
                "dry_run",
                "unknown",
                "cancelled",
                name="delivery_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["telegram_groups.id"],
            name=op.f("fk_announcement_deliveries_group_id_telegram_groups"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["announcement_runs.id"],
            name=op.f("fk_announcement_deliveries_run_id_announcement_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcement_deliveries")),
        sa.UniqueConstraint("run_id", "group_id", name="uq_announcement_deliveries_pair"),
    )
    op.create_index(
        "ix_announcement_deliveries_due", "announcement_deliveries", ["status", "next_attempt_at"], unique=False
    )
    op.create_index(op.f("ix_announcement_deliveries_group_id"), "announcement_deliveries", ["group_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_announcement_deliveries_group_id"), table_name="announcement_deliveries")
    op.drop_index("ix_announcement_deliveries_due", table_name="announcement_deliveries")
    op.drop_table("announcement_deliveries")
    op.drop_index("uq_sla_incidents_one_open", table_name="sla_incidents", postgresql_where=sa.text("status = 'open'"))
    op.drop_index("ix_sla_incidents_started", table_name="sla_incidents")
    op.drop_index("ix_sla_incidents_due", table_name="sla_incidents")
    op.drop_table("sla_incidents")
    op.drop_index(op.f("ix_outgoing_messages_conversation_id"), table_name="outgoing_messages")
    op.drop_index("ix_outgoing_due", table_name="outgoing_messages")
    op.drop_table("outgoing_messages")
    op.drop_index("ix_messages_tg_id", table_name="messages")
    op.drop_index("ix_messages_sent_at", table_name="messages")
    op.drop_index("ix_messages_conv_sent", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_campaign_targets_group_id"), table_name="campaign_targets")
    op.drop_table("campaign_targets")
    op.drop_index("ix_announcement_runs_due", table_name="announcement_runs")
    op.drop_table("announcement_runs")
    op.drop_index("ix_worker_commands_status", table_name="worker_commands")
    op.drop_table("worker_commands")
    op.drop_index("ix_conversations_last_message", table_name="conversations")
    op.drop_index(op.f("ix_conversations_assigned_admin_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_admin_id"), table_name="audit_events")
    op.drop_index("ix_audit_events_action_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("app_settings")
    op.drop_index("ix_campaigns_status", table_name="announcement_campaigns")
    op.drop_table("announcement_campaigns")
    op.drop_index(op.f("ix_admin_sessions_expires_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_admin_id"), table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_table("worker_state")
    op.drop_table("telegram_groups")
    op.drop_index("ix_rate_limit_hits_key_created", table_name="rate_limit_hits")
    op.drop_index(op.f("ix_rate_limit_hits_created_at"), table_name="rate_limit_hits")
    op.drop_table("rate_limit_hits")
    op.drop_index("ix_customers_welcome_due", table_name="customers")
    op.drop_index(op.f("ix_customers_username"), table_name="customers")
    op.drop_index("ix_customers_first_seen", table_name="customers")
    op.drop_table("customers")
    op.drop_index(op.f("ix_connection_events_created_at"), table_name="connection_events")
    op.drop_table("connection_events")
    op.drop_table("admins")
