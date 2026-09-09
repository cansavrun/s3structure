from app.core.errors import ErrorKind, ServiceError
from app.repository.sessions import SessionRepository


class RateLimiter:
    def __init__(self, sessions: SessionRepository):
        self.sessions = sessions

    def check(self, scope: str, identity: str, limit: int) -> None:
        if self.sessions.increment(scope, identity) > limit:
            raise ServiceError(
                ErrorKind.RATE_LIMITED,
                "Çok fazla istek. Bir dakika sonra tekrar deneyin.",
                retry_after=60,
            )
