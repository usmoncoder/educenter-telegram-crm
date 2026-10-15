"""FastAPI application (admin web API).

    uvicorn app.main:app --host 0.0.0.0 --port 8000

The API never talks to Telegram directly: it reads/writes the database, and the worker
(app.workers.main) performs every Telegram operation. Telegram credentials and the session
file are therefore never needed by, or exposed through, the web process.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import admin, announcements, auth, config, crm, health
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.session import create_engine, create_session_factory

log = get_logger("api")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}

_FIELD_NAMES_UZ = {
    "username": "Login",
    "password": "Parol",
    "text": "Matn",
    "title": "Sarlavha",
    "targets": "Guruhlar",
}


def _error(status: int, code: str, message: str, details: object = None) -> JSONResponse:
    body: dict[str, object] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details  # type: ignore[index]
    return JSONResponse(body, status_code=status)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        log.info("api_started", environment=settings.environment)
        yield
        await engine.dispose()

    app = FastAPI(
        title="EduCenter Telegram CRM API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    app.state.settings = settings

    allowed_origins = set(settings.cors_origins)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=request_id[:64])
        try:
            # Defence in depth against CSRF: unsafe requests must come from our own origin.
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                origin = request.headers.get("origin")
                if origin:
                    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
                    same = urlsplit(origin).netloc == host
                    if not same and origin not in allowed_origins:
                        return _error(403, "bad_origin", "So'rov manbasi ruxsat etilmagan")
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        response.headers["X-Request-ID"] = request_id[:64]
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            msg = str(err.get("msg", "")).removeprefix("Value error, ")
            field = _FIELD_NAMES_UZ.get(loc[-1], loc[-1]) if loc else None
            details.append({"field": ".".join(loc), "message": f"{field}: {msg}" if field else msg})
        message = details[0]["message"] if details else "Ma'lumotlar noto'g'ri"
        return _error(422, "validation_error", message, details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {404: "Sahifa topilmadi", 405: "Bu usul qo'llab-quvvatlanmaydi"}
        return _error(exc.status_code, f"http_{exc.status_code}", messages.get(exc.status_code, "So'rov xatosi"))

    @app.exception_handler(OperationalError)
    @app.exception_handler(DBAPIError)
    async def db_error(_: Request, exc: Exception) -> JSONResponse:
        log.error("database_error", error_type=type(exc).__name__)
        return _error(503, "database_unavailable", "Ma'lumotlar bazasi vaqtincha mavjud emas")

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(exc).__name__)
        return _error(500, "internal_error", "Ichki xatolik yuz berdi")

    for module in (health, auth, crm, config, announcements, admin):
        app.include_router(module.router, prefix="/api")

    # Optionally serve the built SPA from the same origin (single-service PaaS deploys).
    # On the Docker Compose setup this is unset and nginx serves the frontend instead.
    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = settings.frontend_dist
    if dist is None or not Path(dist).is_dir():
        return
    dist = Path(dist)
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        # API routes are matched first; anything else falls back to the SPA shell.
        if full_path.startswith("api/") or full_path == "api":
            return _error(404, "http_404", "Sahifa topilmadi")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
