"""Saves, always scoped to one user (docs/09-security-privacy.md#user-isolation)."""

import hashlib
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Reading, Save, Snapshot
from app.ingest.urls import canonical_url, find_urls, platform_of
from app.verify.secrets import screen


def content_hash(value: str) -> str:
    return hashlib.sha256(" ".join(value.split()).lower().encode()).hexdigest()


def new_save_from_text(user_id: str, text: str, *, origin: str = "paste") -> Save:
    """Turn pasted or shared text into a save: a note, one link, or a list of links."""
    text = text.strip()
    urls = find_urls(text)
    result = screen(text)
    save = Save(
        user_id=user_id,
        origin=origin,
        text=text,
        visibility="private" if result.private else "normal",
        private_reason=result.reason,
    )
    if len(urls) == 1:
        rest = text.replace(urls[0], "").strip()
        save.kind = "link"
        save.url = urls[0]
        save.platform = platform_of(urls[0])
        save.canonical_url = canonical_url(urls[0])
        save.label = rest if 0 < len(rest) <= 60 else None
        save.content_hash = content_hash(save.canonical_url)
    else:
        save.kind = "list" if urls else "note"
        save.content_hash = content_hash(text)
    return save


def get_save(db: Session, user_id: str, save_id: str) -> Save | None:
    return db.scalar(select(Save).where(Save.id == save_id, Save.user_id == user_id))


def list_saves(
    db: Session, user_id: str, *, limit: int = 30, before_id: str | None = None
) -> Sequence[Save]:
    q = select(Save).where(Save.user_id == user_id)
    if before_id:
        q = q.where(Save.id < before_id)
    return db.scalars(q.order_by(Save.id.desc()).limit(limit)).all()


def get_reading(db: Session, save_id: str) -> Reading | None:
    return db.get(Reading, save_id)


def snapshots_for(db: Session, save_id: str) -> Sequence[Snapshot]:
    return db.scalars(
        select(Snapshot).where(Snapshot.save_id == save_id).order_by(Snapshot.id)
    ).all()


def readings_for(db: Session, save_ids: Sequence[str]) -> dict[str, Reading]:
    if not save_ids:
        return {}
    rows = db.scalars(select(Reading).where(Reading.save_id.in_(save_ids))).all()
    return {r.save_id: r for r in rows}


def upsert_reading(db: Session, save_id: str, values: dict) -> None:
    stmt = insert(Reading).values(save_id=save_id, **values)
    db.execute(stmt.on_conflict_do_update(index_elements=[Reading.save_id], set_=values))
