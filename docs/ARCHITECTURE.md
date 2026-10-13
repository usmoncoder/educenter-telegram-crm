# Architecture and design decisions

Developer documentation (English). The operator-facing guide is the Uzbek `README.md`.

## Processes

| Process | Entry point | Owns |
|---|---|---|
| API | `uvicorn app.main:app` | HTTP, auth, RBAC, CRUD, reports. Never connects to Telegram. |
| Worker | `python -m app.workers.main` | The single Telethon connection and all background loops. |
| Migrations | `alembic upgrade head` | Schema. |
| CLI | `python -m app.cli`, `python -m app.telegram.auth_cli` | First admin, password reset, Telegram login. |

The API and the worker communicate **only through PostgreSQL**:

- API → worker: `worker_commands` (sync groups, resolve a group, reconnect, test alert),
  `outgoing_messages` (panel replies), `announcement_campaigns` (schedules), `app_settings`.
- Worker → API: `worker_state` (status + heartbeat), `connection_events`, and the domain tables.

Consequences: the API never holds Telegram credentials or the session; any UI action that
involves Telegram is asynchronous and shows a *real* result once the worker reports it.

## Code layout

```
backend/app/
  core/          config (env), logging (redaction), security (Argon2id, tokens), permissions, time
  db/            models, enums, session helpers, Alembic migrations
  schemas/       Pydantic request/response models
  services/      domain logic (Telethon-free, unit-testable)
    inbox.py           ingest private messages, classify replies, open/resolve SLA incidents
    welcome.py         first-contact message dispatcher
    sla.py             breach detection + alert dispatcher
    notifications.py   alert transports (userbot / Bot API) and alert text
    announcements.py   scheduler: materialize runs, start runs, deliver, finalize
    campaigns.py       campaign CRUD and state transitions (API side)
    recurrence.py      occurrence computation in local wall-clock time
    outbox.py          panel replies
    commands.py        worker command executor
    sender.py          centralized Telegram sending (rate limit, flood wait, chat locks)
    metrics.py         dashboard + report queries
    retention.py       data minimization
  telegram/      Telethon client, gateway implementation, error mapping, handlers, reconcile, login CLI
  workers/       worker main loop and container healthcheck
  api/           FastAPI dependencies and routers
```

`app/telegram/types.py` defines `TelegramGateway` (a Protocol) and normalized dataclasses
(`TgMessage`, `SentMessage`, `GroupInfo`, `SendError`). Services depend only on these, so tests
substitute `FakeGateway` and never need a Telegram account.

## Data model (PostgreSQL)

| Table | Purpose / key constraints |
|---|---|
| `admins`, `admin_sessions` | Accounts (Argon2id hash); server-side sessions keyed by SHA-256 of the cookie token, with CSRF token. |
| `rate_limit_hits` | Shared rate-limit counters (login failures per user/IP, replies, commands). |
| `audit_events` | Administrator actions; actor username snapshotted. |
| `customers` | Unique `telegram_user_id`; first-contact (`welcome_*`) state machine. |
| `conversations` | One per customer (unique `customer_id`); last-activity timestamps, assignment. |
| `messages` | Metadata per Telegram message, unique `(conversation_id, telegram_message_id)` → idempotent ingestion. Text only as an optional truncated preview of *customer* messages. |
| `sla_incidents` | Waiting cycles; partial unique index: one `open` incident per conversation. Alert state machine. |
| `outgoing_messages` | Panel reply outbox. |
| `telegram_groups` | Discovered/manual groups with permission analysis and explicit `is_enabled` opt-in. |
| `announcement_campaigns`, `campaign_targets` | Campaign definition and per-group text. |
| `announcement_runs` | Occurrences; unique `(campaign_id, scheduled_for)`. |
| `announcement_deliveries` | One per run and group; unique `(run_id, group_id)`. |
| `app_settings` | Singleton JSONB row validated by `RuntimeSettings`. |
| `worker_state`, `connection_events`, `worker_commands` | Worker status, history, API→worker requests. |

All timestamps are `timestamptz` in UTC; the UI renders `Asia/Tashkent`.

## State machines and idempotency

Every outbound operation follows the same pattern:

1. **Claim** rows with `SELECT … FOR UPDATE SKIP LOCKED` and set an in-flight state
   (`sending`), **committed before** the Telegram call.
2. Call Telegram through `TelegramSender`.
3. Record the outcome (`sent` / retry with `next_attempt_at` / `failed`).
4. On worker start, rows left in the in-flight state (crash between 1 and 3) become
   `unknown`/`failed` and are **never re-sent automatically**.

This yields *at-most-once* delivery for every customer-, group- and admin-facing message:
a crash at the exact moment of sending can lose one message (visible as "unknown"), but can
never duplicate one.

### First contact (`customers.welcome_status`)
`not_applicable | pending → sending → sent | existing | failed | unknown`.
`pending` is set only when the customer row is *inserted* (unique `telegram_user_id`), so a
customer can be queued once. Before sending, the worker skips customers whose chat already
had history (`existing`), who were excluded, or who already got a human reply during the delay.

### SLA (`sla_incidents`)
- Opened by the first unanswered customer message; further messages only increment the count
  (the deadline does not move).
- Resolved by an outgoing message with a higher message id that counts as a human reply.
- `alert_status`: `none → pending` (single atomic `UPDATE … WHERE alert_status='none' AND
  deadline_at <= now()`), `pending → sending → sent | pending (retry) | failed`, or `skipped`.
- Changing the timeout recalculates deadlines of open, not-yet-alerted incidents.

### Reply classification (outgoing private messages)
Automated if: recorded by our own sender (checked under the per-chat lock, plus an in-memory
id registry), sent via a Telegram Business bot, or textually identical to the welcome template.
Forwarded messages count only when `count_forwarded_as_reply` is enabled. Edits never count.

### Announcements
`campaign: draft → scheduled ⇄ paused → completed | cancelled`.
The scheduler (every tick): materializes the next occurrence of each scheduled campaign as a
`pending` run (unique per occurrence) → starts due runs, creating one delivery per target
(`skipped` for disabled/forbidden groups, `dry_run` for test campaigns) → sends one delivery at a
time respecting `announcement_min_interval_seconds` and global flood waits → finalizes runs as
`completed | partial | failed | cancelled`. Runs older than `misfire_grace_minutes` become `missed`.

## Concurrency control

- **One Telegram connection:** the worker takes a PostgreSQL session-level advisory lock
  (`pg_try_advisory_lock`) before touching the session. A second worker waits in `standby` and
  takes over automatically if the first dies (the lock is released with its connection).
- **No double sends even if two workers ran:** all claims use `SKIP LOCKED` + committed
  in-flight state (`tests/test_announcements.py::test_concurrent_schedulers_do_not_double_send`).
- **Per-chat serialization:** `TelegramSender.chat_lock(user_id)` serializes processing of a chat
  so the update for a message we just sent cannot be misclassified as a human reply.
- **API:** stateless; can run several replicas.

## Restart recovery

- Telethon `catch_up=True` replays missed updates; handlers are registered before `connect()`.
- `reconcile_since()` re-reads private dialogs active since `worker_state.processed_until`
  (advanced only while connected) and feeds them through the idempotent inbox.
- SLA incidents, scheduled runs and queued replies live in the database, so nothing is lost.
- Long Telegram calls are raced against the shutdown event, so `SIGTERM` exits in ~1 s.

## Telegram error handling

`app/telegram/errors.py` maps Telethon/network exceptions to `SendError.kind`:
`flood` (wait exactly `retry_after`, not counted as an attempt, pauses all sends globally),
`transient` (exponential backoff 30 s → 30 min, bounded attempts), `permanent` (no retry;
group permission errors mark the group `can_send=false`), `unauthorized` (worker status
`unauthorized`, client disconnects), `invalid_content`.

## Why not APScheduler / Redis / Celery

The prompt allowed "APScheduler or an equally reliable persistent scheduling implementation".
APScheduler 3's job stores are synchronous and its state is a pickled job, which duplicates the
domain state (campaigns/runs) and makes idempotency and visibility harder. A database-driven
scheduler with explicit run/delivery rows gives persistence, exactly-one materialization,
per-group history and multi-process safety with no extra service. Redis/Celery would add
operational cost without solving a problem this workload has (a few messages per minute).

## Known limitations

See README §18.
