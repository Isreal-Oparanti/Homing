"""The team feed, always scoped to one user."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AgentEvent


def list_events(
    db: Session,
    user_id: str,
    *,
    before_id: int | None = None,
    limit: int = 50,
    agent: str | None = None,
) -> Sequence[AgentEvent]:
    """Newest first. Page backwards with `before_id`."""
    q = select(AgentEvent).where(AgentEvent.user_id == user_id)
    if before_id is not None:
        q = q.where(AgentEvent.id < before_id)
    if agent is not None:
        q = q.where(AgentEvent.agent == agent)
    return db.scalars(q.order_by(AgentEvent.id.desc()).limit(limit)).all()


def events_after(
    db: Session, user_id: str, after_id: int, limit: int = 100
) -> Sequence[AgentEvent]:
    """Oldest first, for the live stream."""
    q = (
        select(AgentEvent)
        .where(AgentEvent.user_id == user_id, AgentEvent.id > after_id)
        .order_by(AgentEvent.id)
        .limit(limit)
    )
    return db.scalars(q).all()


def latest_event_id(db: Session, user_id: str) -> int:
    q = select(func.coalesce(func.max(AgentEvent.id), 0)).where(AgentEvent.user_id == user_id)
    return int(db.scalar(q) or 0)
