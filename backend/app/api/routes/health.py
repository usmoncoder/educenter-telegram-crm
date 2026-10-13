from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_factory
from app.db.session import SessionFactory

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Process is up. Exposes no configuration or customer data."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(factory: SessionFactory = Depends(get_factory)) -> JSONResponse:
    try:
        async with factory() as s:
            await s.execute(sa.text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "up"})
