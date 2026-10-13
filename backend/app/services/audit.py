from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, redact_value
from app.db.models import Admin, AuditEvent

log = get_logger("audit")


async def audit(
    session: AsyncSession,
    action: str,
    *,
    actor: Admin | None,
    entity_type: str | None = None,
    entity_id: object = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Record an administrator action in the same transaction as the change itself."""
    safe_details = redact_value(details or {})
    session.add(
        AuditEvent(
            actor_admin_id=actor.id if actor else None,
            actor_username=actor.username if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=safe_details,
            ip=ip,
        )
    )
    log.info(
        "audit",
        action=action,
        actor=actor.username if actor else None,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
    )
