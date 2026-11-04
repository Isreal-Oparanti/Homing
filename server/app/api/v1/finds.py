"""What's it for? finds: what Muse Wonder found on the web for a goal, after code's checks.

Keep turns a find into an ordinary save, so every agent reads it like anything else saved.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import goal_memory
from app.agents.finds_more import queue_find
from app.agents.web_tools import host_of
from app.core.auth import CurrentUser, require_user
from app.core.errors import AppError
from app.db.models import AgentEvent, Find, Thread, User
from app.db.repo import saves as saves_repo
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.events.emitter import emit
from app.jobs import queue

router = APIRouter(tags=["finds"])

TAPS_A_DAY = 3  # Find more runs a goal can have in a day: web agents cost real money

FIT = {
    "fits_you": "Fits you",
    "needs_your_answer": "Check one thing to see if it fits you",
    "checked": "Open to apply · the page doesn't say who can",
}


class FindOut(BaseModel):
    id: str
    goal: str | None
    thread_id: str | None
    name: str
    what: str
    url: str
    site: str
    closes: str | None
    deadline_at: datetime | None
    fit: str
    verdict: str
    rules: list[dict[str, Any]]
    quotes: list[dict[str, Any]]
    state: str
    save_id: str | None


def _out(find: Find, goal: str | None, tz: str) -> FindOut:
    closes = None
    if find.deadline_at is not None:
        day = find.deadline_at.astimezone(ZoneInfo(tz))
        closes = f"Closes {day:%a} {day.day} {day:%b}"
    return FindOut(
        id=find.id,
        goal=goal,
        thread_id=find.thread_id,
        name=find.name,
        what=find.what,
        url=find.url,
        site=host_of(find.url),
        closes=closes,
        deadline_at=find.deadline_at,
        fit=FIT.get(find.verdict, "Open to apply"),
        verdict=find.verdict,
        rules=[
            {"plain": r.get("plain"), "quote": r.get("quote"), "result": r.get("result")}
            for r in find.rules
        ],
        quotes=find.quotes,
        state=find.state,
        save_id=find.save_id,
    )


@router.get("/finds", response_model=list[FindOut])
def list_finds(
    thread_id: str | None = None,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[FindOut]:
    """New finds whose closing date hasn't passed, soonest first."""
    ensure_user(db, user)
    me = db.get(User, user.id)
    assert me is not None
    now = datetime.now(UTC)
    where = [Find.user_id == user.id, Find.state == "new"]
    if thread_id:
        where.append(Find.thread_id == thread_id)
    rows = db.execute(
        select(Find, Thread.title)
        .outerjoin(Thread, Thread.id == Find.thread_id)
        .where(*where)
        .order_by(Find.deadline_at.asc().nulls_last(), Find.created_at.desc())
        .limit(20)
    ).all()
    return [
        _out(f, goal, me.tz) for f, goal in rows if f.deadline_at is None or f.deadline_at > now
    ]


def _get(db: Session, user_id: str, find_id: str) -> Find:
    find = db.get(Find, find_id)
    if find is None or find.user_id != user_id:
        raise AppError("find_not_found", "That find doesn't exist.", status=404)
    return find


@router.post("/finds/{find_id}/keep", response_model=FindOut)
def keep(
    find_id: str, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> FindOut:
    """Save it: from here it's read, checked, placed and dated like anything the person saved."""
    ensure_user(db, user)
    me = db.get(User, user.id)
    assert me is not None
    find = _get(db, user.id, find_id)
    if find.save_id is None:
        if find.thread_id:
            goal_memory.remember(
                db, user.id, find.thread_id, kept=[{"name": find.name, "site": host_of(find.url)}]
            )
        save = saves_repo.new_save_from_text(user.id, find.url, origin="found")
        db.add(save)
        db.flush()
        find.save_id = save.id
        queue.enqueue(
            db,
            "save.read",
            {"save_id": save.id},
            user_id=user.id,
            priority=queue.PRIORITY_USER,
            dedupe_key=f"read:{save.id}",
        )
        emit(
            db,
            user_id=user.id,
            agent="for",
            action="find_kept",
            summary=f"You kept {find.name}. Reading it like anything you save.",
            save_id=save.id,
            thread_id=find.thread_id,
            models=[],
        )
    find.state = "kept"
    db.commit()
    goal = db.get(Thread, find.thread_id).title if find.thread_id else None
    return _out(find, goal, me.tz)


class DismissIn(BaseModel):
    why: Literal["wrong_country", "not_my_stage", "already_applied", "not_interested"] | None = None


@router.post("/finds/{find_id}/dismiss", status_code=204)
def dismiss(
    find_id: str,
    body: DismissIn | None = None,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> None:
    """Not for me, with an optional reason: the next run for this goal rules out the like."""
    find = _get(db, user.id, find_id)
    find.state = "dismissed"
    why = body.why if body else None
    if find.thread_id:
        goal_memory.remember(
            db,
            user.id,
            find.thread_id,
            dismissed=[{"name": find.name, "site": host_of(find.url), "why": why}],
        )
    reason = f" ({goal_memory.WHY_NOT[why]})" if why else ""
    emit(
        db,
        user_id=user.id,
        agent="for",
        action="find_dismissed",
        summary=f"Not for you: {find.name}{reason}. Next time Homing rules out the like.",
        thread_id=find.thread_id,
        models=[],
    )
    db.commit()


@router.post("/threads/{thread_id}/find", status_code=202)
def find_now(
    thread_id: str, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> dict[str, bool]:
    """Look on the web for more for this goal now."""
    ensure_user(db, user)
    me = db.get(User, user.id)
    assert me is not None
    thread = db.get(Thread, thread_id)
    if thread is None or thread.user_id != user.id:
        raise AppError("thread_not_found", "That goal doesn't exist.", status=404)
    since = datetime.now(UTC) - timedelta(hours=24)
    runs = db.scalar(
        select(func.count())
        .select_from(AgentEvent)
        .where(
            AgentEvent.thread_id == thread.id,
            AgentEvent.action == "find_started",
            AgentEvent.created_at > since,
        )
    )
    if (runs or 0) >= TAPS_A_DAY:
        raise AppError(
            "looked_enough",
            "Homing already looked for this goal a few times today. It looks again overnight.",
            status=429,
        )
    queue_find(db, user.id, thread.id, priority=queue.PRIORITY_USER, asked=True)
    db.commit()
    return {"queued": True}
