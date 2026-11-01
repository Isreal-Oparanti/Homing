"""Files people save, stored once per user and content (docs/02-data-model.md · media)."""

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Media
from app.ingest.files import EXTENSIONS
from app.storage import Storage


def store(
    db: Session, storage: Storage, user_id: str, data: bytes, mime: str, filename: str | None
) -> tuple[Media, bool]:
    """The file's media row, and whether it was new. The same bytes saved again are kept once:
    keys are `u/{user_id}/{sha256}.{ext}`."""
    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Media).where(Media.user_id == user_id, Media.sha256 == sha).limit(1)
    )
    if existing is not None:
        return existing, False
    key = f"u/{user_id}/{sha}.{EXTENSIONS[mime]}"
    storage.put(key, data, mime)
    media = Media(
        user_id=user_id,
        storage_key=key,
        mime=mime,
        bytes=len(data),
        sha256=sha,
        original_filename=(filename or "")[:200] or None,
    )
    db.add(media)
    db.flush()
    return media, True
