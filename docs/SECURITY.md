# Security model and production checklist

## Threat model in brief

The system holds an authorized Telegram session (equivalent to a logged-in phone) and private
customer conversations. The main risks are leaking the session/API hash, unauthorized panel
access, and the account being used to message people who did not ask for it.

## Implemented controls

| Area | Control |
|---|---|
| Telegram credentials | `API_HASH` only in the worker's environment; never sent to the browser or returned by any endpoint. Login codes and 2FA passwords are entered in a terminal CLI and never stored or logged. |
| Session file | Telethon SQLite session in a dedicated volume, directory `0700`, file `0600`, only mounted into the worker. |
| Single session user | PostgreSQL advisory lock ensures one worker uses the session (prevents `AuthKeyDuplicated`). |
| Admin passwords | Argon2id (argon2-cffi defaults), rehash on login when parameters change, policy ≥ 12 chars with 3 character classes, no username inside. No default password; first admin created via CLI. |
| Sessions | Opaque 256-bit token in an `HttpOnly`, `Secure` (production), `SameSite=Lax` cookie; only its SHA-256 stored; expiry; revoked on logout, password change, deactivation. |
| CSRF | Per-session token required in `X-CSRF-Token` for all unsafe methods + `Origin` check. |
| Brute force | Failed logins limited per username (5/15 min) and per IP (20/15 min), shared across processes via the database. Unknown usernames take the same time and return the same error. |
| Authorization | Server-side RBAC on every route (`require(Perm…)`); operators additionally scoped to assigned/unassigned conversations in SQL. |
| Input | Pydantic validation on every request; Telegram HTML validated (allowed tags, `https/http/tg/mailto` links only, UTF-16 length). React renders message previews as text/elements — no `innerHTML`. SQL only through SQLAlchemy expressions. |
| Output | Error responses carry a code and an Uzbek message; never stack traces. API docs disabled in production. |
| Headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, CSP (nginx), HSTS (API in production), `Cache-Control: no-store` on API. |
| CORS | Not needed (same origin). Explicit allow-list only; `*` rejected in production. |
| Logging | structlog with a redaction processor and a stdlib filter for third-party logs (API hash, bot tokens, passwords, DB URL credentials, cookies). |
| Data minimization | Customer message text only as an optional truncated preview; operator reply text never stored; retention job deletes old message rows; per-customer erasure endpoint; personal contacts excluded by default. |
| Audit | Logins, settings, auto-reply, admin, customer, campaign, group and Telegram actions recorded with actor, IP and time. |
| Messaging safety | Groups are opt-in, permission-checked, multi-group sends require explicit confirmation (enforced server-side), flood waits honoured, no group joining, no invite-link handling. |

## Production checklist

- [ ] `ENVIRONMENT=production` in `.env`; `.env` is `chmod 600` and owned by the deploy user.
- [ ] Strong `POSTGRES_PASSWORD` (`openssl rand -base64 32`); the `db` service has no published port.
- [ ] HTTPS reverse proxy in front of `web` (Caddy/nginx with Let's Encrypt); `WEB_BIND=127.0.0.1`.
- [ ] `TRUSTED_PROXY_COUNT` equals the number of proxies in front of the API (nginx `web` + HTTPS proxy = 2).
- [ ] First Super Admin created via CLI; a second Super Admin exists as a recovery account.
- [ ] Telegram login done via `make tg-login`; 2FA enabled on the Telegram account.
- [ ] Alerts configured and verified with "Sinov ogohlantirishini yuborish".
- [ ] Daily `scripts/backup.sh` via cron; backups copied off-server; a restore has been tested.
- [ ] Docker log rotation (configured in `compose.yaml`: 10 MB × 5 per service).
- [ ] Retention period set in Settings according to your privacy policy.
- [ ] Firewall: only 22/443 open publicly.
- [ ] OS and Docker images updated regularly (`docker compose pull && docker compose up -d --build`).

## Incident response

1. Suspected session leak: Telegram → Settings → Devices → terminate the "EduCenter CRM"
   session; delete the `tgsession` volume; create a new API app at my.telegram.org; log in again.
2. Suspected admin compromise: deactivate the account (revokes its sessions), review the audit
   log, reset passwords via `python -m app.cli reset-password`.
