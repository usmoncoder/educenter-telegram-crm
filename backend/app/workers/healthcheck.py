"""Container healthcheck for the worker: healthy while its database heartbeat is fresh.

    python -m app.workers.healthcheck      (exit code 0 = healthy, 1 = unhealthy)

The worker writes a liveness heartbeat during its whole lifetime (also while connecting or
waiting for Telegram authorization), so this detects a hung or crashed worker, not a
Telegram outage - Telegram connection state is shown separately in the dashboard.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.db.models import WorkerState
from app.db.session import create_engine


async def check() -> bool:
    settings = get_settings()
    engine = create_engine(settings, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as conn:
            beat = await conn.scalar(sa.select(WorkerState.last_heartbeat_at).where(WorkerState.id == 1))
    finally:
        await engine.dispose()
    return beat is not None and utcnow() - beat < timedelta(seconds=settings.worker_stale_after_seconds)


def main() -> None:
    try:
        ok = asyncio.run(check())
    except Exception:  # noqa: BLE001
        ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
