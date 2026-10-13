"""Administrator accounts and audit log (Super Admin only)."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, client_ip, get_db, require
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.permissions import Perm
from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.db.enums import Role
from app.db.models import Admin, AuditEvent
from app.schemas.api import AdminCreate, AdminOut, AdminUpdate, AuditOut, ResetPasswordRequest
from app.schemas.common import Page
from app.services.audit import audit
from app.services.auth import revoke_all_sessions, validate_new_password

router = APIRouter(tags=["admin"])


async def _active_super_admins(db: AsyncSession) -> int:
    return int(
        await db.scalar(
            sa.select(sa.func.count())
            .select_from(Admin)
            .where(Admin.role == Role.SUPER_ADMIN, Admin.is_active.is_(True))
        )
        or 0
    )


@router.get("/admins", response_model=list[AdminOut])
async def list_admins(
    _: Principal = Depends(require(Perm.ADMINS_MANAGE)), db: AsyncSession = Depends(get_db)
) -> list[AdminOut]:
    rows = (await db.scalars(sa.select(Admin).order_by(Admin.role, Admin.username))).all()
    return [AdminOut.model_validate(a) for a in rows]


@router.post("/admins", response_model=AdminOut, status_code=201)
async def create_admin(
    body: AdminCreate,
    request: Request,
    principal: Principal = Depends(require(Perm.ADMINS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AdminOut:
    if await db.scalar(sa.select(Admin.id).where(Admin.username == body.username)):
        raise ConflictError("Bu login band")
    validate_new_password(body.password, body.username)
    admin = Admin(
        username=body.username,
        full_name=body.full_name.strip(),
        role=body.role,
        password_hash=hash_password(body.password),
        password_changed_at=utcnow(),
    )
    db.add(admin)
    await db.flush()
    await audit(
        db,
        "admin.create",
        actor=principal.admin,
        entity_type="admin",
        entity_id=admin.id,
        details={"username": admin.username, "role": admin.role},
        ip=client_ip(request),
    )
    await db.refresh(admin)
    return AdminOut.model_validate(admin)


@router.patch("/admins/{admin_id}", response_model=AdminOut)
async def update_admin(
    admin_id: int,
    body: AdminUpdate,
    request: Request,
    principal: Principal = Depends(require(Perm.ADMINS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AdminOut:
    admin = await db.get(Admin, admin_id, with_for_update=True)
    if admin is None:
        raise NotFoundError("Xodim topilmadi")
    demoting = admin.role == Role.SUPER_ADMIN and (
        (body.role is not None and body.role != Role.SUPER_ADMIN) or body.is_active is False
    )
    if demoting and admin.is_active and await _active_super_admins(db) <= 1:
        raise ConflictError("Kamida bitta faol Super Admin qolishi kerak")
    if admin.id == principal.admin.id and body.is_active is False:
        raise ValidationAppError("O'z akkauntingizni o'chira olmaysiz")
    changes: dict[str, object] = {}
    if body.username is not None and body.username != admin.username:
        if await db.scalar(sa.select(Admin.id).where(Admin.username == body.username, Admin.id != admin.id)):
            raise ConflictError("Bu login band")
        changes["username"] = {"from": admin.username, "to": body.username}
        admin.username = body.username
    if body.full_name is not None:
        admin.full_name = body.full_name.strip()
        changes["full_name"] = admin.full_name
    if body.role is not None and body.role != admin.role:
        admin.role = body.role
        changes["role"] = body.role
    if body.is_active is not None and body.is_active != admin.is_active:
        admin.is_active = body.is_active
        changes["is_active"] = body.is_active
        if not body.is_active:
            await revoke_all_sessions(db, admin.id)
    await audit(
        db,
        "admin.update",
        actor=principal.admin,
        entity_type="admin",
        entity_id=admin.id,
        details=changes,
        ip=client_ip(request),
    )
    await db.flush()
    await db.refresh(admin)
    return AdminOut.model_validate(admin)


@router.post("/admins/{admin_id}/reset-password", response_model=AdminOut)
async def reset_password(
    admin_id: int,
    body: ResetPasswordRequest,
    request: Request,
    principal: Principal = Depends(require(Perm.ADMINS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AdminOut:
    admin = await db.get(Admin, admin_id, with_for_update=True)
    if admin is None:
        raise NotFoundError("Xodim topilmadi")
    validate_new_password(body.new_password, admin.username)
    admin.password_hash = hash_password(body.new_password)
    admin.password_changed_at = utcnow()
    await revoke_all_sessions(db, admin.id)
    await audit(
        db,
        "admin.reset_password",
        actor=principal.admin,
        entity_type="admin",
        entity_id=admin.id,
        ip=client_ip(request),
    )
    return AdminOut.model_validate(admin)


@router.get("/audit", response_model=Page[AuditOut])
async def audit_log(
    _: Principal = Depends(require(Perm.AUDIT_VIEW)),
    db: AsyncSession = Depends(get_db),
    action: str | None = Query(default=None, max_length=64),
    actor: str | None = Query(default=None, max_length=64),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> Page[AuditOut]:
    stmt = sa.select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    if actor:
        stmt = stmt.where(AuditEvent.actor_username == actor.lower())
    if date_from:
        stmt = stmt.where(AuditEvent.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditEvent.created_at <= date_to)
    total = await db.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
    rows = (await db.scalars(stmt.order_by(AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return Page(items=[AuditOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)
