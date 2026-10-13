"""Automatic response editor, message preview, system settings, Telegram connection status."""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, client_ip, get_db, get_settings_dep, require
from app.core.config import Settings
from app.core.errors import ValidationAppError
from app.core.permissions import Perm
from app.db.enums import CommandStatus, CommandType, WelcomeStatus
from app.db.models import ConnectionEvent, Customer, WorkerCommand
from app.schemas.api import (
    AutoReplyOut,
    AutoReplyUpdate,
    CommandOut,
    ConnectionEventOut,
    PreviewOut,
    PreviewRequest,
    WorkerStatusOut,
)
from app.services.app_settings import RuntimeSettings, load_settings, save_settings
from app.services.audit import audit
from app.services.auth import enforce_rate_limit
from app.services.formatting import TELEGRAM_TEXT_LIMIT, parse_message
from app.services.metrics import worker_status

router = APIRouter(tags=["config"])


def _validation_message(exc: ValidationError) -> str:
    msgs = []
    for err in exc.errors():
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "__root__")
        msgs.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(msgs)


@router.post("/messages/preview", response_model=PreviewOut)
async def preview(body: PreviewRequest, _: Principal = Depends(require(Perm.CONVERSATIONS_VIEW))) -> PreviewOut:
    parsed = parse_message(body.text)
    return PreviewOut(
        text=parsed.text,
        entities=parsed.entities,
        length=parsed.length,
        limit=TELEGRAM_TEXT_LIMIT,
        errors=parsed.errors,
    )


# ------------------------------------------------------------------------------- auto reply
async def _welcome_stats(db: AsyncSession) -> dict[str, int]:
    rows = (
        await db.execute(sa.select(Customer.welcome_status, sa.func.count()).group_by(Customer.welcome_status))
    ).all()
    stats = {s.value: 0 for s in WelcomeStatus}
    for status, n in rows:
        stats[getattr(status, "value", status)] = int(n)
    return stats


@router.get("/autoreply", response_model=AutoReplyOut)
async def get_autoreply(
    _: Principal = Depends(require(Perm.AUTOREPLY_MANAGE)), db: AsyncSession = Depends(get_db)
) -> AutoReplyOut:
    s = await load_settings(db)
    return AutoReplyOut(
        welcome_enabled=s.welcome_enabled,
        welcome_text=s.welcome_text,
        welcome_delay_seconds=s.welcome_delay_seconds,
        welcome_only_new_chats=s.welcome_only_new_chats,
        welcome_link_preview=s.welcome_link_preview,
        welcome_excluded_user_ids=s.welcome_excluded_user_ids,
        stats=await _welcome_stats(db),
    )


@router.put("/autoreply", response_model=AutoReplyOut)
async def update_autoreply(
    body: AutoReplyUpdate,
    request: Request,
    principal: Principal = Depends(require(Perm.AUTOREPLY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AutoReplyOut:
    current = await load_settings(db)
    try:
        new = RuntimeSettings.model_validate({**current.model_dump(), **body.model_dump()})
    except ValidationError as exc:
        raise ValidationAppError(_validation_message(exc))
    await save_settings(db, new, principal.admin.id)
    await audit(
        db,
        "autoreply.update",
        actor=principal.admin,
        entity_type="settings",
        entity_id="autoreply",
        details={
            "enabled": new.welcome_enabled,
            "delay": new.welcome_delay_seconds,
            "text_length": len(new.welcome_text),
        },
        ip=client_ip(request),
    )
    return await get_autoreply(principal, db)


# ------------------------------------------------------------------------------- settings
@router.get("/settings", response_model=RuntimeSettings)
async def get_settings_route(
    _: Principal = Depends(require(Perm.SETTINGS_MANAGE)), db: AsyncSession = Depends(get_db)
) -> RuntimeSettings:
    return await load_settings(db)


@router.put("/settings", response_model=RuntimeSettings)
async def update_settings(
    body: dict,
    request: Request,
    principal: Principal = Depends(require(Perm.SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RuntimeSettings:
    current = await load_settings(db)
    unknown = set(body) - set(RuntimeSettings.model_fields)
    if unknown:
        raise ValidationAppError(f"Noma'lum sozlamalar: {', '.join(sorted(unknown))}")
    try:
        new = RuntimeSettings.model_validate({**current.model_dump(), **body})
    except ValidationError as exc:
        raise ValidationAppError(_validation_message(exc))
    await save_settings(db, new, principal.admin.id)
    old_d, new_d = current.model_dump(), new.model_dump()
    changed = {k: new_d[k] for k in new_d if old_d[k] != new_d[k] and k != "welcome_text"}
    await audit(
        db,
        "settings.update",
        actor=principal.admin,
        entity_type="settings",
        entity_id="runtime",
        details={"changed": changed},
        ip=client_ip(request),
    )
    return new


# ------------------------------------------------------------------------------- telegram
@router.get("/telegram/status", response_model=WorkerStatusOut)
async def telegram_status(
    _: Principal = Depends(require(Perm.TELEGRAM_VIEW)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> WorkerStatusOut:
    return WorkerStatusOut(**await worker_status(db, settings))


@router.get("/telegram/events", response_model=list[ConnectionEventOut])
async def telegram_events(
    _: Principal = Depends(require(Perm.TELEGRAM_VIEW)),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=200),
) -> list[ConnectionEventOut]:
    rows = (await db.scalars(sa.select(ConnectionEvent).order_by(ConnectionEvent.id.desc()).limit(limit))).all()
    return [ConnectionEventOut.model_validate(r) for r in rows]


async def queue_command(
    db: AsyncSession, principal: Principal, command: CommandType, payload: dict | None = None
) -> WorkerCommand:
    await enforce_rate_limit(db, f"cmd:{principal.admin.id}", limit=20, window=timedelta(minutes=5))
    existing = await db.scalar(
        sa.select(WorkerCommand).where(
            WorkerCommand.command == command,
            WorkerCommand.status.in_([CommandStatus.PENDING, CommandStatus.RUNNING]),
            WorkerCommand.payload == (payload or {}),
        )
    )
    if existing is not None:
        return existing  # idempotent: don't queue the same command twice
    cmd = WorkerCommand(command=command, payload=payload or {}, requested_by_admin_id=principal.admin.id)
    db.add(cmd)
    await db.flush()
    await db.refresh(cmd)
    return cmd


@router.post("/telegram/reconnect", response_model=CommandOut, status_code=202)
async def telegram_reconnect(
    request: Request,
    principal: Principal = Depends(require(Perm.TELEGRAM_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CommandOut:
    cmd = await queue_command(db, principal, CommandType.RECONNECT)
    await audit(db, "telegram.reconnect", actor=principal.admin, ip=client_ip(request))
    return CommandOut.model_validate(cmd)


@router.post("/telegram/test-alert", response_model=CommandOut, status_code=202)
async def telegram_test_alert(
    request: Request,
    principal: Principal = Depends(require(Perm.SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CommandOut:
    cmd = await queue_command(db, principal, CommandType.TEST_ALERT)
    await audit(db, "alerts.test", actor=principal.admin, ip=client_ip(request))
    return CommandOut.model_validate(cmd)


@router.get("/commands/{command_id}", response_model=CommandOut)
async def get_command(
    command_id: int,
    _: Principal = Depends(require(Perm.TELEGRAM_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> CommandOut:
    cmd = await db.get(WorkerCommand, command_id)
    if cmd is None:
        raise ValidationAppError("Buyruq topilmadi")
    return CommandOut.model_validate(cmd)
