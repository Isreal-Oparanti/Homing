"""The team feed: a page of past events, and a live stream of new ones (docs/07-api.md)."""

import asyncio
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_user
from app.db.models import AgentEvent
from app.db.repo import events as events_repo
from app.db.session import get_db, session_factory

router = APIRouter(tags=["team"])

POLL_S = 0.75
KEEPALIVE_S = 15.0
STREAM_MAX_S = 600.0


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
        yield "retry: 2000\n\n"
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
