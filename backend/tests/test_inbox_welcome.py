"""First-contact detection, duplicate prevention and human-reply classification."""

from __future__ import annotations

import sqlalchemy as sa

from app.db.enums import IncidentStatus, MessageSource, Resolution, SenderType, WelcomeStatus
from app.db.models import Customer, Message, SlaIncident
from app.services.inbox import InboxService, IngestOutcome
from app.services.welcome import WelcomeDispatcher
from app.telegram.types import SendError, SendErrorKind, TgUser
from tests.conftest import CUSTOMER, set_runtime, tg_msg

WELCOME = "<b>EduCenter</b>ga xush kelibsiz! Kurslar: IELTS, IT."


async def _setup(factory, settings_cache, sender, gateway, **runtime):
    await set_runtime(factory, welcome_enabled=True, welcome_text=WELCOME, **runtime)
    inbox = InboxService(factory, settings_cache, sender)
    welcome = WelcomeDispatcher(factory, settings_cache, sender, gateway)
    return inbox, welcome


async def _one(factory, model, *where):
    async with factory() as s:
        return (await s.scalars(sa.select(model).where(*where))).all()


async def test_first_message_creates_customer_incident_and_queues_welcome(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway)
    res = await inbox.handle(tg_msg(10))
    assert res.outcome == IngestOutcome.INCOMING and res.new_customer
    [customer] = await _one(factory, Customer)
    assert customer.telegram_user_id == CUSTOMER.id
    assert customer.welcome_status == WelcomeStatus.PENDING
    [incident] = await _one(factory, SlaIncident)
    assert incident.status == IncidentStatus.OPEN
    assert (incident.deadline_at - incident.started_at).total_seconds() == 300


async def test_welcome_sent_exactly_once(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10))
    assert await welcome.run_once() == 1
    assert await welcome.run_once() == 0  # nothing left to claim
    # Customer writes again: no second welcome.
    await inbox.handle(tg_msg(11))
    assert await welcome.run_once() == 0
    # A restarted dispatcher (new instance) does not resend either.
    assert await WelcomeDispatcher(factory, settings_cache, sender, gateway).run_once() == 0
    assert [html for _, html in gateway.sent] == [WELCOME]
    [customer] = await _one(factory, Customer)
    assert customer.welcome_status == WelcomeStatus.SENT
    [auto] = await _one(factory, Message, Message.source == MessageSource.WELCOME)
    assert auto.sender_type == SenderType.AUTOMATION and not auto.counts_as_reply


async def test_duplicate_events_are_idempotent(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway)
    assert (await inbox.handle(tg_msg(10))).outcome == IngestOutcome.INCOMING
    assert (await inbox.handle(tg_msg(10))).outcome == IngestOutcome.DUPLICATE
    [incident] = await _one(factory, SlaIncident)
    assert incident.customer_message_count == 1
    assert len(await _one(factory, Message)) == 1


async def test_automated_welcome_does_not_count_as_human_reply(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10, minutes_ago=1))
    await welcome.run_once()
    welcome_id = gateway.next_id
    # Telegram later delivers the update for our own welcome message: must be recognized.
    res = await inbox.handle(tg_msg(welcome_id, outgoing=True, text="EduCenterga xush kelibsiz! Kurslar: IELTS, IT."))
    assert res.outcome == IngestOutcome.DUPLICATE
    [incident] = await _one(factory, SlaIncident)
    assert incident.status == IncidentStatus.OPEN


async def test_outgoing_copy_of_template_and_business_bot_are_automation(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10, minutes_ago=2))
    res1 = await inbox.handle(tg_msg(11, outgoing=True, text="EduCenterga xush kelibsiz! Kurslar: IELTS, IT."))
    res2 = await inbox.handle(tg_msg(12, outgoing=True, text="Auto away message", via_business_bot=True))
    assert res1.outcome == res2.outcome == IngestOutcome.AUTOMATED
    [incident] = await _one(factory, SlaIncident)
    assert incident.status == IncidentStatus.OPEN


async def test_human_reply_resolves_incident(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10, minutes_ago=3))
    res = await inbox.handle(tg_msg(11, outgoing=True, text="Assalomu alaykum! Qaysi kurs qiziqtiradi?"))
    assert res.outcome == IngestOutcome.HUMAN_REPLY
    [incident] = await _one(factory, SlaIncident)
    assert incident.status == IncidentStatus.RESOLVED
    assert incident.resolution == Resolution.HUMAN_REPLY
    assert 170 <= incident.response_seconds <= 190
    assert incident.breached_at is None


async def test_reply_older_than_incident_does_not_resolve(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(20, minutes_ago=1))
    # Out-of-order delivery of an operator message with a lower id (sent before the question).
    await inbox.handle(tg_msg(19, outgoing=True, text="old", minutes_ago=2))
    [incident] = await _one(factory, SlaIncident)
    assert incident.status == IncidentStatus.OPEN


async def test_multiple_customer_messages_keep_first_deadline(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10, minutes_ago=4))
    await inbox.handle(tg_msg(11, minutes_ago=1))
    await inbox.handle(tg_msg(12, minutes_ago=0))
    [incident] = await _one(factory, SlaIncident)
    assert incident.customer_message_count == 3
    assert incident.first_telegram_message_id == 10
    assert (incident.deadline_at - incident.started_at).total_seconds() == 300
    # One reply closes the whole waiting cycle; the next question opens a new incident.
    await inbox.handle(tg_msg(13, outgoing=True, text="Javob"))
    await inbox.handle(tg_msg(14))
    incidents = await _one(factory, SlaIncident)
    assert sorted(i.status for i in incidents) == [IncidentStatus.OPEN, IncidentStatus.RESOLVED]


async def test_forwarded_outgoing_not_a_reply_by_default(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10, minutes_ago=1))
    res = await inbox.handle(tg_msg(11, outgoing=True, text="price list", is_forwarded=True))
    assert res.outcome == IngestOutcome.NOT_A_REPLY
    assert (await _one(factory, SlaIncident))[0].status == IncidentStatus.OPEN
    await set_runtime(factory, count_forwarded_as_reply=True)
    res = await inbox.handle(tg_msg(12, outgoing=True, text="price list", is_forwarded=True))
    assert res.outcome == IngestOutcome.HUMAN_REPLY


async def test_service_bots_contacts_and_exclusions_are_ignored(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway, monitor_excluded_user_ids=[333])
    bot = TgUser(id=222, username="somebot", is_bot=True)
    contact = TgUser(id=444, first_name="Opa", is_contact=True)
    excluded = TgUser(id=333, first_name="Staff")
    assert (await inbox.handle(tg_msg(1, user=bot))).outcome == IngestOutcome.IGNORED
    assert (await inbox.handle(tg_msg(2, user=contact))).outcome == IngestOutcome.IGNORED
    assert (await inbox.handle(tg_msg(3, user=excluded))).outcome == IngestOutcome.IGNORED
    assert (await inbox.handle(tg_msg(4, is_service=True))).outcome == IngestOutcome.IGNORED
    assert (await inbox.handle(tg_msg(5, outgoing=True, user=TgUser(id=999)))).outcome == IngestOutcome.IGNORED
    assert await _one(factory, Customer) == []


async def test_existing_chat_history_is_not_greeted(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway)
    gateway.users_with_history.add(CUSTOMER.id)
    await inbox.handle(tg_msg(10))
    await welcome.run_once()
    assert gateway.sent == []
    [customer] = await _one(factory, Customer)
    assert customer.welcome_status == WelcomeStatus.EXISTING


async def test_welcome_skipped_when_operator_answers_during_delay(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway, welcome_delay_seconds=0)
    await inbox.handle(tg_msg(10, minutes_ago=1))
    await inbox.handle(tg_msg(11, outgoing=True, text="Salom!"))
    await welcome.run_once()
    assert gateway.sent == []
    assert (await _one(factory, Customer))[0].welcome_status == WelcomeStatus.NOT_APPLICABLE


async def test_welcome_delay_is_respected(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway, welcome_delay_seconds=600)
    await inbox.handle(tg_msg(10))
    assert await welcome.run_once() == 0
    assert gateway.sent == []


async def test_welcome_disabled_or_excluded(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway, welcome_excluded_user_ids=[CUSTOMER.id])
    await inbox.handle(tg_msg(10))
    await welcome.run_once()
    assert gateway.sent == []
    assert (await _one(factory, Customer))[0].welcome_status == WelcomeStatus.NOT_APPLICABLE


async def test_welcome_flood_wait_postpones_without_consuming_attempt(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10))
    gateway.errors.append(SendError(SendErrorKind.FLOOD, "flood_wait", "wait", retry_after=120))
    await welcome.run_once()
    [c] = await _one(factory, Customer)
    assert c.welcome_status == WelcomeStatus.PENDING
    assert c.welcome_attempts == 0
    assert gateway.sent == []


async def test_welcome_permanent_error_marks_failed(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10))
    gateway.errors.append(SendError(SendErrorKind.PERMANENT, "UserIsBlockedError", "blocked"))
    await welcome.run_once()
    [c] = await _one(factory, Customer)
    assert c.welcome_status == WelcomeStatus.FAILED and c.welcome_error == "blocked"


async def test_interrupted_welcome_is_never_resent(factory, settings_cache, sender, gateway):
    inbox, welcome = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10))
    async with factory() as s, s.begin():
        await s.execute(sa.update(Customer).values(welcome_status=WelcomeStatus.SENDING))  # simulated crash
    assert await welcome.recover_interrupted() == 1
    assert await welcome.run_once() == 0
    assert (await _one(factory, Customer))[0].welcome_status == WelcomeStatus.UNKNOWN
    assert gateway.sent == []


async def test_edit_and_delete_do_not_affect_sla(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway)
    await inbox.handle(tg_msg(10, minutes_ago=1, text="birinchi"))
    await inbox.mark_edited(tg_msg(10, text="tahrirlangan"))
    assert await inbox.mark_deleted([10]) == 1
    [m] = await _one(factory, Message)
    assert m.edited_at is not None and m.deleted_at is not None and m.text_preview == "tahrirlangan"
    assert (await _one(factory, SlaIncident))[0].status == IncidentStatus.OPEN


async def test_message_text_not_stored_when_disabled(factory, settings_cache, sender, gateway):
    inbox, _ = await _setup(factory, settings_cache, sender, gateway, store_message_text=False)
    await inbox.handle(tg_msg(10, text="maxfiy matn"))
    [m] = await _one(factory, Message)
    assert m.text_preview is None
