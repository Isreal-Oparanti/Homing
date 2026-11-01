"""Threads: the goals saves serve (docs/07-api.md#threads)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.whats_it_for import clean_title
from app.api.v1.saves import SaveListItem, SaveOut
from app.core.auth import CurrentUser, require_user
from app.core.errors import AppError
from app.db.models import Save, Thread, ThreadSave
from app.db.repo import saves as saves_repo
from app.db.session import get_db
from app.jobs import queue

router = APIRouter(prefix="/threads", tags=["threads"])


class ThreadOut(BaseModel):
    id: str
    title: str
    summary: str | None
    locked: bool  # the person named it; rebuilds keep the name
    saves: int
    last_saved_at: datetime | None


class ThreadPage(BaseModel):
    items: list[ThreadOut]
    unplaced: int  # ready saves in no thread


class ThreadDetail(ThreadOut):
    items: list[SaveListItem]


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)


def _owned(db: Session, user_id: str, thread_id: str) -> Thread:
    thread = db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id))
    if thread is None or thread.archived_at is not None:
        raise AppError("thread_not_found", "That thread doesn't exist.", status=404)
    return thread


def _stats(db: Session, thread_ids: list[str]) -> dict[str, tuple[int, datetime | None]]:
    rows = db.execute(
        select(ThreadSave.thread_id, func.count(), func.max(Save.saved_at))
        .join(Save, Save.id == ThreadSave.save_id)
        .where(ThreadSave.thread_id.in_(thread_ids))
        .group_by(ThreadSave.thread_id)
    ).all()
    return {tid: (n, last) for tid, n, last in rows}


def _out(thread: Thread, stats: dict[str, tuple[int, datetime | None]]) -> ThreadOut:
    n, last = stats.get(thread.id, (0, None))
    return ThreadOut(
        id=thread.id,
        title=thread.title,
        summary=thread.summary,
        locked=thread.locked_by_user,
        saves=n,
        last_saved_at=last,
    )


@router.get("", response_model=ThreadPage)
def list_threads(
    user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> ThreadPage:
    threads = db.scalars(
        select(Thread).where(Thread.user_id == user.id, Thread.archived_at.is_(None))
    ).all()
    stats = _stats(db, [t.id for t in threads])
    items = sorted((_out(t, stats) for t in threads), key=lambda t: (-t.saves, t.title))
    in_a_thread = select(ThreadSave.save_id).join(Thread).where(Thread.user_id == user.id)
    unplaced = db.scalar(
        select(func.count())
        .select_from(Save)
        .where(
            Save.user_id == user.id,
            Save.status == "ready",
            Save.visibility == "normal",
            Save.id.not_in(in_a_thread),
        )
    )
    return ThreadPage(items=[t for t in items if t.saves], unplaced=unplaced or 0)


@router.post("/rebuild", status_code=202)
def rebuild_threads(
    user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> dict[str, bool]:
    """Organise the whole pile again (What's it for?, threads.rebuild). Threads the person
    named keep their names."""
    queue.enqueue(
        db,
        "threads.rebuild",
        {},
        user_id=user.id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"rebuild:{user.id}",
    )
    db.commit()
    return {"queued": True}


@router.get("/{thread_id}", response_model=ThreadDetail)
def get_thread(
    thread_id: str, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> ThreadDetail:
    thread = _owned(db, user.id, thread_id)
    saves = db.scalars(
        select(Save)
        .join(ThreadSave, ThreadSave.save_id == Save.id)
        .where(ThreadSave.thread_id == thread.id, Save.user_id == user.id)
        .order_by(Save.saved_at.desc())
    ).all()
    readings = saves_repo.readings_for(db, [s.id for s in saves])
    items = [
        SaveListItem(
            **SaveOut.of(s).model_dump(),
            title=readings[s.id].title if s.id in readings else None,
            what=readings[s.id].what if s.id in readings else None,
        )
        for s in saves
    ]
    return ThreadDetail(**_out(thread, _stats(db, [thread.id])).model_dump(), items=items)


@router.patch("/{thread_id}", response_model=ThreadOut)
def rename_thread(
    thread_id: str,
    body: RenameIn,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> ThreadOut:
    """The person's own name for a goal. It locks the thread: rebuilds never rename it."""
    thread = _owned(db, user.id, thread_id)
    title = clean_title(body.title)
    if title is None:
        raise AppError(
            "bad_title",
            "Name it after a goal, in 60 characters or fewer, e.g. 'Getting into YC'.",
            status=422,
        )
    thread.title = title
    thread.locked_by_user = True
    thread.updated_at = datetime.now(UTC)
    db.commit()
    return _out(thread, _stats(db, [thread.id]))
