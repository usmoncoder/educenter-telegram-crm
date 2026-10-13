from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings

SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(settings: Settings | None = None, **kwargs: object) -> AsyncEngine:
    settings = settings or get_settings()
    options: dict[str, object] = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,
        **kwargs,  # callers may override pool options (e.g. the healthcheck uses a 1-connection pool)
    }
    return create_async_engine(settings.database_url.get_secret_value(), **options)  # type: ignore[arg-type]


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def transaction(factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Open a session with a transaction that commits on success and rolls back on error."""
    async with factory() as session, session.begin():
        yield session
