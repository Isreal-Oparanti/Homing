"""What's it for? Connects each save to the goal it serves (a thread) and spots repeats.

See docs/03-agents.md#whats-it-for. Repeats are found by code. The model only picks a thread
or proposes a goal; code checks the pick and rejects titles that describe the person.
"""

import re
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Save, Snapshot, Thread, ThreadSave, User
from app.db.repo import saves as saves_repo
from app.events.emitter import emit
from app.jobs.errors import PermanentError
from app.jobs.runner import JobContext
from app.llm.gateway import ModelGateway
from app.schemas.agents import Placement

MAX_THREADS_SHOWN = 60
# Threads are goals, never labels about the person (docs/03, "Never: labels the user").
_ABOUT_THE_PERSON = re.compile(
    r"\b(you|your|you're|yourself|personality|introvert\w*|extrovert\w*|lazy|procrastinat\w*"
    r"|anxious|insecure|traits?|mbti)\b",
    re.I,
)

# Tests swap this for a fake; agents never build clients themselves.
gateway_factory: Any = ModelGateway


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def clean_title(title: str | None) -> str | None:
    """A usable goal title, or None if it's empty, too long or describes the person."""
    if not title:
        return None
    title = " ".join(title.split()).strip(" .'\"")
    if not title or len(title) > 60 or _ABOUT_THE_PERSON.search(title):
        return None
    if not re.search(r"[A-Za-z]", title):
        return None
    return title[0].upper() + title[1:]


def _join(ctx: JobContext, thread_id: str, save_id: str, reason: str | None) -> int:
    """Add the save to the thread (once) and return its count."""
    ctx.db.execute(
        insert(ThreadSave)
        .values(thread_id=thread_id, save_id=save_id, added_by="agent", reason=reason)
        .on_conflict_do_nothing()
    )
    return (
        ctx.db.scalar(
            select(func.count()).select_from(ThreadSave).where(ThreadSave.thread_id == thread_id)
        )
        or 0
    )


def _repeat_of(ctx: JobContext, save: Save) -> Save | None:
    return ctx.db.scalar(
        select(Save)
        .where(
            Save.user_id == save.user_id,
            Save.content_hash == save.content_hash,
            Save.id != save.id,
            Save.saved_at <= save.saved_at,
            Save.visibility == "normal",
        )
        .order_by(Save.saved_at)
        .limit(1)
    )


def _unreadable(ctx: JobContext, save: Save) -> bool:
    """A link we couldn't see inside, with no words of the person's own: nothing to place."""
    if save.kind != "link" or save.label:
        return False
    copies = ctx.db.scalar(
        select(func.count()).select_from(Snapshot).where(Snapshot.save_id == save.id)
    )
    return not copies


def place(ctx: JobContext, payload: dict[str, Any]) -> None:
    if ctx.user_id is None:
        raise PermanentError("save.place needs a user.")
    save = saves_repo.get_save(ctx.db, ctx.user_id, str(payload.get("save_id")))
    if save is None:
        raise PermanentError("That save no longer exists.")
    reading = saves_repo.get_reading(ctx.db, save.id)
    if save.visibility == "private" or reading is None:
        return

    # 1. Repeats, by code: same link or same text as an earlier save.
    if (earlier := _repeat_of(ctx, save)) is not None:
        save.duplicate_of = earlier.id
        thread_ids = ctx.db.scalars(
            select(ThreadSave.thread_id).where(ThreadSave.save_id == earlier.id)
        ).all()
        for thread_id in thread_ids:
            _join(ctx, thread_id, save.id, "Saved before")
        user = ctx.db.get(User, save.user_id)
        when = earlier.saved_at.astimezone(ZoneInfo(user.tz if user else "Africa/Lagos"))
        emit(
            ctx.db,
            user_id=save.user_id,
            agent="for",
            action="merged",
            summary=f"You saved this before, on {when.day} {when:%b}.",
            save_id=save.id,
            evidence=[{"label": "The earlier save", "url": f"/saves/{earlier.id}"}],
        )
        return

    if _unreadable(ctx, save):
        return

    # 2. The model picks a thread or proposes a goal; code checks the answer.
    threads = ctx.db.scalars(
        select(Thread)
        .where(Thread.user_id == save.user_id, Thread.archived_at.is_(None))
        .order_by(Thread.updated_at.desc())
        .limit(MAX_THREADS_SHOWN)
    ).all()
    counts = dict(
        ctx.db.execute(
            select(ThreadSave.thread_id, func.count())
            .where(ThreadSave.thread_id.in_([t.id for t in threads]))
            .group_by(ThreadSave.thread_id)
        ).all()
    )
    placement: Placement = gateway_factory(ctx.db).run(
        "place.assign",
        user_id=save.user_id,
        inputs={
            "save": {
                "title": reading.title,
                "what": reading.what,
                "label": save.label,
                "platform": save.platform,
                "is_opportunity": reading.is_opportunity,
            },
            "threads": [
                {"id": t.id, "title": t.title, "saves": counts.get(t.id, 0)} for t in threads
            ],
        },
        save_ids=[save.id],
    )
    by_id = {t.id: t for t in threads}
    thread = by_id.get(placement.thread_id or "")
    if thread is None:
        title = clean_title(placement.new_thread_title)
        if title is None:
            return  # unclear, or a title we won't use: better no thread than a wrong one
        same = next((t for t in threads if t.title.lower() == title.lower()), None)
        thread = same or Thread(user_id=save.user_id, title=title, created_by="agent")
        ctx.db.add(thread)
        ctx.db.flush()

    count = _join(ctx, thread.id, save.id, placement.reason[:200] or None)
    thread.updated_at = func.now()
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="for",
        action="placed",
        summary=f"Added to '{thread.title}' ({_ordinal(count)} save).",
        save_id=save.id,
        thread_id=thread.id,
    )
