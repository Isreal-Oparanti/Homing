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
from app.db.models import AgentEvent, Save, Thread, ThreadSave, User
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


class GoalDot(BaseModel):
    id: str
    title: str
    saves: int


class Overview(BaseModel):
    """What the agents map and the clock strip draw: all real counts, none made up."""

    saves: int
    goals: list[GoalDot]  # the largest goals, biggest first
    goal_of: dict[str, str]  # save id -> one of those goals, so a live event can land on it
    date: str
    hours: dict[str, list[int]]  # agent -> events in each hour of today, the person's time
    hour_now: int


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
