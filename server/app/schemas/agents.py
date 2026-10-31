"""What the agents get back from models. Validated on every call (docs/06-models.md)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DateFact(BaseModel):
    text: str = Field(description="The date words exactly as written, e.g. 'closes TOMORROW'.")
    role: Literal["deadline", "event", "published", "other"] = "other"


class TextFact(BaseModel):
    text: str


class KeyFacts(BaseModel):
    dates: list[DateFact] = Field(default_factory=list)
    amounts: list[TextFact] = Field(default_factory=list)
    requirements: list[TextFact] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    organisations: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)


class Reading(BaseModel):
    """The answer to "What is it?"."""

    title: str = Field(description="Short, plain title, at most 80 characters.")
    what: str = Field(description="One plain sentence saying what this is, at most 160 characters.")
    key_facts: KeyFacts = Field(default_factory=KeyFacts)
    is_checkable: bool = Field(
        description="True if it states dates, requirements, prices or outside claims."
    )
    is_opportunity: bool = Field(
        description="True for grants, programmes, jobs, competitions, scholarships, hackathons."
    )

    @field_validator("title")
    @classmethod
    def _short_title(cls, v: str) -> str:
        v = " ".join(v.split())
        return v if len(v) <= 80 else v[:79].rstrip() + "…"

    @field_validator("what")
    @classmethod
    def _short_what(cls, v: str) -> str:
        v = " ".join(v.split())
        return v if len(v) <= 200 else v[:199].rstrip() + "…"
