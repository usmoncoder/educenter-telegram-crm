"""Dashboard, customers, conversations, incidents (Javobsiz murojaatlar)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, client_ip, get_db, get_settings_dep, require
from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.permissions import Perm
from app.core.timeutil import utcnow
from app.db.enums import AlertStatus, IncidentStatus, OutboxStatus, Resolution, Role
from app.db.models import Admin, Conversation, Customer, Message, OutgoingMessage, SlaIncident
from app.schemas.api import (
    AssignRequest,
    ConversationOut,
    CustomerDetailOut,
    CustomerOut,
    ExcludeRequest,
    IncidentOut,
    MessageOut,
    OutgoingOut,
    ReplyRequest,
)
from app.schemas.common import OkResponse, Page
from app.services import crm_queries as q
from app.services.app_settings import load_settings, save_settings
from app.services.audit import audit
from app.services.auth import enforce_rate_limit
from app.services.formatting import parse_message
from app.services.metrics import dashboard_summary, local_day_start

router = APIRouter(tags=["crm"])


@router.get("/dashboard")
async def dashboard(
    principal: Principal = Depends(require(Perm.DASHBOARD_VIEW)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    summary = await dashboard_summary(db, settings)
    recent, _ = await q.list_conversations(db, principal, limit=8)
    waiting, _ = await q.list_incidents(db, principal, status="open", limit=8)
    summary["latest_activity"] = [c.model_dump(mode="json") for c in recent]
    summary["waiting_incidents"] = [i.model_dump(mode="json") for i in waiting]
    if not principal.can(Perm.HISTORY_VIEW):
        summary["recent_errors"] = []
    return summary


# ------------------------------------------------------------------------------- customers
@router.get("/customers", response_model=Page[CustomerOut])
async def list_customers(
    principal: Principal = Depends(require(Perm.CUSTOMERS_VIEW)),
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(default=None, max_length=100),
    status: Literal["all", "unanswered", "overdue", "welcome_sent", "welcome_failed", "excluded"] = "all",
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[CustomerOut]:
    stmt = (
        sa.select(Customer)
        .outerjoin(Conversation, Conversation.customer_id == Customer.id)
        .where(sa.or_(Conversation.id.is_(None), await q.conversation_scope(db, principal)))
    )
    if not principal.can(Perm.CONVERSATIONS_VIEW_ALL):
        stmt = stmt.where(Conversation.id.is_not(None))
    if search:
        stmt = stmt.where(q.search_clause(search))
    if date_from:
        stmt = stmt.where(Customer.first_seen_at >= local_day_start(date_from))
    if date_to:
        stmt = stmt.where(Customer.first_seen_at < local_day_start(date_to + timedelta(days=1)))
    open_inc = sa.select(SlaIncident.id).where(
        SlaIncident.conversation_id == Conversation.id, SlaIncident.status == IncidentStatus.OPEN
    )
    if status == "unanswered":
        stmt = stmt.where(open_inc.exists())
    elif status == "overdue":
        stmt = stmt.where(open_inc.where(SlaIncident.deadline_at <= utcnow()).exists())
    elif status == "welcome_sent":
        stmt = stmt.where(Customer.welcome_status == "sent")
    elif status == "welcome_failed":
        stmt = stmt.where(Customer.welcome_status.in_(["failed", "unknown"]))
    elif status == "excluded":
        stmt = stmt.where(Customer.is_excluded.is_(True))
    total = await db.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await db.scalars(
            stmt.order_by(Conversation.last_message_at.desc().nulls_last(), Customer.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(items=[CustomerOut.model_validate(c) for c in rows], total=total, page=page, page_size=page_size)


async def _customer_or_404(db: AsyncSession, principal: Principal, customer_id: int) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Mijoz topilmadi")
    if not principal.can(Perm.CONVERSATIONS_VIEW_ALL):
        conv = await q.conversation_for_customer(db, principal, customer_id)
        if conv is None:
            raise NotFoundError("Mijoz topilmadi")
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerDetailOut)
async def customer_detail(
    customer_id: int,
    principal: Principal = Depends(require(Perm.CUSTOMERS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> CustomerDetailOut:
    customer = await _customer_or_404(db, principal, customer_id)
    conv = await q.conversation_for_customer(db, principal, customer_id)
    incidents: list[IncidentOut] = []
    msg_count = 0
    if conv:
        incidents, _ = await q.list_incidents(db, principal, status="all", conversation_id=conv.id, limit=50)
        msg_count = int(
            await db.scalar(sa.select(sa.func.count()).select_from(Message).where(Message.conversation_id == conv.id))
            or 0
        )
    return CustomerDetailOut(
        customer=CustomerOut.model_validate(customer), conversation=conv, incidents=incidents, message_count=msg_count
    )


@router.post("/customers/{customer_id}/exclude", response_model=CustomerOut)
async def exclude_customer(
    customer_id: int,
    body: ExcludeRequest,
    request: Request,
    principal: Principal = Depends(require(Perm.CUSTOMERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CustomerOut:
    """Exclude a person (e.g. a staff member) from monitoring and automatic messages."""
    customer = await _customer_or_404(db, principal, customer_id)
    customer.is_excluded = body.excluded
    settings = await load_settings(db)
    ids = set(settings.monitor_excluded_user_ids)
    (ids.add if body.excluded else ids.discard)(customer.telegram_user_id)
    settings.monitor_excluded_user_ids = sorted(ids)
    await save_settings(db, settings, principal.admin.id)
    if body.excluded:
        conv_id = sa.select(Conversation.id).where(Conversation.customer_id == customer.id).scalar_subquery()
        await db.execute(
            sa.update(SlaIncident)
            .where(SlaIncident.conversation_id == conv_id, SlaIncident.status == IncidentStatus.OPEN)
            .values(
                status=IncidentStatus.DISMISSED,
                resolution=Resolution.DISMISSED,
                resolved_at=utcnow(),
                dismissed_by_admin_id=principal.admin.id,
                alert_status=sa.case(
                    (SlaIncident.alert_status.in_(["none", "pending"]), AlertStatus.SKIPPED),
                    else_=SlaIncident.alert_status,
                ),
            )
        )
    await audit(
        db,
        "customer.exclude" if body.excluded else "customer.include",
        actor=principal.admin,
        entity_type="customer",
        entity_id=customer.id,
        ip=client_ip(request),
    )
    return CustomerOut.model_validate(customer)


@router.delete("/customers/{customer_id}", response_model=OkResponse)
async def delete_customer(
    customer_id: int,
    request: Request,
    principal: Principal = Depends(require(Perm.SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    """Erase a customer's stored data (conversation, message metadata, incidents)."""
    customer = await _customer_or_404(db, principal, customer_id)
    tg_id = customer.telegram_user_id
    # Database-level ON DELETE CASCADE removes the conversation, message metadata and incidents.
    await db.execute(sa.delete(Customer).where(Customer.id == customer_id))
    await audit(
        db,
        "customer.delete",
        actor=principal.admin,
        entity_type="customer",
        entity_id=customer_id,
        details={"telegram_user_id": tg_id},
        ip=client_ip(request),
    )
    return OkResponse(message="Mijoz ma'lumotlari o'chirildi")


# ------------------------------------------------------------------------------- conversations
@router.get("/conversations", response_model=Page[ConversationOut])
async def list_conversations(
    principal: Principal = Depends(require(Perm.CONVERSATIONS_VIEW)),
    db: AsyncSession = Depends(get_db),
    status: Literal["all", "unresolved", "overdue", "resolved"] = "all",
    search: str | None = Query(default=None, max_length=100),
    assigned: Literal["me", "none"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[ConversationOut]:
    items, total = await q.list_conversations(
        db,
        principal,
        status=status,
        search=search,
        assigned=assigned,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: int,
    principal: Principal = Depends(require(Perm.CONVERSATIONS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    return await q.get_conversation(db, principal, conversation_id)


@router.get("/conversations/{conversation_id}/messages", response_model=Page[MessageOut])
async def conversation_messages(
    conversation_id: int,
    principal: Principal = Depends(require(Perm.CONVERSATIONS_VIEW)),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> Page[MessageOut]:
    await q.get_conversation(db, principal, conversation_id)  # access check
    base = sa.select(Message).where(Message.conversation_id == conversation_id)
    total = await db.scalar(sa.select(sa.func.count()).select_from(base.subquery())) or 0
    rows = (
        await db.scalars(
            base.order_by(Message.sent_at.desc(), Message.telegram_message_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(items=[MessageOut.model_validate(m) for m in rows], total=total, page=page, page_size=page_size)


@router.get("/conversations/{conversation_id}/outgoing", response_model=list[OutgoingOut])
async def conversation_outgoing(
    conversation_id: int,
    principal: Principal = Depends(require(Perm.CONVERSATIONS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[OutgoingOut]:
    await q.get_conversation(db, principal, conversation_id)
    rows = (
        await db.scalars(
            sa.select(OutgoingMessage)
            .where(OutgoingMessage.conversation_id == conversation_id)
            .order_by(OutgoingMessage.id.desc())
            .limit(20)
        )
    ).all()
    return [OutgoingOut.model_validate(r) for r in rows]


@router.post("/conversations/{conversation_id}/reply", response_model=OutgoingOut, status_code=202)
async def reply(
    conversation_id: int,
    body: ReplyRequest,
    request: Request,
    principal: Principal = Depends(require(Perm.CONVERSATIONS_REPLY)),
    db: AsyncSession = Depends(get_db),
) -> OutgoingOut:
    """Queue a reply. Status stays `queued` until the worker confirms Telegram accepted it."""
    conv = await q.get_conversation(db, principal, conversation_id)
    if conv.customer.is_excluded:
        raise ValidationAppError("Mijoz monitoringdan chiqarilgan")
    parsed = parse_message(body.text)
    if not parsed.ok:
        raise ValidationAppError("; ".join(parsed.errors), code="invalid_message")
    await enforce_rate_limit(db, f"reply:{principal.admin.id}", limit=30, window=timedelta(minutes=1))
    out = OutgoingMessage(
        conversation_id=conversation_id,
        text=body.text,
        requested_by_admin_id=principal.admin.id,
        status=OutboxStatus.QUEUED,
        next_attempt_at=utcnow(),
    )
    db.add(out)
    await db.flush()
    await audit(
        db,
        "conversation.reply_queued",
        actor=principal.admin,
        entity_type="conversation",
        entity_id=conversation_id,
        details={"outgoing_id": out.id},
        ip=client_ip(request),
    )
    await db.refresh(out)
    return OutgoingOut.model_validate(out)


@router.post("/conversations/{conversation_id}/assign", response_model=ConversationOut)
async def assign(
    conversation_id: int,
    body: AssignRequest,
    request: Request,
    principal: Principal = Depends(require(Perm.CONVERSATIONS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    """Admins assign to anyone; operators may only take an unassigned conversation for themselves."""
    await q.get_conversation(db, principal, conversation_id)
    conv = await db.get(Conversation, conversation_id, with_for_update=True)
    assert conv is not None
    if not principal.can(Perm.CONVERSATIONS_ASSIGN) and (
        body.admin_id != principal.admin.id or conv.assigned_admin_id not in (None, principal.admin.id)
    ):
        raise ValidationAppError("Operator faqat biriktirilmagan suhbatni o'ziga olishi mumkin")
    if body.admin_id is not None:
        target = await db.get(Admin, body.admin_id)
        if target is None or not target.is_active:
            raise ValidationAppError("Xodim topilmadi yoki faol emas")
    conv.assigned_admin_id = body.admin_id
    await audit(
        db,
        "conversation.assign",
        actor=principal.admin,
        entity_type="conversation",
        entity_id=conversation_id,
        details={"admin_id": body.admin_id},
        ip=client_ip(request),
    )
    await db.flush()
    return await q.get_conversation(db, principal, conversation_id)


# ------------------------------------------------------------------------------- incidents
@router.get("/incidents", response_model=Page[IncidentOut])
async def list_incidents(
    principal: Principal = Depends(require(Perm.CONVERSATIONS_VIEW)),
    db: AsyncSession = Depends(get_db),
    status: Literal["open", "overdue", "breached", "resolved", "dismissed", "all"] = "open",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[IncidentOut]:
    items, total = await q.list_incidents(db, principal, status=status, offset=(page - 1) * page_size, limit=page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/incidents/{incident_id}/dismiss", response_model=OkResponse)
async def dismiss_incident(
    incident_id: int,
    request: Request,
    principal: Principal = Depends(require(Perm.INCIDENTS_DISMISS)),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    """Close an incident that needs no reply (e.g. the customer only said "rahmat")."""
    inc = await q.get_incident_row(db, principal, incident_id)
    if inc.status != IncidentStatus.OPEN:
        raise ValidationAppError("Murojaat allaqachon yopilgan")
    now = utcnow()
    inc.status = IncidentStatus.DISMISSED
    inc.resolution = Resolution.DISMISSED
    inc.resolved_at = now
    inc.dismissed_by_admin_id = principal.admin.id
    if inc.alert_status in (AlertStatus.NONE, AlertStatus.PENDING):
        inc.alert_status = AlertStatus.SKIPPED
    await audit(
        db,
        "incident.dismiss",
        actor=principal.admin,
        entity_type="incident",
        entity_id=incident_id,
        ip=client_ip(request),
    )
    return OkResponse(message="Murojaat yopildi")


@router.get("/staff", response_model=list[dict])
async def assignable_staff(
    principal: Principal = Depends(require(Perm.CONVERSATIONS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = (
        await db.execute(
            sa.select(Admin.id, Admin.username, Admin.full_name, Admin.role)
            .where(Admin.is_active.is_(True), Admin.role.in_([Role.OPERATOR, Role.ADMIN, Role.SUPER_ADMIN]))
            .order_by(Admin.full_name, Admin.username)
        )
    ).all()
    return [{"id": i, "username": u, "full_name": f or u, "role": r} for i, u, f, r in rows]
