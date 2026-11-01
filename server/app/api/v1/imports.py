"""WhatsApp imports: upload an export, then watch it come in (docs/07-api.md)."""

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_uploader, require_user
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.models import Import
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs import queue

router = APIRouter(prefix="/imports", tags=["imports"])

CHUNK = 1024 * 1024


class ImportOut(BaseModel):
    id: str
    status: str  # received · importing · done · failed
    format: str | None
    counts: dict[str, Any]
    error: str | None
    created_at: datetime
    finished_at: datetime | None

    @classmethod
    def of(cls, imp: Import) -> "ImportOut":
        return cls.model_validate(imp, from_attributes=True)


@router.post("/whatsapp", status_code=202, response_model=ImportOut)
def upload_whatsapp(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_uploader),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportOut:
    """The `.zip` WhatsApp makes with "Include media", or the chat `.txt` alone. It waits on
    the server's disk until the import job has read it, then it's deleted."""
    ensure_user(db, user)
    imp = Import(user_id=user.id, storage_key="", status="received", counts={})
    db.add(imp)
    db.flush()
    folder = Path(settings.import_dir)
    folder.mkdir(parents=True, exist_ok=True)
    imp.storage_key = f"{imp.id}.upload"
    path = folder / imp.storage_key
    size = 0
    with path.open("wb") as out:
        while chunk := file.file.read(CHUNK):
            size += len(chunk)
            if size > settings.import_max_bytes:
                break
            out.write(chunk)
    if size == 0 or size > settings.import_max_bytes:
        path.unlink(missing_ok=True)
        db.rollback()
        if size == 0:
            raise AppError("empty_file", "That file is empty.", status=422)
        raise AppError("too_big", "Exports must be 1 GB or smaller.", status=413)
    queue.enqueue(
        db,
        "import.whatsapp",
        {"import_id": imp.id},
        user_id=user.id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"import:{imp.id}",
        max_attempts=3,
    )
    db.commit()
    return ImportOut.of(imp)


@router.get("", response_model=list[ImportOut])
def recent_imports(
    user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> list[ImportOut]:
    rows = db.scalars(
        select(Import).where(Import.user_id == user.id).order_by(Import.id.desc()).limit(5)
    ).all()
    return [ImportOut.of(i) for i in rows]


@router.get("/{import_id}", response_model=ImportOut)
def get_import(
    import_id: str, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> ImportOut:
    imp = db.scalar(select(Import).where(Import.id == import_id, Import.user_id == user.id))
    if imp is None:
        raise AppError("not_found", "That import doesn't exist.", status=404)
    return ImportOut.of(imp)
