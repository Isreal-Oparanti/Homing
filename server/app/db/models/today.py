"""Today (S11): moments the person types, and the cards Today shows (docs/02 · cards)."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text
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
