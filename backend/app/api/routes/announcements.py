"""Telegram groups, announcement campaigns, delivery history, reports."""

from __future__ import annotations

from datetime import date
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import Principal, client_ip, get_db, require
from app.api.routes.config import queue_command
from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import Perm
from app.db.enums import CampaignStatus, CommandType, DeliveryStatus, OutboxStatus, WelcomeStatus
from app.db.models import (
    Admin,
    AnnouncementCampaign,
    AnnouncementDelivery,
    AnnouncementRun,
    CampaignTarget,
    Conversation,
    Customer,
    OutgoingMessage,
    SlaIncident,
    TelegramGroup,
)
from app.schemas.api import (
    CampaignIn,
    CampaignOut,
    CommandOut,
    ConfirmRequest,
    DeliveryOut,
    GroupOut,
    GroupUpdate,
    ManualGroupRequest,
    RunOut,
)
from app.schemas.common import OkResponse, Page
from app.services import campaigns as svc
from app.services.audit import audit
from app.services.metrics import ensure_range, report

router = APIRouter(tags=["announcements"])


# ------------------------------------------------------------------------------- groups
@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    _: Principal = Depends(require(Perm.GROUPS_VIEW)),
    db: AsyncSession = Depends(get_db),
    only_enabled: bool = False,
) -> list[GroupOut]:
    stmt = sa.select(TelegramGroup).order_by(TelegramGroup.is_enabled.desc(), TelegramGroup.title)
    if only_enabled:
        stmt = stmt.where(TelegramGroup.is_enabled.is_(True))
    return [GroupOut.model_validate(g) for g in (await db.scalars(stmt)).all()]


@router.patch("/groups/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int,
    body: GroupUpdate,
    request: Request,
    principal: Principal = Depends(require(Perm.GROUPS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> GroupOut:
    group = await db.get(TelegramGroup, group_id, with_for_update=True)
    if group is None:
        raise NotFoundError("Guruh topilmadi")
    if body.is_enabled and not (group.is_member and group.can_send):
        raise ConflictError(group.permission_note or "Akkaunt bu guruhga xabar yubora olmaydi")
    group.is_enabled = body.is_enabled
    await audit(
        db,
        "group.enable" if body.is_enabled else "group.disable",
        actor=principal.admin,
        entity_type="group",
        entity_id=group_id,
        details={"title": group.title},
        ip=client_ip(request),
    )
    return GroupOut.model_validate(group)


@router.delete("/groups/{group_id}", response_model=OkResponse)
async def delete_group(
    group_id: int,
    request: Request,
    principal: Principal = Depends(require(Perm.GROUPS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    group = await db.get(TelegramGroup, group_id)
    if group is None:
        raise NotFoundError("Guruh topilmadi")
    used = await db.scalar(
        sa.select(sa.func.count()).select_from(CampaignTarget).where(CampaignTarget.group_id == group_id)
    )
    used_hist = await db.scalar(
        sa.select(sa.func.count()).select_from(AnnouncementDelivery).where(AnnouncementDelivery.group_id == group_id)
    )
    if used or used_hist:
        raise ConflictError("Guruh e'lonlarda ishlatilgan. Uni o'chirish o'rniga e'lonlar uchun o'chirib qo'ying.")
    await db.delete(group)
    await audit(
        db,
        "group.delete",
        actor=principal.admin,
        entity_type="group",
        entity_id=group_id,
        details={"title": group.title},
        ip=client_ip(request),
    )
    return OkResponse()


@router.post("/groups/sync", response_model=CommandOut, status_code=202)
async def sync_groups(
    request: Request,
    principal: Principal = Depends(require(Perm.GROUPS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CommandOut:
    cmd = await queue_command(db, principal, CommandType.SYNC_GROUPS)
    await audit(db, "group.sync_requested", actor=principal.admin, ip=client_ip(request))
    return CommandOut.model_validate(cmd)


@router.post("/groups/manual", response_model=CommandOut, status_code=202)
async def add_manual_group(
    body: ManualGroupRequest,
    request: Request,
    principal: Principal = Depends(require(Perm.GROUPS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CommandOut:
    cmd = await queue_command(db, principal, CommandType.RESOLVE_GROUP, {"identifier": body.identifier.strip()})
    await audit(
        db,
        "group.manual_requested",
        actor=principal.admin,
        details={"identifier": body.identifier},
        ip=client_ip(request),
    )
    return CommandOut.model_validate(cmd)


# ------------------------------------------------------------------------------- campaigns
@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(
    _: Principal = Depends(require(Perm.CAMPAIGNS_VIEW)),
    db: AsyncSession = Depends(get_db),
    status: CampaignStatus | None = None,
) -> list[CampaignOut]:
    stmt = (
        sa.select(AnnouncementCampaign)
        .options(selectinload(AnnouncementCampaign.targets).selectinload(CampaignTarget.group))
        .order_by(
            sa.case(
                (AnnouncementCampaign.status == CampaignStatus.SCHEDULED, 0),
                (AnnouncementCampaign.status == CampaignStatus.DRAFT, 1),
                (AnnouncementCampaign.status == CampaignStatus.PAUSED, 2),
                else_=3,
            ),
            AnnouncementCampaign.next_run_at.asc().nulls_last(),
            AnnouncementCampaign.id.desc(),
        )
        .limit(200)
    )
    if status:
        stmt = stmt.where(AnnouncementCampaign.status == status)
    return [await svc.campaign_out(db, c) for c in (await db.scalars(stmt)).all()]


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignIn,
    request: Request,
    principal: Principal = Depends(require(Perm.CAMPAIGNS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    c = await svc.create_campaign(db, body, principal.admin)
    await audit(
        db,
        "campaign.create",
        actor=principal.admin,
        entity_type="campaign",
        entity_id=c.id,
        details={"title": c.title, "targets": len(c.targets), "schedule": c.schedule_type},
        ip=client_ip(request),
    )
    return await svc.campaign_out(db, c)


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: int, _: Principal = Depends(require(Perm.CAMPAIGNS_VIEW)), db: AsyncSession = Depends(get_db)
) -> CampaignOut:
    return await svc.campaign_out(db, await svc._load(db, campaign_id))


@router.put("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: int,
    body: CampaignIn,
    request: Request,
    principal: Principal = Depends(require(Perm.CAMPAIGNS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    c = await svc.update_campaign(db, campaign_id, body)
    await audit(
        db,
        "campaign.update",
        actor=principal.admin,
        entity_type="campaign",
        entity_id=c.id,
        details={"title": c.title, "targets": len(c.targets)},
        ip=client_ip(request),
    )
    return await svc.campaign_out(db, c)


async def _transition(
    action: str, campaign_id: int, request: Request, principal: Principal, db: AsyncSession, fn, *args
) -> CampaignOut:
    c = await fn(db, campaign_id, *args)
    await audit(
        db,
        f"campaign.{action}",
        actor=principal.admin,
        entity_type="campaign",
        entity_id=campaign_id,
        details={"title": c.title, "targets": len(c.targets)},
        ip=client_ip(request),
    )
    await db.flush()
    return await svc.campaign_out(db, await svc._load(db, campaign_id))


@router.post("/campaigns/{campaign_id}/activate", response_model=CampaignOut)
async def activate_campaign(
    campaign_id: int,
    body: ConfirmRequest,
    request: Request,
    principal: Principal = Depends(require(Perm.CAMPAIGNS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    return await _transition("activate", campaign_id, request, principal, db, svc.activate, body.confirm)


@router.post("/campaigns/{campaign_id}/send-now", response_model=CampaignOut)
async def send_campaign_now(
    campaign_id: int,
    body: ConfirmRequest,
    request: Request,
    principal: Principal = Depends(require(Perm.CAMPAIGNS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    return await _transition("send_now", campaign_id, request, principal, db, svc.send_now, body.confirm)


@router.post("/campaigns/{campaign_id}/pause", response_model=CampaignOut)
async def pause_campaign(
    campaign_id: int,
    request: Request,
    principal: Principal = Depends(require(Perm.CAMPAIGNS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    return await _transition("pause", campaign_id, request, principal, db, svc.pause)


@router.post("/campaigns/{campaign_id}/resume", response_model=CampaignOut)
async def resume_campaign(
    campaign_id: int,
    request: Request,
    principal: Principal = Depends(require(Perm.CAMPAIGNS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    return await _transition("resume", campaign_id, request, principal, db, svc.resume)


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignOut)
async def cancel_campaign(
    campaign_id: int,
    request: Request,
    principal: Principal = Depends(require(Perm.CAMPAIGNS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    return await _transition("cancel", campaign_id, request, principal, db, svc.cancel)


@router.get("/campaigns/{campaign_id}/runs", response_model=list[RunOut])
async def campaign_runs(
    campaign_id: int, _: Principal = Depends(require(Perm.CAMPAIGNS_VIEW)), db: AsyncSession = Depends(get_db)
) -> list[RunOut]:
    await svc._load(db, campaign_id)
    return await svc.list_runs(db, campaign_id)


# ------------------------------------------------------------------------------- history
@router.get("/history/deliveries", response_model=Page[DeliveryOut])
async def delivery_history(
    _: Principal = Depends(require(Perm.HISTORY_VIEW)),
    db: AsyncSession = Depends(get_db),
    status: DeliveryStatus | None = None,
    campaign_id: int | None = None,
    group_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[DeliveryOut]:
    stmt = (
        sa.select(AnnouncementDelivery, AnnouncementRun, AnnouncementCampaign.title, TelegramGroup.title)
        .join(AnnouncementRun, AnnouncementRun.id == AnnouncementDelivery.run_id)
        .join(AnnouncementCampaign, AnnouncementCampaign.id == AnnouncementRun.campaign_id)
        .join(TelegramGroup, TelegramGroup.id == AnnouncementDelivery.group_id)
    )
    if status:
        stmt = stmt.where(AnnouncementDelivery.status == status)
    if campaign_id:
        stmt = stmt.where(AnnouncementCampaign.id == campaign_id)
    if group_id:
        stmt = stmt.where(AnnouncementDelivery.group_id == group_id)
    total = await db.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await db.execute(stmt.order_by(AnnouncementDelivery.id.desc()).offset((page - 1) * page_size).limit(page_size))
    ).all()
    items = [
        DeliveryOut(
            id=d.id,
            run_id=r.id,
            campaign_id=r.campaign_id,
            campaign_title=ct,
            group_id=d.group_id,
            group_title=gt,
            status=d.status,
            attempts=d.attempts,
            error_code=d.error_code,
            error_message=d.error_message,
            sent_at=d.sent_at,
            scheduled_for=r.scheduled_for,
            created_at=d.created_at,
            text=d.text,
        )
        for d, r, ct, gt in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/history/system")
async def system_history(
    _: Principal = Depends(require(Perm.HISTORY_VIEW)),
    db: AsyncSession = Depends(get_db),
    kind: Literal["welcome", "alerts", "replies"] = "welcome",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict:
    """History of automatic welcome messages, administrator alerts and panel replies."""
    offset = (page - 1) * page_size
    if kind == "welcome":
        stmt = sa.select(Customer).where(Customer.welcome_status.not_in([WelcomeStatus.NOT_APPLICABLE]))
        total = await db.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
        rows = (await db.scalars(stmt.order_by(Customer.first_seen_at.desc()).offset(offset).limit(page_size))).all()
        items = [
            {
                "id": c.id,
                "customer_id": c.id,
                "customer": c.display_name,
                "telegram_user_id": c.telegram_user_id,
                "status": c.welcome_status,
                "at": c.welcome_sent_at or c.updated_at,
                "error": c.welcome_error,
                "attempts": c.welcome_attempts,
            }
            for c in rows
        ]
    elif kind == "alerts":
        stmt = (
            sa.select(SlaIncident, Customer)
            .join(Conversation, Conversation.id == SlaIncident.conversation_id)
            .join(Customer, Customer.id == Conversation.customer_id)
            .where(SlaIncident.alert_status.in_(["pending", "sending", "sent", "failed"]))
        )
        total = await db.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
        rows = (await db.execute(stmt.order_by(SlaIncident.deadline_at.desc()).offset(offset).limit(page_size))).all()
        items = [
            {
                "id": i.id,
                "customer_id": c.id,
                "customer": c.display_name,
                "telegram_user_id": c.telegram_user_id,
                "status": i.alert_status,
                "at": i.alerted_at or i.deadline_at,
                "error": i.alert_error,
                "attempts": i.alert_attempts,
                "incident_status": i.status,
            }
            for i, c in rows
        ]
    else:
        stmt = (
            sa.select(OutgoingMessage, Customer, Admin.username)
            .join(Conversation, Conversation.id == OutgoingMessage.conversation_id)
            .join(Customer, Customer.id == Conversation.customer_id)
            .outerjoin(Admin, Admin.id == OutgoingMessage.requested_by_admin_id)
            .where(OutgoingMessage.status.in_(list(OutboxStatus)))
        )
        total = await db.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
        rows = (await db.execute(stmt.order_by(OutgoingMessage.id.desc()).offset(offset).limit(page_size))).all()
        items = [
            {
                "id": o.id,
                "customer_id": c.id,
                "customer": c.display_name,
                "telegram_user_id": c.telegram_user_id,
                "status": o.status,
                "at": o.sent_at or o.created_at,
                "error": o.error,
                "attempts": o.attempts,
                "admin": un,
                "conversation_id": o.conversation_id,
            }
            for o, c, un in rows
        ]
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


# ------------------------------------------------------------------------------- reports
@router.get("/reports")
async def reports(
    _: Principal = Depends(require(Perm.REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    d1, d2 = ensure_range(date_from, date_to)
    return await report(db, d1, d2)
