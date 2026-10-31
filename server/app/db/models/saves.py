"""Saves and what we keep about them. See docs/02-data-model.md."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Numeric, Text
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now
from app.db.ids import uuid7


class Media(Base):
    __tablename__ = "media"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    storage_key: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Text)
    duration_s: Mapped[float | None] = mapped_column(Numeric)
    original_bytes: Mapped[int | None] = mapped_column(BigInteger)
    thumb_key: Mapped[str | None] = mapped_column(Text)
    compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    original_filename: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (Index("ix_media_user_sha256", "user_id", "sha256"),)


class Import(Base):
    __tablename__ = "imports"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    storage_key: Mapped[str] = mapped_column(Text)
    format: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="received")
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Save(Base):
    __tablename__ = "saves"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    import_id: Mapped[str | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"))
    url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    media_id: Mapped[str | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    media_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)  # all files, in order
    content_hash: Mapped[str] = mapped_column(Text)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status: Mapped[str] = mapped_column(Text, default="received")
    visibility: Mapped[str] = mapped_column(Text, default="normal")
    private_reason: Mapped[str | None] = mapped_column(Text)
    duplicate_of: Mapped[str | None] = mapped_column(ForeignKey("saves.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        Index("ix_saves_user_saved_at", "user_id", sql("saved_at DESC")),
        Index("ix_saves_user_content_hash", "user_id", "content_hash"),
        Index(
            "ix_saves_in_progress",
            "status",
            postgresql_where=sql("status IN ('received', 'reading')"),
        ),
    )


class Snapshot(Base):
    """Our copy of a save's content at save time, so a dead link doesn't lose it."""

    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    save_id: Mapped[str] = mapped_column(ForeignKey("saves.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Reading(Base):
    """The answer to "What is it?"."""

    __tablename__ = "readings"

    save_id: Mapped[str] = mapped_column(
        ForeignKey("saves.id", ondelete="CASCADE"), primary_key=True
    )
    title: Mapped[str] = mapped_column(Text)
    what: Mapped[str] = mapped_column(Text)
    key_facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_checkable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_opportunity: Mapped[bool] = mapped_column(Boolean, default=False)
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
