from fastapi import APIRouter

from app.api.v1 import dev, health, me, team

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(me.router)
router.include_router(team.router)
router.include_router(dev.router)
