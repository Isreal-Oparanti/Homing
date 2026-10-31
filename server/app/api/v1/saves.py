"""Saves: add one, list them, and read a save card (docs/07-api.md#saves)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_user
from app.core.errors import AppError
from app.db.models import Save
from app.db.repo import saves as saves_repo
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs import queue

router = APIRouter(prefix="/saves", tags=["saves"])

MAX_TEXT = 20_000


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
            out.text = None  # shown blurred in the UI; never echoed back
        return out


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
    pending: list[str]


class SavePage(BaseModel):
    items: list[SaveOut]
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
    return SavePage(
        items=[SaveOut.of(s) for s in rows],
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
        pending=pending,
    )
