"""Search by meaning and Ask (S10, ADR 0003)."""

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now
from app.db.ids import uuid7


class SaveEmbedding(Base):
    """One vector per save's reading. Private saves are never embedded."""

    __tablename__ = "save_embeddings"

    save_id: Mapped[str] = mapped_column(
        ForeignKey("saves.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(Text)  # unchanged text: no need to embed again
    embedding: Mapped[Any] = mapped_column(Vector(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Ask(Base):
    """One question, one answer page."""

    __tablename__ = "asks"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="working")  # working · done · failed
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
