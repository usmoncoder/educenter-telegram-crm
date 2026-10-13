"""FastAPI dependencies: DB session, authentication, CSRF and permission checks."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.permissions import Perm, has_perm
from app.core.security import constant_time_equals
from app.db.models import Admin, AdminSession
from app.db.session import SessionFactory
from app.services.auth import resolve_session

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "X-CSRF-Token"


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_factory(request: Request) -> SessionFactory:
    return request.app.state.session_factory


async def get_db(factory: SessionFactory = Depends(get_factory)) -> AsyncIterator[AsyncSession]:
    """One transaction per request: committed if the handler succeeds, rolled back otherwise."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def client_ip(request: Request) -> str | None:
    settings: Settings = request.app.state.settings
    if settings.trusted_proxy_count > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hops) >= settings.trusted_proxy_count:
            return hops[-settings.trusted_proxy_count][:64]
    return request.client.host[:64] if request.client else None


@dataclass
class Principal:
    admin: Admin
    session: AdminSession

    def can(self, perm: Perm) -> bool:
        return has_perm(self.admin.role, perm)


async def get_principal(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Principal:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise AuthenticationError("Tizimga kiring")
    resolved = await resolve_session(db, token)
    if resolved is None:
        raise AuthenticationError("Sessiya muddati tugagan. Qayta kiring.", code="session_expired")
    admin, sess = resolved
    if request.method in UNSAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        if not header or not constant_time_equals(header, sess.csrf_token):
            raise PermissionDeniedError("CSRF tekshiruvi muvaffaqiyatsiz. Sahifani yangilang.", code="csrf_failed")
    return Principal(admin=admin, session=sess)


def require(*perms: Perm) -> Callable[..., Principal]:
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        for perm in perms:
            if not principal.can(perm):
                raise PermissionDeniedError("Bu amal uchun ruxsatingiz yo'q")
        return principal

    return dependency
