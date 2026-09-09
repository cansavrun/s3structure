from fastapi import APIRouter, Request, Response

from app.api.dependencies import Auth, AuthServiceDep, SettingsDep, check_origin, client_ip
from app.schema.auth import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/api", tags=["Oturum"])


@router.post("/auth/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    service: AuthServiceDep,
):
    check_origin(request, settings)
    principal, raw = service.login(
        body.api_key.get_secret_value(),
        request.cookies.get(settings.cookie_name, ""),
        client_ip(request),
    )
    # Cookie HTTP'ye özgüdür; servisin ürettiği sır API katmanında cookie olur.
    response.set_cookie(
        settings.cookie_name,
        raw,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="strict",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return {"customer": {"id": principal.customer.id, "name": principal.customer.name}}


@router.post("/auth/logout", status_code=204, response_model=None)
def logout(request: Request, response: Response, settings: SettingsDep, service: AuthServiceDep):
    check_origin(request, settings)
    service.logout(request.cookies.get(settings.cookie_name, ""))
    response.delete_cookie(
        settings.cookie_name,
        path="/",
        httponly=True,
        secure=settings.secure_cookie,
        samesite="strict",
    )


@router.get("/me", response_model=MeResponse)
def me(principal: Auth, settings: SettingsDep):
    return {
        "customer": {"id": principal.customer.id, "name": principal.customer.name},
        "key_name": principal.key.name,
        "expires_at": principal.key.expires_at,
        "preview_max_bytes": settings.preview_max_bytes,
    }
