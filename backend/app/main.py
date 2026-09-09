"""Composition root: uygulamayı kurar; endpoint, SQL veya iş kuralı içermez."""

from fastapi import FastAPI
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import install_exception_handlers
from app.api.middleware import install_middleware
from app.api.router import router
from app.core.config import Settings
from app.core.resources import lifespan_for, make_resources
from app.repository.s3 import S3Repository
from app.schema.error import ErrorResponse


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    redis_client: Redis | None = None,
    storage: S3Repository | None = None,
) -> FastAPI:
    settings = settings or Settings()
    resources = make_resources(
        settings, session_factory=session_factory, redis_client=redis_client, storage=storage
    )
    app = FastAPI(
        title="TenantFiles API",
        version="1.0.0",
        lifespan=lifespan_for(resources),
        docs_url=None if settings.environment == "production" else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "production" else "/api/openapi.json",
        responses={code: {"model": ErrorResponse} for code in (422, 500, 503)},
    )
    app.state.resources = resources
    install_middleware(app, settings)
    install_exception_handlers(app)
    app.include_router(router)
    return app
