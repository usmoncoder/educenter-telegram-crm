"""Administrator authentication: login with lockout, server-side sessions, password changes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthenticationError, RateLimitedError, ValidationAppError
from app.core.security import (
    hash_password,
    needs_rehash,
    new_csrf_token,
    new_session_token,
    password_problems,
    token_digest,
    verify_password,
)
from app.core.timeutil import utcnow
from app.db.models import Admin, AdminSession, RateLimitHit

LOGIN_WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_USER = 5
MAX_FAILURES_PER_IP = 20
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass
class LoginResult:
    admin: Admin
    token: str
    csrf_token: str


async def count_hits(session: AsyncSession, key: str, window: timedelta) -> int:
    return int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(RateLimitHit)
            .where(RateLimitHit.key == key, RateLimitHit.created_at > utcnow() - window)
        )
        or 0
    )


async def hit(session: AsyncSession, key: str) -> None:
    session.add(RateLimitHit(key=key[:160]))


async def enforce_rate_limit(session: AsyncSession, key: str, limit: int, window: timedelta) -> None:
    """Generic shared rate limit (counts every call)."""
    if await count_hits(session, key, window) >= limit:
        raise RateLimitedError("Juda ko'p so'rov. Birozdan keyin qayta urinib ko'ring.")
    await hit(session, key)


async def login(
    session: AsyncSession, settings: Settings, username: str, password: str, ip: str | None, user_agent: str | None
) -> LoginResult:
    username = username.strip().lower()
    user_key, ip_key = f"login_fail:user:{username}", f"login_fail:ip:{ip or '-'}"
    if (
        await count_hits(session, user_key, LOGIN_WINDOW) >= MAX_FAILURES_PER_USER
        or await count_hits(session, ip_key, LOGIN_WINDOW) >= MAX_FAILURES_PER_IP
    ):
        raise RateLimitedError("Juda ko'p muvaffaqiyatsiz urinish. 15 daqiqadan so'ng qayta urinib ko'ring.")

    admin = await session.scalar(sa.select(Admin).where(Admin.username == username))
    ok = verify_password(admin.password_hash if admin else None, password)
    if not ok or admin is None or not admin.is_active:
        await hit(session, user_key)
        await hit(session, ip_key)
        await session.commit()  # persist the failure counters even though the request fails
        raise AuthenticationError("Login yoki parol noto'g'ri", code="invalid_credentials")

    if needs_rehash(admin.password_hash):
        admin.password_hash = hash_password(password)
    token, csrf = new_session_token(), new_csrf_token()
    now = utcnow()
    session.add(
        AdminSession(
            id=token_digest(token),
            admin_id=admin.id,
            csrf_token=csrf,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
            ip=ip,
            user_agent=(user_agent or "")[:256] or None,
        )
    )
    admin.last_login_at = now
    await session.execute(sa.delete(RateLimitHit).where(RateLimitHit.key == user_key))
    return LoginResult(admin=admin, token=token, csrf_token=csrf)


async def resolve_session(session: AsyncSession, token: str) -> tuple[Admin, AdminSession] | None:
    row = (
        await session.execute(
            sa.select(AdminSession, Admin)
            .join(Admin, Admin.id == AdminSession.admin_id)
            .where(AdminSession.id == token_digest(token))
        )
    ).one_or_none()
    if row is None:
        return None
    sess, admin = row
    now = utcnow()
    if sess.revoked_at is not None or sess.expires_at <= now or not admin.is_active:
        return None
    if now - sess.last_seen_at > SESSION_TOUCH_INTERVAL:
        sess.last_seen_at = now
    return admin, sess


async def revoke_session(session: AsyncSession, session_id: str) -> None:
    await session.execute(sa.update(AdminSession).where(AdminSession.id == session_id).values(revoked_at=utcnow()))


async def revoke_all_sessions(session: AsyncSession, admin_id: int, except_id: str | None = None) -> None:
    stmt = sa.update(AdminSession).where(AdminSession.admin_id == admin_id, AdminSession.revoked_at.is_(None))
    if except_id:
        stmt = stmt.where(AdminSession.id != except_id)
    await session.execute(stmt.values(revoked_at=utcnow()))


def validate_new_password(password: str, username: str) -> None:
    problems = password_problems(password, username)
    if problems:
        raise ValidationAppError("; ".join(problems), code="weak_password")


async def change_password(session: AsyncSession, admin: Admin, current: str, new: str, current_session_id: str) -> None:
    if not verify_password(admin.password_hash, current):
        raise ValidationAppError("Joriy parol noto'g'ri", code="invalid_current_password")
    validate_new_password(new, admin.username)
    admin.password_hash = hash_password(new)
    admin.password_changed_at = utcnow()
    await revoke_all_sessions(session, admin.id, except_id=current_session_id)
