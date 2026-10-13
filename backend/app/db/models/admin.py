from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db.base import Base, TimestampMixin, str_enum
from app.db.enums import Role


class Admin(TimestampMixin, Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(64), unique=True)  # stored lowercase
    full_name: Mapped[str] = mapped_column(sa.String(128), default="")
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    last_login_at: Mapped[datetime | None]
    password_changed_at: Mapped[datetime | None]

    sessions: Mapped[list[AdminSession]] = relationship(back_populates="admin", cascade="all, delete-orphan")


class AdminSession(Base):
    """Server-side session. Only the SHA-256 digest of the cookie token is stored."""

    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)  # sha256(token)
    admin_id: Mapped[int] = mapped_column(sa.ForeignKey("admins.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    expires_at: Mapped[datetime] = mapped_column(index=True)
    revoked_at: Mapped[datetime | None]
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    user_agent: Mapped[str | None] = mapped_column(sa.String(256))

    admin: Mapped[Admin] = relationship(back_populates="sessions")


class RateLimitHit(Base):
    """Shared (multi-process) rate-limit counter, e.g. failed logins per username / per IP."""

    __tablename__ = "rate_limit_hits"
    __table_args__ = (sa.Index("ix_rate_limit_hits_key_created", "key", "created_at"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    key: Mapped[str] = mapped_column(sa.String(160))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now(), index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (sa.Index("ix_audit_events_action_created", "action", "created_at"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    actor_admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admins.id", ondelete="SET NULL"), index=True)
    actor_username: Mapped[str | None] = mapped_column(sa.String(64))  # snapshot, survives admin deletion
    action: Mapped[str] = mapped_column(sa.String(64))
    entity_type: Mapped[str | None] = mapped_column(sa.String(64))
    entity_id: Mapped[str | None] = mapped_column(sa.String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=sa.text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now(), index=True)
