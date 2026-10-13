from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, client_ip, get_db, get_principal, get_settings_dep
from app.core.config import Settings
from app.core.permissions import ROLE_PERMISSIONS
from app.schemas.api import AdminOut, ChangePasswordRequest, LoginRequest, MeOut
from app.schemas.common import OkResponse
from app.services import auth as auth_service
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=bool(settings.cookie_secure),
        samesite="lax",
        path="/",
    )


def _me(principal_admin, csrf: str) -> MeOut:
    return MeOut(
        admin=AdminOut.model_validate(principal_admin),
        permissions=sorted(p.value for p in ROLE_PERMISSIONS[principal_admin.role]),
        csrf_token=csrf,
    )


@router.post("/login", response_model=MeOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> MeOut:
    ip = client_ip(request)
    result = await auth_service.login(db, settings, body.username, body.password, ip, request.headers.get("user-agent"))
    await audit(db, "auth.login", actor=result.admin, ip=ip)
    _set_cookie(response, settings, result.token)
    return _me(result.admin, result.csrf_token)


@router.post("/logout", response_model=OkResponse)
async def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> OkResponse:
    await auth_service.revoke_session(db, principal.session.id)
    await audit(db, "auth.logout", actor=principal.admin, ip=client_ip(request))
    response.delete_cookie(settings.session_cookie_name, path="/")
    return OkResponse()


@router.get("/me", response_model=MeOut)
async def me(principal: Principal = Depends(get_principal)) -> MeOut:
    return _me(principal.admin, principal.session.csrf_token)


@router.post("/change-password", response_model=OkResponse)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    await auth_service.enforce_rate_limit(
        db, f"pwchange:{principal.admin.id}", limit=10, window=auth_service.LOGIN_WINDOW
    )
    await auth_service.change_password(
        db, principal.admin, body.current_password, body.new_password, principal.session.id
    )
    await audit(
        db,
        "auth.password_changed",
        actor=principal.admin,
        entity_type="admin",
        entity_id=principal.admin.id,
        ip=client_ip(request),
    )
    return OkResponse(message="Parol o'zgartirildi. Boshqa qurilmalardagi sessiyalar yakunlandi.")
