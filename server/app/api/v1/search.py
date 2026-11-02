"""Search and Ask (docs/07-api.md, ADR 0003)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.saves import SaveListItem, SaveOut
from app.core.auth import CurrentUser, require_user
from app.core.errors import AppError
from app.db.models import Ask
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs import queue
from app.search.hybrid import search

router = APIRouter(tags=["search"])


class SearchOut(BaseModel):
    items: list[SaveListItem]


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)


class AskOut(BaseModel):
    id: str
    question: str
    status: str  # working · done · failed
    answer: dict[str, Any] | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None

    @classmethod
    def of(cls, ask: Ask) -> "AskOut":
        return cls.model_validate(ask, from_attributes=True)


@router.get("/search", response_model=SearchOut)
def search_saves(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> SearchOut:
    """By words and by meaning at once; no model call, so it can run as you type."""
    found = search(db, user.id, q, limit=limit)
    return SearchOut(
        items=[
            SaveListItem(
                **SaveOut.of(f.save).model_dump(), title=f.reading.title, what=f.reading.what
            )
            for f in found
        ]
    )


@router.post("/asks", status_code=202, response_model=AskOut)
def ask_question(
    body: AskIn, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> AskOut:
    """One question, one answer page, filled in by the ask.answer job."""
    ensure_user(db, user)
    ask = Ask(user_id=user.id, question=" ".join(body.question.split()))
    db.add(ask)
    db.flush()
    queue.enqueue(
        db,
        "ask.answer",
        {"ask_id": ask.id},
        user_id=user.id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"ask:{ask.id}",
        max_attempts=2,
    )
    db.commit()
    return AskOut.of(ask)


@router.get("/asks", response_model=list[AskOut])
def recent_asks(
    user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> list[AskOut]:
    rows = db.scalars(
        select(Ask).where(Ask.user_id == user.id).order_by(Ask.created_at.desc()).limit(10)
    ).all()
    return [AskOut.of(a) for a in rows]


@router.get("/asks/{ask_id}", response_model=AskOut)
def get_ask(
    ask_id: str, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> AskOut:
    ask = db.scalar(select(Ask).where(Ask.id == ask_id, Ask.user_id == user.id))
    if ask is None:
        raise AppError("ask_not_found", "That question doesn't exist.", status=404)
    return AskOut.of(ask)
