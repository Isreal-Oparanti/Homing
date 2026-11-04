"""What's it for? Connects each save to the goal it serves (a thread) and spots repeats.

See docs/03-agents.md#whats-it-for. Repeats are found by code. The model only picks a thread
or proposes a goal; code checks the pick and rejects titles that describe the person.
"""

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.agents.finds_more import queue_find
from app.db.models import Reading, Save, Snapshot, Thread, ThreadSave, User
from app.db.repo import saves as saves_repo
from app.events.emitter import emit
from app.ingest.urls import find_urls
from app.jobs import queue
from app.jobs.errors import DeferredError, PermanentError
from app.jobs.runner import JobContext
from app.llm.gateway import ModelGateway
from app.schemas.agents import Placement, Rebuild

MAX_THREADS_SHOWN = 60
# The whole pile at once (threads.rebuild).
MIN_SAVES = 2  # a goal with one save is a guess
MAX_GOALS_PER_SAVE = 2
MAX_LINE_CHARS = 220
REBUILD_WAIT = timedelta(minutes=2)  # while an import is still being read
REBUILD_PATIENCE = timedelta(hours=3)  # then go with what's ready
SECOND_LOOK_MIN = 10  # left-out saves worth a second look
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
    if reading.is_opportunity and not save.import_id:
        # An opportunity saved for a goal: look on the web for more like it (once a day a goal).
        user = ctx.db.get(User, save.user_id)
        today = datetime.now(ZoneInfo(user.tz if user else "Africa/Lagos")).date().isoformat()
        queue_find(ctx.db, save.user_id, thread.id, today=today, priority=queue.PRIORITY_NORMAL)


def _when_in(save: Save, tz: str) -> str:
    when = save.saved_at.astimezone(ZoneInfo(tz))
    return f"{when.day} {when:%b}"


def link_repeats(ctx: JobContext, user_id: str, tz: str) -> int:
    """Repeats across the pile, by code: a later save with the same content as an earlier one
    is marked as a repeat, and The team says when it was first saved."""
    saves = ctx.db.scalars(
        select(Save)
        .where(Save.user_id == user_id, Save.visibility == "normal", Save.duplicate_of.is_(None))
        .order_by(Save.saved_at, Save.id)
    ).all()
    first: dict[str, Save] = {}
    linked = 0
    for save in saves:
        earlier = first.setdefault(save.content_hash, save)
        if earlier is save:
            continue
        save.duplicate_of = earlier.id
        linked += 1
        emit(
            ctx.db,
            user_id=user_id,
            agent="for",
            action="merged",
            summary=f"You saved this before, on {_when_in(earlier, tz)}.",
            save_id=save.id,
            evidence=[{"label": "The earlier save", "url": f"/saves/{earlier.id}"}],
        )
    return linked


def _something_to_go_on(save: Save, reading: Reading) -> bool:
    """A model reading, or words of the person's own: not just "An Instagram post you saved"."""
    if reading.model != "none" or save.label:
        return True
    words = save.text or ""
    for url in find_urls(words):
        words = words.replace(url, "")
    return bool(words.strip())


def _line(n: int, save: Save, reading: Reading) -> str:
    parts = [
        str(n),
        f"{save.saved_at:%Y-%m-%d}",
        reading.title,
        reading.what or "",
        save.label or "",
    ]
    return " | ".join(" ".join(p.split()) for p in parts)[:MAX_LINE_CHARS]


Plan = dict[str, tuple[Thread | None, str, str, list[Save]]]
SECOND_LOOK = (
    "Second look: SAVES holds only the saves the first pass left out, and THREADS the goals "
    "it made."
)


def _ask(
    ctx: JobContext,
    uid: str,
    goals: dict[str, Thread],
    counts: dict[str, int],
    lines: list[str],
    by_n: dict[int, Save],
    note: str | None = None,
) -> Rebuild:
    inputs: dict[str, Any] = {
        "threads": [
            {"id": tid, "title": t.title, "saves": counts.get(t.id, 0), "locked": t.locked_by_user}
            for tid, t in goals.items()
        ],
        "saves": "\n".join(lines),
    }
    if note:
        inputs["note"] = note
    return gateway_factory(ctx.db).run(
        "place.rebuild",
        user_id=uid,
        inputs=inputs,
        save_ids=[save.id for save in by_n.values()],
    )


def _check(
    out: Rebuild, goals: dict[str, Thread], by_n: dict[int, Save], goals_of: Counter[str]
) -> Plan:
    """Code checks the model's plan: real line numbers, goal titles (never about the person),
    at least two saves a new goal, at most two goals a save, the person's own names kept."""
    plan: Plan = {}
    for goal in out.threads:
        kept = goals.get(goal.keep or "")
        title = kept.title if kept is not None and kept.locked_by_user else clean_title(goal.title)
        if title is None:
            continue
        members = [
            save
            for n in dict.fromkeys(goal.saves)
            if (save := by_n.get(n)) is not None and goals_of[save.id] < MAX_GOALS_PER_SAVE
        ]
        # An existing goal can take a single save; a new goal needs at least two.
        if not members or (kept is None and len(members) < MIN_SAVES):
            continue
        for save in members:
            goals_of[save.id] += 1
        key = title.lower()
        if key in plan:  # the same goal twice: one thread
            old = plan[key]
            plan[key] = (old[0] or kept, old[1], old[2], old[3] + members)
        else:
            plan[key] = (kept, title, goal.why[:200], members)
    return plan


def _apply(ctx: JobContext, uid: str, plan: Plan, by_title: dict[str, Thread]) -> list[Thread]:
    used = []
    for key, (kept, title, why, members) in plan.items():
        thread = kept or by_title.get(key)
        if thread is None:
            thread = Thread(user_id=uid, title=title, created_by="agent", summary=why)
            ctx.db.add(thread)
            ctx.db.flush()
            by_title[key] = thread
        elif kept is None or not thread.summary:
            thread.summary = why
        if not thread.locked_by_user:
            thread.title = title
        thread.archived_at = None
        thread.updated_at = func.now()
        for save in members:
            ctx.db.execute(
                insert(ThreadSave)
                .values(thread_id=thread.id, save_id=save.id, added_by="agent", reason=why)
                .on_conflict_do_nothing()
            )
        used.append(thread)
    return used


def rebuild(ctx: JobContext, payload: dict[str, Any]) -> None:
    """What's it for? over the whole pile in long-context calls (docs/03 · Rebuild). The model
    proposes goals and which saves serve each, then takes a second look at what it left out;
    code checks every title, keeps threads the person named, links repeats, and archives
    threads left empty."""
    if ctx.user_id is None:
        raise PermanentError("threads.rebuild needs a user.")
    uid = ctx.user_id
    now = datetime.now(UTC)
    since = payload.get("since")
    unread = ctx.db.scalar(
        select(func.count())
        .select_from(Save)
        .where(
            Save.user_id == uid,
            Save.visibility == "normal",
            Save.status.in_(("received", "reading")),
        )
    )
    if unread and since and now - datetime.fromisoformat(since) < REBUILD_PATIENCE:
        raise DeferredError(f"Waiting for {unread} saves to be read.", until=now + REBUILD_WAIT)

    owner = ctx.db.get(User, uid)
    tz = owner.tz if owner else "Africa/Lagos"
    link_repeats(ctx, uid, tz)
    ctx.db.flush()

    rows = ctx.db.execute(
        select(Save, Reading)
        .join(Reading, Reading.save_id == Save.id)
        .where(
            Save.user_id == uid,
            Save.visibility == "normal",
            Save.status == "ready",
            Save.duplicate_of.is_(None),
        )
        .order_by(Save.saved_at, Save.id)
    ).all()
    pile = [(save, reading) for save, reading in rows if _something_to_go_on(save, reading)]
    if len(pile) < MIN_SAVES:
        return
    by_n = {n: save for n, (save, _) in enumerate(pile, 1)}
    lines = [_line(n, save, reading) for n, (save, reading) in enumerate(pile, 1)]

    threads = ctx.db.scalars(
        select(Thread)
        .where(Thread.user_id == uid, Thread.archived_at.is_(None))
        .order_by(Thread.created_at)
    ).all()
    counts = dict(
        ctx.db.execute(
            select(ThreadSave.thread_id, func.count())
            .where(ThreadSave.thread_id.in_([t.id for t in threads]))
            .group_by(ThreadSave.thread_id)
        ).all()
    )
    existing = {f"T{i}": t for i, t in enumerate(threads, 1)}
    goals_of: Counter[str] = Counter()
    plan = _check(_ask(ctx, uid, existing, counts, lines, by_n), existing, by_n, goals_of)

    unlocked = [t.id for t in threads if not t.locked_by_user]
    if unlocked:
        ctx.db.execute(
            delete(ThreadSave).where(
                ThreadSave.thread_id.in_(unlocked), ThreadSave.added_by == "agent"
            )
        )
    by_title = {t.title.lower(): t for t in threads}
    made = _apply(ctx, uid, plan, by_title)

    # A second look at what the first pass left out: one long answer tends to under-place.
    left = [(save, reading) for save, reading in pile if not goals_of[save.id]]
    if len(left) >= SECOND_LOOK_MIN and made:
        ctx.db.flush()
        goals = {f"T{i}": t for i, t in enumerate(dict.fromkeys(made), 1)}
        sizes = {t.id: sum(1 for _ in plan.get(t.title.lower(), (0, 0, 0, []))[3]) for t in made}
        more_n = {n: save for n, (save, _) in enumerate(left, 1)}
        more_lines = [_line(n, save, reading) for n, (save, reading) in enumerate(left, 1)]
        more = _ask(ctx, uid, goals, sizes, more_lines, more_n, note=SECOND_LOOK)
        made += _apply(ctx, uid, _check(more, goals, more_n, goals_of), by_title)

    # Repeats follow the save they repeat.
    repeats = ctx.db.execute(
        select(Save.id, ThreadSave.thread_id)
        .join(ThreadSave, ThreadSave.save_id == Save.duplicate_of)
        .where(Save.user_id == uid, Save.duplicate_of.is_not(None))
    ).all()
    for save_id, thread_id in repeats:
        ctx.db.execute(
            insert(ThreadSave)
            .values(thread_id=thread_id, save_id=save_id, added_by="agent", reason="Saved before")
            .on_conflict_do_nothing()
        )

    # Threads left with nothing in them are archived, never deleted.
    ctx.db.flush()
    for thread in threads:
        n = ctx.db.scalar(
            select(func.count()).select_from(ThreadSave).where(ThreadSave.thread_id == thread.id)
        )
        if not n and not thread.locked_by_user:
            thread.archived_at = now

    goals_made = list(dict.fromkeys(made))
    sizes_now = dict(
        ctx.db.execute(
            select(ThreadSave.thread_id, func.count())
            .where(
                ThreadSave.thread_id.in_([t.id for t in goals_made]),
                ThreadSave.save_id.in_([save.id for save, _ in pile]),
            )
            .group_by(ThreadSave.thread_id)
        ).all()
    )
    final = sorted(((t, sizes_now.get(t.id, 0)) for t in goals_made), key=lambda x: -x[1])
    placed = sum(1 for save, _ in pile if goals_of[save.id])
    like = " and ".join(f"'{t.title}' ({n})" for t, n in final[:2])
    emit(
        ctx.db,
        user_id=uid,
        agent="for",
        action="rebuilt",
        summary=f"Organised {placed} saves into {len(final)} goals"
        + (f", like {like}." if like else "."),
        evidence=[{"label": t.title, "url": f"/threads/{t.id}"} for t, _ in final[:5]],
    )
