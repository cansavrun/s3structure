from fastapi import APIRouter

from app.api.routes import auth, files, health

router = APIRouter()
router.include_router(auth.router)
router.include_router(files.router)
router.include_router(health.router)
