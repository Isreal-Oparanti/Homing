"""The team feed: a page of past events, and a live stream of new ones (docs/07-api.md)."""

import asyncio
import time
from datetime import UTC, datetime
from datetime import time as day_time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_user
from app.db.models import (
    AgentEvent,
    Check,
    Job,
    ModelCall,
    Reading,
    Save,
    Thread,
    ThreadSave,
    User,
    When,
)
from app.db.repo import events as events_repo
from app.db.session import get_db, session_factory

router = APIRouter(tags=["team"])

POLL_S = 0.75
KEEPALIVE_S = 15.0
# Streams end after a minute and the browser reconnects, resuming from the id it last saw.
# Long streams hold up uvicorn reloads and deploys, which wait for open connections.
STREAM_MAX_S = 60.0


class AgentEventOut(BaseModel):
    id: int
    agent: str
    action: str
    summary: str
    save_id: str | None
    thread_id: str | None
    card_id: str | None
    evidence: list[dict[str, Any]]
    models: list[str] | None  # the Meta models behind it; [] code did it; None unknown
    created_at: datetime

    @classmethod
    def of(cls, e: AgentEvent) -> "AgentEventOut":
        return cls.model_validate(e, from_attributes=True)


class TeamPage(BaseModel):
    items: list[AgentEventOut]
    next_cursor: str | None


@router.get("/team", response_model=TeamPage)
def team(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    agent: str | None = Query(default=None),
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> TeamPage:
    before = int(cursor) if cursor and cursor.isdigit() else None
    rows = events_repo.list_events(db, user.id, before_id=before, limit=limit, agent=agent)
    next_cursor = str(rows[-1].id) if len(rows) == limit else None
    return TeamPage(items=[AgentEventOut.of(e) for e in rows], next_cursor=next_cursor)


MAP_GOALS = 8
AGENT_ROWS = ("what", "true", "for", "when")


# Which agent each job belongs to, so "working" comes from the real queue.
JOB_AGENT = {
    "save.read": "what",
    "save.read_batch": "what",
    "import.whatsapp": "what",
    "save.check": "true",
    "save.check_item": "true",
    "save.place": "for",
    "threads.rebuild": "for",
    "goal.find": "for",
    "watch.user": "true",
    "save.when": "when",
    "moment.match": "when",
    "card.prep": "when",
}
NEEDS_YOU_SHOWN = 5


class NeedsYou(BaseModel):
    save_id: str
    title: str


class Attention(BaseModel):
    """What's happening now: each agent's jobs in hand, and the saves waiting on the person."""

    working: dict[str, int]
    needs_you: int
    needs_you_items: list[NeedsYou]


def attention(db: Session, user_id: str) -> Attention:
    now = datetime.now(UTC)
    working = dict.fromkeys(AGENT_ROWS, 0)
    for kind, n in db.execute(
        select(Job.kind, func.count())
        .where(
            Job.user_id == user_id,
            Job.status.in_(("queued", "running")),
            Job.run_after <= now,
        )
        .group_by(Job.kind)
    ):
        if agent := JOB_AGENT.get(kind):
            working[agent] += n
    waiting = (
        select(Save.id, Reading.title)
        .join(Check, Check.save_id == Save.id)
        .join(Reading, Reading.save_id == Save.id)
        .outerjoin(When, When.save_id == Save.id)
        .where(
            Save.user_id == user_id,
            Save.visibility == "normal",
            Check.verdict == "needs_your_answer",
            (Check.deadline_at.is_(None)) | (Check.deadline_at > now),
            # A question about something whose date has passed is noise, not a need.
            (When.due_at.is_(None)) | (When.due_at > now),
        )
        .order_by(Check.deadline_at.asc().nulls_last(), Save.saved_at.desc())
    )
    items = db.execute(waiting.limit(NEEDS_YOU_SHOWN)).all()
    total = db.scalar(select(func.count()).select_from(waiting.subquery())) or 0
    return Attention(
        working=working,
        needs_you=total,
        needs_you_items=[NeedsYou(save_id=i, title=t) for i, t in items],
    )


@router.get("/team/attention", response_model=Attention)
def team_attention(
    user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> Attention:
    """Small and cheap: the menu asks this to show a badge when something needs you."""
    return attention(db, user.id)


class GoalDot(BaseModel):
    id: str
    title: str
    saves: int


class ModelUse(BaseModel):
    model: str
    calls_today: int
    calls: int
    tokens: int


class Overview(BaseModel):
    """What the agents map and the clock strip draw: all real counts, none made up."""

    saves: int
    goals: list[GoalDot]  # the largest goals, biggest first
    goal_of: dict[str, str]  # save id -> one of those goals, so a live event can land on it
    date: str
    hours: dict[str, list[int]]  # agent -> events in each hour of today, the person's time
    hour_now: int
    now: Attention
    models: list[ModelUse]  # each Meta model's real calls for this person, from model_calls


@router.get("/team/overview", response_model=Overview)
def overview(user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)) -> Overview:
    owner = db.get(User, user.id)
    tz = ZoneInfo(owner.tz if owner else "Africa/Lagos")
    now = datetime.now(tz)
    saves = db.scalar(
        select(func.count())
        .select_from(Save)
        .where(Save.user_id == user.id, Save.visibility == "normal")
    )
    size = func.count(ThreadSave.save_id)
    goals = db.execute(
        select(Thread.id, Thread.title, size)
        .join(ThreadSave, ThreadSave.thread_id == Thread.id)
        .where(Thread.user_id == user.id, Thread.archived_at.is_(None))
        .group_by(Thread.id, Thread.title)
        .order_by(size.desc(), Thread.title)
        .limit(MAP_GOALS)
    ).all()
    goal_of: dict[str, str] = {}
    for save_id, thread_id in db.execute(
        select(ThreadSave.save_id, ThreadSave.thread_id).where(
            ThreadSave.thread_id.in_([g[0] for g in goals])
        )
    ):
        goal_of.setdefault(save_id, thread_id)
    hours = {agent: [0] * 24 for agent in AGENT_ROWS}
    midnight = datetime.combine(now.date(), day_time(0), tzinfo=tz).astimezone(UTC)
    for agent, at in db.execute(
        select(AgentEvent.agent, AgentEvent.created_at).where(
            AgentEvent.user_id == user.id, AgentEvent.created_at >= midnight
        )
    ):
        if agent in hours:
            hours[agent][at.astimezone(tz).hour] += 1
    return Overview(
        saves=saves or 0,
        goals=[GoalDot(id=i, title=t, saves=n) for i, t, n in goals],
        goal_of=goal_of,
        date=now.date().isoformat(),
        hours=hours,
        hour_now=now.hour,
        now=attention(db, user.id),
        models=[
            ModelUse(model=m, calls_today=t or 0, calls=n, tokens=k or 0)
            for m, t, n, k in db.execute(
                select(
                    ModelCall.model,
                    func.count().filter(ModelCall.created_at >= midnight),
                    func.count(),
                    func.sum(ModelCall.tokens_in + ModelCall.tokens_out),
                )
                .where(ModelCall.user_id == user.id, ModelCall.status == "ok")
                .group_by(ModelCall.model)
                .order_by(func.count().desc())
            )
        ],
    )


def _latest(user_id: str) -> int:
    with session_factory()() as db:
        return events_repo.latest_event_id(db, user_id)


def _after(user_id: str, after_id: int) -> list[AgentEventOut]:
    with session_factory()() as db:
        return [AgentEventOut.of(e) for e in events_repo.events_after(db, user_id, after_id)]


@router.get("/events/stream")
async def stream(
    request: Request,
    user: CurrentUser = Depends(require_user),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Server-sent events. Resumes after `Last-Event-ID`, otherwise starts from now."""

    async def events() -> Any:
        last = int(last_event_id) if last_event_id and last_event_id.isdigit() else None
        if last is None:
            last = await asyncio.to_thread(_latest, user.id)
        started = last_ping = time.monotonic()
        # The id sets the browser's resume point, so a reconnect after a quiet minute skips nothing.
        yield f"id: {last}\nretry: 2000\n\n"
        while time.monotonic() - started < STREAM_MAX_S:
            if await request.is_disconnected():
                break
            for event in await asyncio.to_thread(_after, user.id, last):
                last = event.id
                yield f"id: {event.id}\nevent: agent_event\ndata: {event.model_dump_json()}\n\n"
                last_ping = time.monotonic()
            if time.monotonic() - last_ping > KEEPALIVE_S:
                yield ": keep-alive\n\n"
                last_ping = time.monotonic()
            await asyncio.sleep(POLL_S)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
