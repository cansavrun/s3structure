from fastapi import APIRouter

from app.api.dependencies import Db, SessionDep
from app.schema.health import LiveResponse, ReadyResponse
from app.services.health import check_readiness

router = APIRouter(prefix="/health", tags=["Sağlık"])


@router.get("/live", response_model=LiveResponse)
def live():
    return {"status": "ok"}


@router.get("/ready", response_model=ReadyResponse)
def ready(db: Db, sessions: SessionDep):
    check_readiness(db, sessions)
    return {"status": "ready"}
