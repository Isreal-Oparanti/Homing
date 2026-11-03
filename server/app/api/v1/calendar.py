"""The calendar feed: every date and moment, delivered by the person's own calendar
(docs/07-api.md#calendar). Homing has no push, so a feed is how a save reaches you when
you're not in the app: your phone's calendar reminds you, and the event links back.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.when_needed import explain_now
from app.calendar_ics import Event, calendar
from app.core.auth import CurrentUser, calendar_token, require_user, user_from_calendar_token
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.models import Card, Check, Moment, Reading, Save, Thread, ThreadSave, When
from app.db.session import get_db

router = APIRouter(tags=["calendar"])

FEED_PAST = timedelta(days=30)
FEED_AHEAD = timedelta(days=365)


class FeedOut(BaseModel):
    https_url: str
    webcal_url: str  # opens Apple Calendar and most phone calendars
    google_url: str  # adds it to Google Calendar


@router.get("/me/calendar", response_model=FeedOut)
def my_feed(
    user: CurrentUser = Depends(require_user), settings: Settings = Depends(get_settings)
) -> FeedOut:
    """The person's private feed link. Anyone with it can see the titles and dates in it."""
    token = calendar_token(user.id, settings.proxy_secret)
    https = f"{settings.public_api_url.rstrip('/')}/api/v1/calendar/{token}.ics"
    webcal = "webcal://" + https.split("://", 1)[1]
    return FeedOut(
        https_url=https,
        webcal_url=webcal,
        google_url=f"https://calendar.google.com/calendar/r?cid={quote(webcal, safe='')}",
    )


def _goals(db: Session, save_ids: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for save_id, title in db.execute(
        select(ThreadSave.save_id, Thread.title)
        .join(Thread, Thread.id == ThreadSave.thread_id)
        .where(ThreadSave.save_id.in_(save_ids), Thread.archived_at.is_(None))
    ):
        out.setdefault(save_id, []).append(title)
    return out


def feed_events(db: Session, user_id: str, web: str, now: datetime) -> list[Event]:
    """Dated saves (reminded when Homing brings them back) and moments (the day before)."""
    rows = db.execute(
        select(Save, Reading, When)
        .join(Reading, Reading.save_id == Save.id)
        .join(When, When.save_id == Save.id)
        .outerjoin(Check, Check.save_id == Save.id)
        .where(
            Save.user_id == user_id,
            Save.visibility == "normal",
            When.kind == "date",
            When.due_at > now - FEED_PAST,
            When.due_at < now + FEED_AHEAD,
            or_(Check.verdict.is_(None), Check.verdict != "not_for_you"),
        )
    ).all()
    goals = _goals(db, [s.id for s, _, _ in rows])
    events: list[Event] = []
    for save, reading, when in rows:
        assert when.due_at is not None
        link = f"{web}/saves/{save.id}"
        about = explain_now(when, now)
        if goals.get(save.id):
            about += f" Goal: {', '.join(goals[save.id])}."
        back = when.bring_back_at
        events.append(
            Event(
                uid=f"save-{save.id}@homing",
                start=when.due_at,
                summary=reading.title,
                description=f"{about}\n\nOpen it in Homing: {link}",
                url=link,
                alarms=[back] if back and back < when.due_at else ["-P1D"],
            )
        )

    moments = db.scalars(
        select(Moment).where(
            Moment.user_id == user_id,
            Moment.at > now - timedelta(days=7),
            Moment.at < now + FEED_AHEAD,
        )
    ).all()
    preps = {
        c.moment_id: c.id
        for c in db.scalars(
            select(Card).where(Card.user_id == user_id, Card.moment_id.in_([m.id for m in moments]))
        )
    }
    named = select(Thread.id, Thread.title).where(Thread.user_id == user_id)
    titles = {i: t for i, t in db.execute(named)}
    for m in moments:
        names = [titles[t] for t in m.thread_ids or [] if t in titles]
        link = f"{web}/cards/{preps[m.id]}" if m.id in preps else f"{web}/today"
        what = (
            f"Your saves in {', '.join(names)} can help. Homing makes a prep sheet the day before."
            if names
            else "Homing looks for the saves that can help."
        )
        events.append(
            Event(
                uid=f"moment-{m.id}@homing",
                start=m.at,
                summary=m.text[:1].upper() + m.text[1:],
                description=f"{what}\n\nOpen it in Homing: {link}",
                url=link,
                minutes=60,
                alarms=["-P1D", "-PT1H"],
            )
        )
    return events


@router.get("/calendar/{token}.ics")
def feed(
    token: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> Response:
    """The feed itself: public, because calendar apps can't sign in; the token is the key."""
    user_id = user_from_calendar_token(token, settings.proxy_secret)
    if user_id is None:
        raise AppError("not_found", "No calendar here.", status=404)
    now = datetime.now(UTC)
    events = feed_events(db, user_id, settings.web_url.rstrip("/"), now)
    return Response(
        calendar(events, name="Homing", now=now),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )
