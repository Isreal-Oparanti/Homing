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


class ListItem(BaseModel):
    """One entry in a save that lists several things, e.g. one of 18 funding opportunities."""

    name: str = Field(description="The item's name as written, e.g. 'TripleFunds'.")
    url: str | None = Field(default=None, description="Its link if the save shows one, else null.")
    note: str | None = Field(default=None, description="What the save says about it, if anything.")


class Reading(BaseModel):
    """The answer to "What is it?"."""

    title: str = Field(description="Short, plain title, at most 80 characters.")
    what: str = Field(description="One plain sentence saying what this is, at most 160 characters.")
    key_facts: KeyFacts = Field(default_factory=KeyFacts)
    is_checkable: bool = Field(
        description="True only for claims an official source could confirm: deadlines, "
        "eligibility, prices, offers, availability, event dates."
    )
    is_opportunity: bool = Field(
        description="True for grants, programmes, jobs, competitions, scholarships, hackathons."
    )
    items: list[ListItem] = Field(
        default_factory=list,
        max_length=25,
        description="Only when the save lists several separate things; else empty.",
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


class ProposedFinding(BaseModel):
    point: str = Field(
        description="One plain sentence for the person, e.g. 'It's on-site in Cairo.'"
    )
    quote: str = Field(description="Copied word for word from SOURCE, 3 to 40 words.")
    kind: Literal["left_out", "differs", "confirmed"]


class LanguageNeed(BaseModel):
    code: str = Field(description="ISO 639-1 language code, e.g. 'en' or 'fr'.")
    level: Literal["basic", "working", "fluent"]


class ProposedRule(BaseModel):
    """One eligibility rule from the official page. Code checks the quote and judges it."""

    rule: Literal[
        "age", "nationality", "residence", "student", "education", "language", "company", "other"
    ]
    strength: Literal["required", "preferred"]
    quote: str = Field(description="The rule's words, copied exactly from SOURCE.")
    plain: str = Field(
        description="The rule in plain words, e.g. 'Aged 20-32 in the year you apply'."
    )
    min_age: int | None = None
    max_age: int | None = None
    countries: list[str] = Field(
        default_factory=list, description="ISO alpha-2 codes, or ['ANY'] when open to everyone."
    )
    student_status: Literal["full_time", "any_student"] | None = None
    education_levels: list[Literal["secondary", "undergraduate", "postgraduate", "graduate"]] = (
        Field(default_factory=list)
    )
    languages_any: list[LanguageNeed] = Field(
        default_factory=list, description="At least one of these is needed."
    )
    languages_all: list[LanguageNeed] = Field(
        default_factory=list, description="All of these are needed."
    )
    company_registered: bool | None = None
    question: str | None = Field(
        default=None, description="For 'other' only: a yes/no question for the person."
    )
    yes_meets: bool = Field(default=True, description="For 'other': does 'yes' mean they meet it?")


class ProposedCheck(BaseModel):
    """What the model proposes for "Is it true?". Code verifies every quote before showing it."""

    is_same_opportunity: bool = Field(
        description="True if SOURCE is the opportunity or offer the SAVE is about."
    )
    findings: list[ProposedFinding] = Field(default_factory=list, max_length=8)
    deadline_quote: str | None = Field(
        default=None, description="The exact words from SOURCE giving the closing date, or null."
    )
    rules: list[ProposedRule] = Field(default_factory=list, max_length=10)


class Placement(BaseModel):
    """Where one save goes: an existing thread, a new goal, or nowhere if it's unclear."""

    thread_id: str | None = Field(default=None, description="An id from THREADS, or null.")
    new_thread_title: str | None = Field(
        default=None, description="A new goal, 2-5 words, e.g. 'Getting into YC'. Or null."
    )
    reason: str = Field(description="One short line on why it serves that goal.")


class VideoPoint(BaseModel):
    point: str = Field(
        description="One practical thing to do, in plain words, e.g. 'Pause before key points.'"
    )
    t_start: int = Field(description="The second this point starts, from a transcript line.")
    t_end: int = Field(description="The second it ends.")
    quote: str = Field(
        description="Words copied exactly from the transcript between t_start and t_end."
    )


class VideoPoints(BaseModel):
    """What one video says that helps with the moment. Code checks every second and quote."""

    points: list[VideoPoint] = Field(default_factory=list, max_length=6)


class Cite(BaseModel):
    video: str = Field(description="A video id from POINTS, e.g. 'V3'.")
    t: int = Field(description="The t_start of a point from that video, exactly as given.")


class SheetItem(BaseModel):
    text: str = Field(description="One plain sentence.")
    cites: list[Cite] = Field(min_length=1)


class Disagreement(BaseModel):
    topic: str
    sides: list[SheetItem] = Field(min_length=2, max_length=3)


class PrepSheet(BaseModel):
    """The prep sheet for a moment, built only from verified points (docs/03, card.prep)."""

    agree: list[SheetItem] = Field(default_factory=list, max_length=6)
    disagree: list[Disagreement] = Field(default_factory=list, max_length=3)
    checklist: list[SheetItem] = Field(default_factory=list, max_length=5)


class FileReading(Reading):
    """A reading of an image or scanned PDF, with every word on it as our copy of the content."""

    text: str = Field(description="All readable text, word for word, in reading order.")
