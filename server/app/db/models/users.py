from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    tz: Mapped[str] = mapped_column(String(64), default="Africa/Lagos")
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Profile(Base):
    """What the person has told Homing, used only by Is it true? for eligibility.

    Filled one answer at a time from questions on save cards, never a form up front.
    Judged by code only; never sent to a closed model (docs/09-security-privacy.md).
    """

    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    birth_year: Mapped[int | None] = mapped_column(Integer)
    nationality: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)  # ISO alpha-2
    residence_country: Mapped[str | None] = mapped_column(Text)
    student_status: Mapped[str | None] = mapped_column(Text)  # full_time · part_time · not_student
    education_level: Mapped[str | None] = mapped_column(Text)
    languages: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)  # {"fr": "basic"}
    company_stage: Mapped[str | None] = mapped_column(Text)
    company_registered: Mapped[bool | None] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
