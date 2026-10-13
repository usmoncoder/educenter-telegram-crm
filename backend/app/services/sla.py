"""SLA breach detection and alert dispatch.

1. `mark_breaches` atomically moves open incidents whose deadline passed from alert_status
   NONE to PENDING (or SKIPPED when alerts are disabled) and records `breached_at`. A single
   UPDATE ... WHERE alert_status='none' makes the transition happen exactly once.
2. `dispatch_alerts` claims PENDING alerts with FOR UPDATE SKIP LOCKED, marks them SENDING
   (committed before the Telegram call), sends, and records SENT / retry / FAILED.
Incidents resolved before the alert is claimed are never alerted. Alerts interrupted by a
crash are marked FAILED (not re-sent) so an incident never produces duplicate alerts; the
incident itself stays visible as overdue on the dashboard.
"""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa

from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.enums import AlertStatus, IncidentStatus, MessageDirection
from app.db.models import Conversation, Customer, Message, SlaIncident
from app.db.session import SessionFactory, transaction
from app.services.app_settings import SettingsCache
from app.services.notifications import AlertNotifier, build_sla_alert
from app.services.sender import backoff_seconds
from app.telegram.types import SendError, SendErrorKind

log = get_logger(__name__)

MAX_ALERT_ATTEMPTS = 6


class SlaMonitor:
    def __init__(self, factory: SessionFactory, settings: SettingsCache, notifier: AlertNotifier) -> None:
        self._factory = factory
        self._settings = settings
        self._notifier = notifier

    async def recover_interrupted(self) -> int:
        async with transaction(self._factory) as s:
            res = await s.execute(
                sa.update(SlaIncident)
                .where(SlaIncident.alert_status == AlertStatus.SENDING)
                .values(
                    alert_status=AlertStatus.FAILED,
                    alert_error="Yuborish jarayonida worker to'xtadi; takroriy yuborilmaydi",
                )
            )
        return res.rowcount or 0

    async def mark_breaches(self) -> int:
        settings = await self._settings.get()
        now = utcnow()
        new_status = AlertStatus.PENDING if settings.alerts_enabled else AlertStatus.SKIPPED
        async with transaction(self._factory) as s:
            res = await s.execute(
                sa.update(SlaIncident)
                .where(
                    SlaIncident.status == IncidentStatus.OPEN,
                    SlaIncident.alert_status == AlertStatus.NONE,
                    SlaIncident.deadline_at <= now,
                )
                .values(
                    alert_status=new_status,
                    breached_at=SlaIncident.deadline_at,
                    alert_next_attempt_at=now,
                    updated_at=now,
                )
            )
        if res.rowcount:
            log.info("sla_breaches_detected", count=res.rowcount, alerts=settings.alerts_enabled)
        return res.rowcount or 0

    async def _claim(self, limit: int) -> list[int]:
        async with transaction(self._factory) as s:
            ids = (
                await s.scalars(
                    sa.select(SlaIncident.id)
                    .where(
                        SlaIncident.status == IncidentStatus.OPEN,
                        SlaIncident.alert_status == AlertStatus.PENDING,
                        SlaIncident.alert_next_attempt_at <= utcnow(),
                    )
                    .order_by(SlaIncident.deadline_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if ids:
                await s.execute(
                    sa.update(SlaIncident)
                    .where(SlaIncident.id.in_(ids))
                    .values(alert_status=AlertStatus.SENDING, alert_attempts=SlaIncident.alert_attempts + 1)
                )
        return list(ids)

    async def dispatch_alerts(self, limit: int = 20) -> int:
        sent = 0
        for incident_id in await self._claim(limit):
            if await self._send_one(incident_id):
                sent += 1
        return sent

    async def _send_one(self, incident_id: int) -> bool:
        settings = await self._settings.get()
        async with self._factory() as s:
            row = (
                await s.execute(
                    sa.select(SlaIncident, Customer)
                    .join(Conversation, Conversation.id == SlaIncident.conversation_id)
                    .join(Customer, Customer.id == Conversation.customer_id)
                    .where(SlaIncident.id == incident_id)
                )
            ).one_or_none()
            if row is None:
                return False
            incident, customer = row
            preview = await s.scalar(
                sa.select(Message.text_preview).where(
                    Message.conversation_id == incident.conversation_id,
                    Message.telegram_message_id == incident.first_telegram_message_id,
                    Message.direction == MessageDirection.IN,
                )
            )
        text = build_sla_alert(
            customer_name=customer.display_name,
            username=customer.username,
            telegram_user_id=customer.telegram_user_id,
            started_at=incident.started_at,
            message_count=incident.customer_message_count,
            preview=preview,
            include_preview=settings.alert_include_preview,
        )
        now = utcnow()
        try:
            await self._notifier.send(settings, text)
        except SendError as exc:
            values: dict[str, object] = {"alert_error": exc.message[:500]}
            if exc.kind == SendErrorKind.FLOOD:
                values.update(
                    alert_status=AlertStatus.PENDING,
                    alert_attempts=SlaIncident.alert_attempts - 1,
                    alert_next_attempt_at=now + timedelta(seconds=exc.retry_after or 60),
                )
            elif exc.kind in (SendErrorKind.TRANSIENT, SendErrorKind.UNAUTHORIZED) and (
                incident.alert_attempts < MAX_ALERT_ATTEMPTS
            ):
                values.update(
                    alert_status=AlertStatus.PENDING,
                    alert_next_attempt_at=now
                    + timedelta(seconds=exc.retry_after or backoff_seconds(incident.alert_attempts)),
                )
            else:
                values.update(alert_status=AlertStatus.FAILED)
            async with transaction(self._factory) as s:
                await s.execute(sa.update(SlaIncident).where(SlaIncident.id == incident_id).values(**values))
            log.warning("sla_alert_failed", incident_id=incident_id, kind=exc.kind, code=exc.code)
            return False
        async with transaction(self._factory) as s:
            await s.execute(
                sa.update(SlaIncident)
                .where(SlaIncident.id == incident_id)
                .values(alert_status=AlertStatus.SENT, alerted_at=now, alert_error=None)
            )
        log.info("sla_alert_sent", incident_id=incident_id)
        return True
