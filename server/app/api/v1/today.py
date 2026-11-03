"""Today, moments and card actions (docs/07-api.md#today-and-cards).

Today is composed when it's opened (app/agents/today.py): at most three new cards a day,
chosen by code.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.today import act, ask_for_sheet, compose
from app.core.auth import CurrentUser, require_user
from app.core.errors import AppError
from app.db.models import Card, Check, Moment, Reading, Save, Thread, ThreadSave, User, When
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs import queue
from app.verify.dates import display, parse_moment

router = APIRouter(tags=["today"])


class CardOut(BaseModel):
    id: str
    kind: str  # deadline · prep
    title: str
    why_now: str
    next_step: str
    save_id: str | None
    thread_ids: list[str]
    due_at: datetime | None
    tz_stated: bool
    unconfirmed: bool  # the date comes from the post, not the official page

    @classmethod
    def of(cls, card: Card) -> "CardOut":
        return cls(
            id=card.id,
            kind=card.kind,
            title=card.title,
            why_now=card.why_now,
            next_step=card.next_step,
            save_id=card.save_id,
            thread_ids=list(card.thread_ids or []),
            due_at=card.due_at,
            tz_stated=bool(card.payload.get("tz_stated", True)),
            unconfirmed=bool(card.payload.get("unconfirmed", False)),
        )


class CardDetail(CardOut):
    """A card with what a job made for it: a prep card's sheet (agree, disagree, checklist,
    the videos each point is from, and the reel)."""

    sheet: dict[str, Any] | None

    @classmethod
    def detail(cls, card: Card) -> "CardDetail":
        return cls(**CardOut.of(card).model_dump(), sheet=card.payload.get("sheet"))


class GoalOut(BaseModel):
    id: str
    title: str


class MomentOut(BaseModel):
    id: str
    text: str
    at: datetime
    display: str
    threads: list[GoalOut]  # empty until When will you need it? has matched them


class ComingBack(BaseModel):
    """A save already set to come back: when it returns, and the date it's for."""

    save_id: str
    title: str
    back_on: str
    due: str


class TodayOut(BaseModel):
    date: str
    cards: list[CardOut]
    moments: list[MomentOut]
    coming_back: list[ComingBack]


COMING_BACK_SHOWN = 3


def _coming_back(db: Session, user_id: str, now: datetime, tz: str) -> list[ComingBack]:
    rows = db.execute(
        select(Save.id, Reading.title, When.bring_back_at, When.due_at)
        .join(Reading, Reading.save_id == Save.id)
        .join(When, When.save_id == Save.id)
        .outerjoin(Check, Check.save_id == Save.id)
        .where(
            Save.user_id == user_id,
            Save.visibility == "normal",
            When.kind == "date",
            When.bring_back_at > now,
            When.due_at > now,
            or_(Check.verdict.is_(None), Check.verdict.notin_(("not_for_you", "closed"))),
        )
        .order_by(When.bring_back_at)
        .limit(COMING_BACK_SHOWN)
    ).all()
    return [
        ComingBack(save_id=i, title=t, back_on=display(b, tz), due=display(d, tz))
        for i, t, b, d in rows
    ]


class MomentIn(BaseModel):
    text: str = Field(min_length=3, max_length=200)


class ActIn(BaseModel):
    action: str = Field(pattern="^(use|dismiss|later)$")


def _owner(db: Session, user: CurrentUser) -> User:
    ensure_user(db, user)
    owner = db.get(User, user.id)
    assert owner is not None
    return owner


def _moment_out(db: Session, moment: Moment, tz: str) -> MomentOut:
    goals = db.execute(
        select(Thread.id, Thread.title).where(Thread.id.in_(moment.thread_ids or []))
    ).all()
    return MomentOut(
        id=moment.id,
        text=moment.text,
        at=moment.at,
        display=display(moment.at, tz),
        threads=[GoalOut(id=i, title=t) for i, t in goals],
    )


@router.get("/today", response_model=TodayOut)
def today(user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)) -> TodayOut:
    owner = _owner(db, user)
    now = datetime.now(UTC)
    cards = compose(db, owner, now)
    moments = db.scalars(
        select(Moment).where(Moment.user_id == user.id, Moment.at > now).order_by(Moment.at)
    ).all()
    db.commit()
    return TodayOut(
        date=now.astimezone(ZoneInfo(owner.tz)).date().isoformat(),
        cards=[CardOut.of(c) for c in cards],
        moments=[_moment_out(db, m, owner.tz) for m in moments],
        coming_back=_coming_back(db, user.id, now, owner.tz),
    )


@router.post("/moments", status_code=202, response_model=MomentOut)
def add_moment(
    body: MomentIn, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> MomentOut:
    """Something coming up, in the person's words. Code reads the day and time; When will you
    need it? then finds the goals whose saves would help."""
    owner = _owner(db, user)
    now = datetime.now(UTC)
    when = parse_moment(body.text, now=now, user_tz=owner.tz)
    if when is None or when.at <= now:
        raise AppError(
            "no_day",
            "Say when, e.g. 'recording my demo on Tuesday evening' or 'pitch on 9 November'.",
            status=422,
        )
    moment = Moment(user_id=user.id, text=" ".join(body.text.split()), at=when.at)
    db.add(moment)
    db.flush()
    queue.enqueue(
        db,
        "moment.match",
        {"moment_id": moment.id},
        user_id=user.id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"moment:{moment.id}",
    )
    db.commit()
    return _moment_out(db, moment, owner.tz)


@router.delete("/moments/{moment_id}", status_code=204)
def remove_moment(
    moment_id: str, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> Response:
    moment = db.scalar(select(Moment).where(Moment.id == moment_id, Moment.user_id == user.id))
    if moment is None:
        raise AppError("moment_not_found", "That moment doesn't exist.", status=404)
    db.delete(moment)
    db.commit()
    return Response(status_code=204)


@router.get("/cards/{card_id}", response_model=CardDetail)
def get_card(
    card_id: str, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> CardDetail:
    card = db.scalar(select(Card).where(Card.id == card_id, Card.user_id == user.id))
    if card is None:
        raise AppError("card_not_found", "That card doesn't exist.", status=404)
    if card.kind == "prep" and "sheet" not in card.payload:
        ask_for_sheet(db, card)
        db.commit()
    return CardDetail.detail(card)


@router.post("/cards/{card_id}/act", response_model=CardOut)
def act_on_card(
    card_id: str,
    body: ActIn,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> CardOut:
    card = db.scalar(select(Card).where(Card.id == card_id, Card.user_id == user.id))
    if card is None:
        raise AppError("card_not_found", "That card doesn't exist.", status=404)
    act(db, _owner(db, user), card, body.action, datetime.now(UTC))
    db.commit()
    return CardOut.of(card)


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@router.get("/saves/{save_id}/calendar.ics")
def calendar_file(
    save_id: str, user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> Response:
    """The save's date as a calendar event, with a reminder a day before."""
    row = db.execute(
        select(Save, Reading, When)
        .join(Reading, Reading.save_id == Save.id)
        .join(When, When.save_id == Save.id)
        .where(Save.id == save_id, Save.user_id == user.id, Save.visibility == "normal")
    ).first()
    if row is None or row[2].due_at is None:
        raise AppError("no_date", "This save has no date to put in a calendar.", status=404)
    save, reading, when = row
    assert when.due_at is not None
    stamp = "%Y%m%dT%H%M%SZ"
    start = when.due_at.astimezone(UTC)
    goals = db.scalars(
        select(Thread.title).join(ThreadSave).where(ThreadSave.save_id == save.id)
    ).all()
    about = when.explanation + (f" Goal: {', '.join(goals)}." if goals else "")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Homing//Homing//EN",
        "BEGIN:VEVENT",
        f"UID:{save.id}@homing",
        f"DTSTAMP:{datetime.now(UTC):{stamp}}",
        f"DTSTART:{start:{stamp}}",
        f"DTEND:{start + timedelta(minutes=30):{stamp}}",
        f"SUMMARY:{_ics_text(reading.title)}",
        f"DESCRIPTION:{_ics_text(about)}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ics_text(reading.title)}",
        "TRIGGER:-P1D",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return Response(
        "\r\n".join(lines) + "\r\n",
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="homing.ics"'},
    )
