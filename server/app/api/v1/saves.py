"""Saves: add one, list them, and read a save card (docs/07-api.md#saves)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_user
from app.core.errors import AppError
from app.db.models import Save, Snapshot
from app.db.repo import saves as saves_repo
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs import queue

router = APIRouter(prefix="/saves", tags=["saves"])

MAX_TEXT = 20_000
COPY_EXCERPT_CHARS = 1_500


class SaveIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)


class SaveOut(BaseModel):
    id: str
    kind: str
    platform: str | None
    url: str | None
    label: str | None
    text: str | None
    saved_at: datetime
    status: str
    visibility: str
    error: str | None

    @classmethod
    def of(cls, save: Save) -> "SaveOut":
        out = cls.model_validate(save, from_attributes=True)
        if save.visibility == "private":
            # Never echoed back; the owner taps Show (GET /saves/{id}/reveal). The link and
            # label go too, since a key inside a URL is one reason a save is private.
            out.text = out.url = out.label = None
        return out


class SaveListItem(SaveOut):
    title: str | None = None
    what: str | None = None


class CopyOut(BaseModel):
    """Our copy of the content, kept at save time: the proof behind "What is it?"."""

    id: str
    kind: str
    source_url: str | None
    chars: int
    excerpt: str

    @classmethod
    def of(cls, snap: Snapshot) -> "CopyOut":
        return cls(
            id=snap.id,
            kind=snap.kind,
            source_url=snap.source_url,
            chars=len(snap.text),
            excerpt=snap.text[:COPY_EXCERPT_CHARS],
        )


class PrivateText(BaseModel):
    text: str


class WhatOut(BaseModel):
    title: str
    what: str
    key_facts: dict[str, Any]
    is_checkable: bool
    is_opportunity: bool


class SaveCard(BaseModel):
    save: SaveOut
    what: WhatOut | None
    true: dict[str, Any] | None = None
    for_: dict[str, Any] | None = Field(default=None, serialization_alias="for")
    when: dict[str, Any] | None = None
    copies: list[CopyOut] = Field(default_factory=list)
    pending: list[str]


class SavePage(BaseModel):
    items: list[SaveListItem]
    next_cursor: str | None


@router.post("", status_code=202, response_model=SaveOut)
def create_save(
    body: SaveIn,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> SaveOut:
    """Store the save and queue "What is it?" in the same transaction."""
    ensure_user(db, user)
    save = saves_repo.new_save_from_text(user.id, body.text)
    db.add(save)
    db.flush()
    queue.enqueue(
        db,
        "save.read",
        {"save_id": save.id},
        user_id=user.id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"read:{save.id}",
    )
    db.commit()
    return SaveOut.of(save)


@router.get("", response_model=SavePage)
def list_saves(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> SavePage:
    rows = saves_repo.list_saves(db, user.id, limit=limit, before_id=cursor)
    readings = saves_repo.readings_for(db, [s.id for s in rows])
    items = []
    for s in rows:
        reading = readings.get(s.id)
        items.append(
            SaveListItem(
                **SaveOut.of(s).model_dump(),
                title=reading.title if reading else None,
                what=reading.what if reading else None,
            )
        )
    return SavePage(
        items=items,
        next_cursor=rows[-1].id if len(rows) == limit else None,
    )


@router.get("/{save_id}", response_model=SaveCard, response_model_by_alias=True)
def save_card(
    save_id: str,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> SaveCard:
    save = saves_repo.get_save(db, user.id, save_id)
    if save is None:
        raise AppError("save_not_found", "That save doesn't exist.", status=404)
    reading = saves_repo.get_reading(db, save.id)
    working = save.status in ("received", "reading")
    pending = []
    if reading is None and working:
        pending.append("what")
    if save.visibility != "private" and save.status != "failed":
        # Is it true? / What's it for? / When will you need it? arrive in the next slices.
        pending += ["true", "for", "when"]
    return SaveCard(
        save=SaveOut.of(save),
        what=WhatOut.model_validate(reading, from_attributes=True) if reading else None,
        copies=[CopyOut.of(snap) for snap in saves_repo.snapshots_for(db, save.id)],
        pending=pending,
    )


@router.get("/{save_id}/reveal", response_model=PrivateText)
def reveal(
    save_id: str,
    response: Response,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> PrivateText:
    """The owner's own text, shown on tap. Private saves leave out their text everywhere else."""
    save = saves_repo.get_save(db, user.id, save_id)
    if save is None or save.text is None:
        raise AppError("save_not_found", "That save doesn't exist.", status=404)
    response.headers["Cache-Control"] = "no-store"
    return PrivateText(text=save.text)
