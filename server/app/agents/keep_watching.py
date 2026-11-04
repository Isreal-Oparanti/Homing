"""Keep watching: every 12 hours the agents look again, without being asked.

- Is it true? re-reads the official pages of saves that can still change (not closed, not
  ruled out, closing date ahead). Code compares each page with our last copy: unchanged costs
  no model call; changed means the save is checked again, so a moved date or a call that
  closed reaches Today on its own.
- What's it for? looks on the web for more for the goals the person is working on (once a
  day a goal, at most MAX_GOALS a run).

One `watch.tick` job is always waiting: the worker makes sure of it at start, and each tick
queues the next. Each tick queues one `watch.user` job per person active lately.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.agents import is_it_true
from app.agents.finds_more import queue_find
from app.db.models import Check, Job, Reading, Save, Snapshot, Thread, ThreadSave, User
from app.events.emitter import emit
from app.jobs import queue
from app.jobs.runner import JobContext

EVERY = timedelta(hours=12)
ACTIVE_FOR = timedelta(days=45)
MAX_PAGES = 15
MAX_GOALS = 3


def start_watching(db: Any) -> None:
    """Make sure one tick is waiting (called when the worker starts)."""
    waiting = db.scalar(
        select(Job.id).where(Job.kind == "watch.tick", Job.status.in_(("queued", "running")))
    )
    if waiting is None:
        queue.enqueue(db, "watch.tick", {}, priority=queue.PRIORITY_BACKLOG, max_attempts=1)
        db.commit()


def tick(ctx: JobContext, payload: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    users = ctx.db.scalars(
        select(Save.user_id).where(Save.created_at > now - ACTIVE_FOR).group_by(Save.user_id)
    ).all()
    for user_id in users:
        queue.enqueue(
            ctx.db,
            "watch.user",
            {},
            user_id=user_id,
            priority=queue.PRIORITY_BACKLOG,
            dedupe_key=f"watch:{user_id}:{now:%Y%m%d%H}",
            max_attempts=2,
        )
    nxt = now + EVERY
    queue.enqueue(
        ctx.db,
        "watch.tick",
        {},
        priority=queue.PRIORITY_BACKLOG,
        run_after=nxt,
        dedupe_key=f"watch:tick:{nxt:%Y%m%d%H}",
        max_attempts=1,
    )


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()) == " ".join(b.split())


def _recheck_pages(ctx: JobContext, user: User, now: datetime) -> None:
    rows = ctx.db.execute(
        select(Save, Check, Reading)
        .join(Check, Check.save_id == Save.id)
        .join(Reading, Reading.save_id == Save.id)
        .where(
            Save.user_id == user.id,
            Save.visibility != "private",
            Check.official_url.is_not(None),
            Check.verdict.notin_(("closed", "not_for_you")),
            (Check.deadline_at.is_(None)) | (Check.deadline_at > now),
        )
        .order_by(Check.deadline_at.asc().nulls_last())
        .limit(MAX_PAGES)
    ).all()
    if not rows:
        return
    fetcher = is_it_true.fetcher_factory()
    changed, gone = [], 0
    for save, check, reading in rows:
        last = ctx.db.scalar(
            select(Snapshot.text)
            .where(Snapshot.save_id == save.id, Snapshot.kind == "official_text")
            .order_by(Snapshot.fetched_at.desc())
            .limit(1)
        )
        page = is_it_true._fetch_source(check.official_url, reading.title, fetcher)
        if page is None:
            gone += 1
            continue
        if last is not None and _same(last, page.text):
            continue
        changed.append(reading.title)
        queue.enqueue(
            ctx.db,
            "save.check",
            {"save_id": save.id, "recheck": True},
            user_id=user.id,
            priority=queue.PRIORITY_NORMAL,
            dedupe_key=f"recheck:{save.id}:{now:%Y%m%d%H}",
        )
    said = f"Kept watching: re-read {len(rows)} official {'page' if len(rows) == 1 else 'pages'}. "
    if changed:
        names = ", ".join(changed[:3]) + (" and more" if len(changed) > 3 else "")
        they = "it's" if len(changed) == 1 else "they're"
        said += f"{len(changed)} changed since last time ({names}), so {they} checked again."
    else:
        said += "Nothing changed."
    if gone:
        said += f" {gone} couldn't be opened this time."
    emit(ctx.db, user_id=user.id, agent="true", action="watched", summary=said, models=[])


def _goals_to_grow(ctx: JobContext, user: User) -> list[str]:
    """Goals with an opportunity in them, most recently active first."""
    return list(
        ctx.db.scalars(
            select(Thread.id)
            .join(ThreadSave, ThreadSave.thread_id == Thread.id)
            .join(Reading, Reading.save_id == ThreadSave.save_id)
            .where(
                Thread.user_id == user.id,
                Thread.archived_at.is_(None),
                Reading.is_opportunity.is_(True),
            )
            .group_by(Thread.id)
            .order_by(func.max(Thread.updated_at).desc())
            .limit(MAX_GOALS)
        )
    )


def watch_user(ctx: JobContext, payload: dict[str, Any]) -> None:
    user = ctx.db.get(User, ctx.user_id) if ctx.user_id else None
    if user is None:
        return
    now = datetime.now(UTC)
    _recheck_pages(ctx, user, now)
    today = now.astimezone(ZoneInfo(user.tz)).date().isoformat()
    for thread_id in _goals_to_grow(ctx, user):
        queue_find(ctx.db, user.id, thread_id, today=today, priority=queue.PRIORITY_BACKLOG)
