from sqlalchemy.orm import Session

from app.core.errors import ErrorKind, ServiceError
from app.repository.health import check_database
from app.repository.sessions import SessionRepository


def check_readiness(db: Session, sessions: SessionRepository) -> None:
    check_database(db)
    try:
        sessions.ping()
    except ServiceError as exc:
        raise ServiceError(ErrorKind.UNAVAILABLE, "Servis henüz hazır değil") from exc
