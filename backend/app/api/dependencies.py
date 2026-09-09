from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorKind, ServiceError
from app.core.resources import Resources
from app.core.security import SESSION_PATTERN
from app.model.principal import Principal
from app.repository.api_keys import ApiKeyRepository
from app.repository.customers import CustomerRepository
from app.repository.sessions import SessionRepository
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.files import FileService


def get_resources(request: Request) -> Resources:
    return request.app.state.resources


ResourceDep = Annotated[Resources, Depends(get_resources)]


def get_settings(resources: ResourceDep) -> Settings:
    return resources.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_db(resources: ResourceDep) -> Generator[Session]:
    # Aynı istekte Depends(get_db) paylaşılır; farklı istekler ayrı Session alır.
    with resources.session_factory() as session:
        yield session


Db = Annotated[Session, Depends(get_db)]


def get_sessions(resources: ResourceDep, settings: SettingsDep) -> SessionRepository:
    return SessionRepository(resources.redis, settings.app_secret.get_secret_value())


SessionDep = Annotated[SessionRepository, Depends(get_sessions)]


def get_audit(db: Db, request: Request) -> AuditService:
    return AuditService(db, request.state.request_id)


AuditDep = Annotated[AuditService, Depends(get_audit)]


def get_auth_service(
    db: Db, settings: SettingsDep, sessions: SessionDep, audit: AuditDep
) -> AuthService:
    return AuthService(settings, CustomerRepository(db), ApiKeyRepository(db), sessions, audit)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def client_ip(request: Request) -> str:
    # X-Forwarded-For'u okumayız; Uvicorn yalnızca güvenilir proxy'yi kabul eder.
    return request.client.host if request.client else "unknown"


def check_origin(request: Request, settings: Settings) -> None:
    if request.headers.get("origin") != settings.public_origin:
        raise ServiceError(ErrorKind.FORBIDDEN, "İstek kaynağına izin verilmiyor")


def authenticate(request: Request, settings: SettingsDep, service: AuthServiceDep) -> Principal:
    raw_key = request.headers.get("x-api-key")
    raw_session = request.cookies.get(settings.cookie_name, "")
    if raw_key is None and SESSION_PATTERN.fullmatch(raw_session):
        # Origin/Fetch Metadata HTTP kuralıdır; servis yalnızca kimliği doğrular.
        if request.headers.get("origin"):
            check_origin(request, settings)
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise ServiceError(ErrorKind.FORBIDDEN, "İstek kaynağına izin verilmiyor")
    return service.authenticate(raw_key, raw_session, client_ip(request))


Auth = Annotated[Principal, Depends(authenticate)]


def get_file_service(resources: ResourceDep, audit: AuditDep, settings: SettingsDep) -> FileService:
    return FileService(resources.storage, audit, settings)


FileServiceDep = Annotated[FileService, Depends(get_file_service)]
