"""The other three answers: Is it true? (checks), What's it for? (threads), When? (whens).

See docs/02-data-model.md.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now
from app.db.ids import uuid7


class Check(Base):
    """The answer to "Is it true?". The verdict is decided by code, never by a model."""

    __tablename__ = "checks"

    save_id: Mapped[str] = mapped_column(
        ForeignKey("saves.id", ondelete="CASCADE"), primary_key=True
    )
    verdict: Mapped[str] = mapped_column(Text)
    official_url: Mapped[str | None] = mapped_column(Text)
    official_found_by: Mapped[str | None] = mapped_column(Text)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_source_text: Mapped[str | None] = mapped_column(Text)
    deadline_tz_stated: Mapped[bool] = mapped_column(Boolean, default=False)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    eligibility: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    question_for_user: Mapped[str | None] = mapped_column(Text)
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # this one only
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # one per list item
    note: Mapped[str | None] = mapped_column(Text)  # plain words when we couldn't check
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)


class Thread(Base):
    """A goal the user's saves serve, e.g. "Getting into YC"."""

    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text, default="agent")
    locked_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ThreadSave(Base):
    __tablename__ = "thread_saves"

    thread_id: Mapped[str] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True
    )
    save_id: Mapped[str] = mapped_column(
        ForeignKey("saves.id", ondelete="CASCADE"), primary_key=True
    )
    added_by: Mapped[str] = mapped_column(Text, default="agent")
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class When(Base):
    """The answer to "When will you need it?"."""

    __tablename__ = "whens"

    save_id: Mapped[str] = mapped_column(
        ForeignKey("saves.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(Text)  # date · moment · none
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bring_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moment_id: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # reading · check · thread · user
    source_text: Mapped[str | None] = mapped_column(Text)  # the exact date words
    tz_stated: Mapped[bool] = mapped_column(Boolean, default=False)
    time_stated: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
