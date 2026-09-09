from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass

from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import make_database
from app.repository.s3 import S3Repository


@dataclass
class Resources:
    """Uygulama ömürlü havuzlar; burada istek Session'ı veya müşteri tutulmaz."""

    settings: Settings
    session_factory: sessionmaker[Session]
    redis: Redis
    storage: S3Repository
    engine: Engine | None
    owns_redis: bool
    owns_storage: bool

    def close(self) -> None:
        # Bir close başarısız olsa da diğer kaynaklar bırakılır. Enjekte edilen
        # kaynakların sahibi çağırandır; onun bağlantısını biz kapatmayız.
        with ExitStack() as cleanup:
            if self.engine is not None:
                cleanup.callback(self.engine.dispose)
            if self.owns_redis:
                cleanup.callback(self.redis.close)
            if self.owns_storage:
                cleanup.callback(self.storage.close)


def make_resources(
    settings: Settings,
    *,
    session_factory: sessionmaker[Session] | None = None,
    redis_client: Redis | None = None,
    storage: S3Repository | None = None,
) -> Resources:
    engine = None
    if session_factory is None:
        engine, session_factory = make_database(settings.database_url.get_secret_value())
    redis = (
        redis_client
        if redis_client is not None
        else Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )
    )
    return Resources(
        settings=settings,
        session_factory=session_factory,
        redis=redis,
        storage=storage if storage is not None else S3Repository(settings),
        engine=engine,
        owns_redis=redis_client is None,
        owns_storage=storage is None,
    )


def lifespan_for(resources: Resources):
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            resources.close()

    return lifespan
