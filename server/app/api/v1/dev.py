"""Local-only helpers for checking the pipeline by hand. Return 404 anywhere but ENV=local."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_user
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs import queue

router = APIRouter(prefix="/dev", tags=["dev"])


class EchoIn(BaseModel):
    message: str = "The team is listening."


@router.post("/echo", status_code=202)
def echo(
    body: EchoIn,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, int | None]:
    """Queue a system.echo job; its event should reach /events/stream within about 2s."""
    if not settings.is_local:
        raise AppError("not_found", "Not found.", status=404)
    ensure_user(db, user)
    job_id = queue.enqueue(
        db, "system.echo", {"message": body.message}, user_id=user.id, priority=queue.PRIORITY_USER
    )
    db.commit()
    return {"job_id": job_id}
