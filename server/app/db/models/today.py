"""Today (S11): moments the person types, and the cards Today shows (docs/02 · cards)."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now
from app.db.ids import uuid7


class Moment(Base):
    """Something coming up, in the person's words: "recording my demo on Tuesday evening"."""

    __tablename__ = "moments"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    thread_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)  # goals it needs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Card(Base):
    """One thing on Today. Created once (dedupe_key), shown at most 3 new a day."""

    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)  # deadline · prep
    save_id: Mapped[str | None] = mapped_column(ForeignKey("saves.id", ondelete="CASCADE"))
    moment_id: Mapped[str | None] = mapped_column(ForeignKey("moments.id", ondelete="CASCADE"))
    thread_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    title: Mapped[str] = mapped_column(Text)
    why_now: Mapped[str] = mapped_column(Text)
    next_step: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(Text, default="new")  # new · used · dismissed · later · gone
    surfaced_on: Mapped[date | None] = mapped_column(Date)  # the person's day it entered Today
    later_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Find(Base):
    """Something What's it for? found on the web for one of the person's goals (finds_more).

    Only what passed code's checks is kept: an official page, quotes found on it word for word,
    a closing date ahead, and who can apply judged by code against the person's profile.
    """

    __tablename__ = "finds"
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_finds_user_url"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    from_save_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)  # what led to it
    name: Mapped[str] = mapped_column(Text)
    what: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_text: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(Text)  # fits_you · needs_your_answer · checked
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # judged by code
    quotes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # {label, quote}
    state: Mapped[str] = mapped_column(Text, default="new")  # new · kept · dismissed
    save_id: Mapped[str | None] = mapped_column(ForeignKey("saves.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
