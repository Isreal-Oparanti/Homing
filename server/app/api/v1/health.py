import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_user
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/deep")
def health_deep(
    _: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    started = time.perf_counter()
    db.execute(text("select 1"))
    return {"status": "ok", "db_ms": round((time.perf_counter() - started) * 1000, 1)}
