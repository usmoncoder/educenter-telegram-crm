# Single-image build for PaaS (e.g. Railway) where one service runs the API that ALSO serves
# the built frontend from the same origin. The Docker Compose setup does NOT use this file —
# it builds backend/ and frontend/ separately with nginx in front. Used by both the `app`
# service (default CMD below) and the `worker` service (which overrides the start command to
# `python -m app.workers.main`).

# --- Stage 1: build the frontend -----------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend + bundled frontend ---------------------------------------------------
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY backend/pyproject.toml ./
# Install only runtime dependencies first (better layer caching).
RUN python -c "import tomllib; print(chr(10).join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

COPY backend/alembic.ini ./
COPY backend/app ./app
COPY --from=frontend /fe/dist /app/frontend_dist

# Session dir kept for the file-session fallback; on Railway TELEGRAM_SESSION_STRING is used.
RUN mkdir -p /data/session && chown -R app:app /data && chmod 700 /data/session
ENV TELEGRAM_SESSION_DIR=/data/session \
    FRONTEND_DIST=/app/frontend_dist

USER app

# One image, two roles selected by RUN_MODE:
#   RUN_MODE=worker  -> the Telegram worker (background jobs, no HTTP port)
#   otherwise        -> run migrations, then the API (which also serves the SPA) on $PORT
CMD ["sh", "-c", "if [ \"$RUN_MODE\" = worker ]; then exec python -m app.workers.main; else alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*' --no-server-header; fi"]
