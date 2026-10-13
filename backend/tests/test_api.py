"""API integration tests: authentication, CSRF, RBAC, validation and real metrics."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import sqlalchemy as sa

from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.db.enums import GroupKind, GroupSource, OutboxStatus, Role
from app.db.models import Admin, AuditEvent, Conversation, Customer, Message, SlaIncident, TelegramGroup
from app.db.session import transaction
from app.main import create_app
from app.services.inbox import InboxService
from tests.conftest import TgUser, tg_msg

PASSWORD = "Test-Passw0rd!x"


@pytest.fixture
async def app(factory, settings):
    application = create_app(settings)
    application.state.session_factory = factory
    return application


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def make_admin(factory, username: str, role: Role) -> int:
    async with transaction(factory) as s:
        a = Admin(username=username, full_name=username.title(), role=role, password_hash=hash_password(PASSWORD))
        s.add(a)
        await s.flush()
        return a.id


async def login(client: httpx.AsyncClient, username: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


async def test_login_logout_and_session(client, factory):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    assert (await client.get("/api/auth/me")).status_code == 401
    csrf = await login(client, "boss")
    assert client.cookies.get("educrm_session")
    me = (await client.get("/api/auth/me")).json()
    assert me["admin"]["role"] == "super_admin" and "settings.manage" in me["permissions"]
    r = await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    client.cookies.clear()
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_lockout_after_repeated_failures(client, factory):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    for _ in range(5):
        r = await client.post("/api/auth/login", json={"username": "boss", "password": "nope"})
        assert r.status_code == 401
        assert r.json()["error"]["message"] == "Login yoki parol noto'g'ri"
    r = await client.post("/api/auth/login", json={"username": "boss", "password": PASSWORD})
    assert r.status_code == 429  # locked even with the right password


async def test_unknown_user_gets_same_error(client):
    r = await client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


async def test_csrf_and_origin_are_enforced(client, factory):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    csrf = await login(client, "boss")
    assert (await client.post("/api/groups/sync")).status_code == 403
    assert (await client.post("/api/groups/sync", headers={"X-CSRF-Token": "wrong"})).status_code == 403
    bad = await client.post("/api/groups/sync", headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"})
    assert bad.status_code == 403 and bad.json()["error"]["code"] == "bad_origin"
    ok = await client.post("/api/groups/sync", headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 202 and ok.json()["status"] == "pending"
    again = await client.post("/api/groups/sync", headers={"X-CSRF-Token": csrf})
    assert again.json()["id"] == ok.json()["id"]  # identical pending command is not duplicated


async def test_role_based_access(client, factory):
    await make_admin(factory, "op", Role.OPERATOR)
    await login(client, "op")
    for path in (
        "/api/settings",
        "/api/admins",
        "/api/campaigns",
        "/api/groups",
        "/api/audit",
        "/api/autoreply",
        "/api/reports",
        "/api/history/deliveries",
    ):
        assert (await client.get(path)).status_code == 403, path
    for path in ("/api/dashboard", "/api/conversations", "/api/incidents", "/api/customers", "/api/telegram/status"):
        assert (await client.get(path)).status_code == 200, path


async def test_admin_cannot_manage_admins_or_settings(client, factory):
    await make_admin(factory, "mgr", Role.ADMIN)
    csrf = await login(client, "mgr")
    assert (await client.get("/api/campaigns")).status_code == 200
    assert (await client.get("/api/admins")).status_code == 403
    r = await client.put("/api/settings", json={"sla_timeout_minutes": 10}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403


async def seed_conversations(factory, settings_cache, sender, op_id: int | None, other_id: int | None):
    inbox = InboxService(factory, settings_cache, sender)
    users = [TgUser(id=501, first_name="Mine"), TgUser(id=502, first_name="Free"), TgUser(id=503, first_name="Other")]
    for i, u in enumerate(users):
        await inbox.handle(tg_msg(100 + i, user=u, minutes_ago=10))
    async with transaction(factory) as s:
        convs = {
            c.customer.first_name: c
            for c in (
                await s.scalars(sa.select(Conversation).options(sa.orm.selectinload(Conversation.customer)))
            ).all()
        }
        convs["Mine"].assigned_admin_id = op_id
        convs["Other"].assigned_admin_id = other_id
        return {k: v.id for k, v in convs.items()}


async def test_operator_sees_only_assigned_or_unassigned(client, factory, settings_cache, sender):
    op = await make_admin(factory, "op", Role.OPERATOR)
    other = await make_admin(factory, "op2", Role.OPERATOR)
    ids = await seed_conversations(factory, settings_cache, sender, op, other)
    csrf = await login(client, "op")
    names = {c["customer"]["first_name"] for c in (await client.get("/api/conversations")).json()["items"]}
    assert names == {"Mine", "Free"}
    assert (await client.get(f"/api/conversations/{ids['Other']}")).status_code == 404
    r = await client.post(
        f"/api/conversations/{ids['Other']}/reply", json={"text": "x"}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 404
    # Operators may take an unassigned conversation, but not reassign others'.
    r = await client.post(
        f"/api/conversations/{ids['Free']}/assign", json={"admin_id": op}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200 and r.json()["assigned_admin_id"] == op
    r = await client.post(
        f"/api/conversations/{ids['Free']}/assign", json={"admin_id": other}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 422
    incidents = (await client.get("/api/incidents?status=overdue")).json()
    assert {i["customer"]["first_name"] for i in incidents["items"]} == {"Mine", "Free"}


async def test_reply_is_queued_not_reported_as_sent(client, factory, settings_cache, sender):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    ids = await seed_conversations(factory, settings_cache, sender, None, None)
    csrf = await login(client, "boss")
    bad = await client.post(
        f"/api/conversations/{ids['Mine']}/reply", json={"text": "<b>x"}, headers={"X-CSRF-Token": csrf}
    )
    assert bad.status_code == 422
    r = await client.post(
        f"/api/conversations/{ids['Mine']}/reply", json={"text": "Javob <b>tayyor</b>"}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 202 and r.json()["status"] == OutboxStatus.QUEUED


async def test_admin_management_rules(client, factory):
    boss = await make_admin(factory, "boss", Role.SUPER_ADMIN)
    csrf = await login(client, "boss")
    h = {"X-CSRF-Token": csrf}
    weak = await client.post(
        "/api/admins", json={"username": "new_op", "role": "operator", "password": "123"}, headers=h
    )
    assert weak.status_code == 422
    ok = await client.post(
        "/api/admins",
        json={"username": "New_Op", "full_name": "Yangi", "role": "operator", "password": "Operator-Pass9!"},
        headers=h,
    )
    assert ok.status_code == 201 and ok.json()["username"] == "new_op"
    dup = await client.post(
        "/api/admins", json={"username": "new_op", "role": "operator", "password": "Operator-Pass9!"}, headers=h
    )
    assert dup.status_code == 409
    last = await client.patch(f"/api/admins/{boss}", json={"role": "admin"}, headers=h)
    assert last.status_code == 409  # cannot remove the last super admin
    async with factory() as s:
        actions = set((await s.scalars(sa.select(AuditEvent.action))).all())
    assert {"auth.login", "admin.create"} <= actions


async def test_settings_validation_and_audit(client, factory):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    h = {"X-CSRF-Token": await login(client, "boss")}
    assert (await client.put("/api/settings", json={"bogus": 1}, headers=h)).status_code == 422
    assert (await client.put("/api/settings", json={"sla_timeout_minutes": 0}, headers=h)).status_code == 422
    r = await client.put("/api/settings", json={"sla_timeout_minutes": 7, "alert_chat": "me"}, headers=h)
    assert r.status_code == 200 and r.json()["sla_timeout_minutes"] == 7
    bad = await client.put(
        "/api/autoreply",
        json={
            "welcome_enabled": True,
            "welcome_text": "<b>yopilmagan",
            "welcome_delay_seconds": 0,
            "welcome_only_new_chats": True,
            "welcome_link_preview": False,
            "welcome_excluded_user_ids": [],
        },
        headers=h,
    )
    assert bad.status_code == 422 and "yopilmagan" in bad.json()["error"]["message"]
    good = await client.put(
        "/api/autoreply",
        json={
            "welcome_enabled": True,
            "welcome_text": "<b>Xush kelibsiz!</b>",
            "welcome_delay_seconds": 5,
            "welcome_only_new_chats": True,
            "welcome_link_preview": False,
            "welcome_excluded_user_ids": [42],
        },
        headers=h,
    )
    assert good.status_code == 200 and good.json()["welcome_enabled"]
    p = await client.post("/api/messages/preview", json={"text": "<i>salom</i>"}, headers=h)
    assert p.json()["entities"] == [{"type": "italic", "offset": 0, "length": 5}]


async def test_dashboard_metrics_come_from_records(client, factory, settings_cache, sender):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    inbox = InboxService(factory, settings_cache, sender)
    await inbox.handle(tg_msg(1, user=TgUser(id=601, first_name="A"), minutes_ago=10))  # overdue
    await inbox.handle(tg_msg(2, user=TgUser(id=602, first_name="B"), minutes_ago=2))  # waiting
    await inbox.handle(tg_msg(3, user=TgUser(id=603, first_name="C"), minutes_ago=3))
    await inbox.handle(tg_msg(4, user=TgUser(id=603, first_name="C"), outgoing=True, text="javob", minutes_ago=2))
    await login(client, "boss")
    d = (await client.get("/api/dashboard")).json()
    m = d["metrics"]
    assert m["total_customers"] == 3 and m["new_customers_today"] >= 1
    assert m["unanswered"] == 2 and m["overdue"] == 1
    assert 55 <= m["avg_response_seconds_30d"] <= 65
    assert sum(b["count"] for b in d["distribution_30d"]) == 1
    assert [i["customer"]["first_name"] for i in d["waiting_incidents"]] == ["A", "B"]  # oldest first
    assert [i["overdue"] for i in d["waiting_incidents"]] == [True, False]
    rep = (await client.get("/api/reports")).json()
    assert rep["totals"]["incidents"] == 3 and rep["totals"]["answered"] == 1


async def test_campaign_api_flow_with_confirmation(client, factory):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    async with transaction(factory) as s:
        for i in range(2):
            s.add(
                TelegramGroup(
                    telegram_id=-1007000 - i,
                    title=f"G{i}",
                    kind=GroupKind.SUPERGROUP,
                    source=GroupSource.DISCOVERED,
                    can_send=True,
                    is_member=True,
                    is_enabled=True,
                )
            )
    h = {"X-CSRF-Token": await login(client, "boss")}
    groups = (await client.get("/api/groups")).json()
    body = {
        "title": "Qabul",
        "default_text": "<b>Yangi guruh</b>",
        "schedule_type": "weekly",
        "time_of_day": "09:00",
        "weekdays": [0, 3],
        "targets": [{"group_id": g["id"]} for g in groups],
    }
    c = await client.post("/api/campaigns", json=body, headers=h)
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    r = await client.post(f"/api/campaigns/{cid}/activate", json={"confirm": False}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "confirmation_required"
    r = await client.post(f"/api/campaigns/{cid}/activate", json={"confirm": True}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "scheduled" and r.json()["next_run_at"]
    assert (await client.post(f"/api/campaigns/{cid}/pause", headers=h)).json()["status"] == "paused"
    assert (await client.post(f"/api/campaigns/{cid}/resume", headers=h)).json()["status"] == "scheduled"
    assert (await client.post(f"/api/campaigns/{cid}/cancel", headers=h)).json()["status"] == "cancelled"
    assert (await client.put(f"/api/campaigns/{cid}", json=body, headers=h)).status_code == 409
    bad = dict(body, schedule_type="weekly", weekdays=[])
    assert (await client.post("/api/campaigns", json=bad, headers=h)).status_code == 422


async def test_customer_exclusion_and_erasure(client, factory, settings_cache, sender):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    inbox = InboxService(factory, settings_cache, sender)
    await inbox.handle(tg_msg(1, user=TgUser(id=701, first_name="Xodim"), minutes_ago=1))
    h = {"X-CSRF-Token": await login(client, "boss")}
    cid = (await client.get("/api/customers")).json()["items"][0]["id"]
    r = await client.post(f"/api/customers/{cid}/exclude", json={"excluded": True}, headers=h)
    assert r.status_code == 200 and r.json()["is_excluded"]
    assert (await client.get("/api/incidents")).json()["total"] == 0  # open incident dismissed
    assert 701 in (await client.get("/api/settings")).json()["monitor_excluded_user_ids"]
    assert (await client.delete(f"/api/customers/{cid}", headers=h)).status_code == 200
    async with factory() as s:
        for model in (Customer, Conversation, Message, SlaIncident):
            assert await s.scalar(sa.select(sa.func.count()).select_from(model)) == 0


async def test_expired_session_rejected(client, factory):
    await make_admin(factory, "boss", Role.SUPER_ADMIN)
    await login(client, "boss")
    async with factory() as s, s.begin():
        from app.db.models import AdminSession

        await s.execute(sa.update(AdminSession).values(expires_at=utcnow() - timedelta(seconds=1)))
    r = await client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_expired"


async def test_health_endpoints_expose_nothing_sensitive(client):
    r = await client.get("/api/health/ready")
    assert r.json() == {"status": "ok", "database": "up"}
