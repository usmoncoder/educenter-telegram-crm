"""Read models for customers, conversations and incidents, including operator scoping."""

from __future__ import annotations

from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import Principal
from app.core.errors import NotFoundError
from app.core.permissions import Perm
from app.core.timeutil import utcnow
from app.db.enums import IncidentStatus, MessageDirection
from app.db.models import Admin, Conversation, Customer, Message, SlaIncident
from app.schemas.api import ConversationOut, CustomerOut, IncidentOut
from app.services.app_settings import load_settings

OpenIncident = aliased(SlaIncident, name="open_incident")


async def conversation_scope(db: AsyncSession, principal: Principal) -> sa.ColumnElement[bool]:
    """SQL predicate restricting conversations to what the principal may see."""
    if principal.can(Perm.CONVERSATIONS_VIEW_ALL):
        return sa.true()
    settings = await load_settings(db)
    mine = Conversation.assigned_admin_id == principal.admin.id
    if settings.operators_see_unassigned:
        return sa.or_(mine, Conversation.assigned_admin_id.is_(None))
    return mine


def search_clause(search: str) -> sa.ColumnElement[bool]:
    term = search.strip().lstrip("@")
    like = f"%{term.replace('%', r'\%').replace('_', r'\_')}%"
    clauses: list[sa.ColumnElement[bool]] = [
        Customer.username.ilike(like),
        Customer.first_name.ilike(like),
        Customer.last_name.ilike(like),
        sa.func.concat_ws(" ", Customer.first_name, Customer.last_name).ilike(like),
    ]
    if term.isdigit():
        clauses.append(Customer.telegram_user_id == int(term))
    return sa.or_(*clauses)


def customer_out(c: Customer) -> CustomerOut:
    return CustomerOut.model_validate(c)


def _conversation_out(conv: Conversation, customer: Customer, incident: SlaIncident | None, admin_name: str | None):
    now = utcnow()
    state: Literal["ok", "waiting", "overdue"] = "ok"
    if incident is not None:
        state = "overdue" if incident.deadline_at <= now else "waiting"
    return ConversationOut(
        id=conv.id,
        customer=customer_out(customer),
        assigned_admin_id=conv.assigned_admin_id,
        assigned_admin_name=admin_name,
        last_message_at=conv.last_message_at,
        last_incoming_at=conv.last_incoming_at,
        last_outgoing_at=conv.last_outgoing_at,
        last_human_reply_at=conv.last_human_reply_at,
        last_message_preview=conv.last_message_preview,
        last_message_direction=conv.last_message_direction,
        sla_state=state,
        open_incident_id=incident.id if incident else None,
        waiting_since=incident.started_at if incident else None,
        deadline_at=incident.deadline_at if incident else None,
    )


def _base_conversation_query() -> sa.Select[Any]:
    return (
        sa.select(Conversation, Customer, OpenIncident, Admin.full_name, Admin.username)
        .join(Customer, Customer.id == Conversation.customer_id)
        .outerjoin(
            OpenIncident,
            sa.and_(OpenIncident.conversation_id == Conversation.id, OpenIncident.status == IncidentStatus.OPEN),
        )
        .outerjoin(Admin, Admin.id == Conversation.assigned_admin_id)
    )


async def list_conversations(
    db: AsyncSession,
    principal: Principal,
    *,
    status: str = "all",
    search: str | None = None,
    assigned: str | None = None,
    offset: int = 0,
    limit: int = 25,
) -> tuple[list[ConversationOut], int]:
    q = _base_conversation_query().where(await conversation_scope(db, principal))
    now = utcnow()
    if status == "unresolved":
        q = q.where(OpenIncident.id.is_not(None))
    elif status == "overdue":
        q = q.where(OpenIncident.id.is_not(None), OpenIncident.deadline_at <= now)
    elif status == "resolved":
        q = q.where(OpenIncident.id.is_(None))
    if search:
        q = q.where(search_clause(search))
    if assigned == "me":
        q = q.where(Conversation.assigned_admin_id == principal.admin.id)
    elif assigned == "none":
        q = q.where(Conversation.assigned_admin_id.is_(None))
    total = await db.scalar(sa.select(sa.func.count()).select_from(q.subquery())) or 0
    order = (
        [OpenIncident.started_at.asc().nulls_last(), Conversation.last_message_at.desc().nulls_last()]
        if status in ("unresolved", "overdue")
        else [Conversation.last_message_at.desc().nulls_last()]
    )
    rows = (await db.execute(q.order_by(*order, Conversation.id.desc()).offset(offset).limit(limit))).all()
    return [_conversation_out(c, cu, inc, fn or un) for c, cu, inc, fn, un in rows], int(total)


async def get_conversation(db: AsyncSession, principal: Principal, conversation_id: int) -> ConversationOut:
    q = _base_conversation_query().where(Conversation.id == conversation_id, await conversation_scope(db, principal))
    row = (await db.execute(q)).one_or_none()
    if row is None:
        raise NotFoundError("Suhbat topilmadi")
    c, cu, inc, fn, un = row
    return _conversation_out(c, cu, inc, fn or un)


async def conversation_for_customer(db: AsyncSession, principal: Principal, customer_id: int) -> ConversationOut | None:
    q = _base_conversation_query().where(
        Conversation.customer_id == customer_id, await conversation_scope(db, principal)
    )
    row = (await db.execute(q)).one_or_none()
    if row is None:
        return None
    c, cu, inc, fn, un = row
    return _conversation_out(c, cu, inc, fn or un)


def _incident_query() -> sa.Select[Any]:
    first_preview = (
        sa.select(Message.text_preview)
        .where(
            Message.conversation_id == SlaIncident.conversation_id,
            Message.telegram_message_id == SlaIncident.first_telegram_message_id,
            Message.direction == MessageDirection.IN,
        )
        .limit(1)
        .scalar_subquery()
    )
    return (
        sa.select(SlaIncident, Customer, first_preview.label("preview"))
        .join(Conversation, Conversation.id == SlaIncident.conversation_id)
        .join(Customer, Customer.id == Conversation.customer_id)
    )


def _incident_out(inc: SlaIncident, cu: Customer, preview: str | None) -> IncidentOut:
    return IncidentOut(
        id=inc.id,
        conversation_id=inc.conversation_id,
        customer=customer_out(cu),
        status=inc.status,
        started_at=inc.started_at,
        last_customer_message_at=inc.last_customer_message_at,
        customer_message_count=inc.customer_message_count,
        deadline_at=inc.deadline_at,
        breached_at=inc.breached_at,
        alert_status=inc.alert_status,
        alerted_at=inc.alerted_at,
        alert_error=inc.alert_error,
        resolved_at=inc.resolved_at,
        resolution=inc.resolution,
        response_seconds=inc.response_seconds,
        first_message_preview=preview,
        overdue=inc.status == IncidentStatus.OPEN and inc.deadline_at <= utcnow(),
    )


async def list_incidents(
    db: AsyncSession,
    principal: Principal,
    *,
    status: str = "open",
    offset: int = 0,
    limit: int = 25,
    conversation_id: int | None = None,
) -> tuple[list[IncidentOut], int]:
    q = _incident_query().where(await conversation_scope(db, principal))
    now = utcnow()
    if status == "open":
        q = q.where(SlaIncident.status == IncidentStatus.OPEN)
    elif status == "overdue":
        q = q.where(SlaIncident.status == IncidentStatus.OPEN, SlaIncident.deadline_at <= now)
    elif status == "breached":
        q = q.where(SlaIncident.breached_at.is_not(None))
    elif status in ("resolved", "dismissed"):
        q = q.where(SlaIncident.status == IncidentStatus(status))
    if conversation_id is not None:
        q = q.where(SlaIncident.conversation_id == conversation_id)
    total = await db.scalar(sa.select(sa.func.count()).select_from(q.subquery())) or 0
    order = SlaIncident.started_at.asc() if status in ("open", "overdue") else SlaIncident.started_at.desc()
    rows = (await db.execute(q.order_by(order, SlaIncident.id.desc()).offset(offset).limit(limit))).all()
    return [_incident_out(i, c, p) for i, c, p in rows], int(total)


async def get_incident_row(db: AsyncSession, principal: Principal, incident_id: int) -> SlaIncident:
    inc = await db.scalar(
        sa.select(SlaIncident)
        .join(Conversation, Conversation.id == SlaIncident.conversation_id)
        .where(SlaIncident.id == incident_id, await conversation_scope(db, principal))
        .with_for_update(of=SlaIncident)
    )
    if inc is None:
        raise NotFoundError("Murojaat topilmadi")
    return inc
