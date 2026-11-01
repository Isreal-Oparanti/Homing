from fastapi import APIRouter

from app.api.v1 import dev, health, imports, me, saves, team, threads, today

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(me.router)
router.include_router(saves.router)
router.include_router(imports.router)
router.include_router(threads.router)
router.include_router(team.router)
router.include_router(today.router)
router.include_router(dev.router)
