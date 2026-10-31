"""Today: at most three things that need you now (docs/07-api.md#today-and-cards).

Rough version (S4): dated saves due within a week, soonest first. Cards, the tick and
dismissals arrive in S11.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents import is_it_true
from app.core.auth import CurrentUser, require_user
from app.db.models import Check, Reading, User, When
from app.db.repo import answers as answers_repo
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.verify.dates import display
from app.verify.eligibility import assess

router = APIRouter(tags=["today"])

MAX_CARDS = 3
WINDOW = timedelta(days=7)


class TodayCard(BaseModel):
    save_id: str
    kind: str  # deadline
    title: str
    why_now: str
    next_step: str
    due_at: datetime
    tz_stated: bool
    unconfirmed: bool  # the date comes from the post, not the official page


class TodayOut(BaseModel):
    date: str
    cards: list[TodayCard]


def next_step(reading: Reading, check: Check | None, questions: int = 0) -> str:
    """What to do now, decided by code from what the agents found."""
    if check is not None and check.verdict == "needs_your_answer" and questions:
        asks = "question" if questions == 1 else f"{questions} questions"
        return f"Answer {'a ' if questions == 1 else ''}{asks} to see if it fits you."
    if check is not None and check.verdict == "fits_you":
        return "It fits you. Apply before it closes."
    findings = check.findings if check else []
    gaps = [f for f in findings if f.get("kind") in ("left_out", "differs")]
    if gaps:
        things = "thing" if len(gaps) == 1 else "things"
        return f"Read the {len(gaps)} {things} the post left out, then decide."
    if reading.is_opportunity:
        return "Decide whether to apply before it closes."
    return "Open it before then."


def _why_now(when: When, user_tz: str) -> str:
    assert when.due_at is not None
    verb = "Closes" if when.source == "check" or "Closes" in when.explanation else "On"
    return f"{verb} {display(when.due_at, user_tz)}"


def _open_questions(db: Session, user_id: str, check: Check | None) -> int:
    if check is None or check.verdict != "needs_your_answer":
        return 0
    facts = is_it_true.facts_for(db, user_id, check)
    ref_year = (check.deadline_at or datetime.now(UTC)).year
    return len(assess(check.eligibility or [], facts, ref_year=ref_year).questions)


@router.get("/today", response_model=TodayOut)
def today(
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> TodayOut:
    ensure_user(db, user)
    owner = db.get(User, user.id)
    user_tz = owner.tz if owner else "Africa/Lagos"
    now = datetime.now(UTC)
    rows = answers_repo.due_soon(db, user.id, now=now, within=WINDOW, limit=MAX_CARDS)
    cards = [
        TodayCard(
            save_id=save.id,
            kind="deadline",
            title=reading.title,
            why_now=_why_now(when, user_tz),
            next_step=next_step(reading, check, _open_questions(db, user.id, check)),
            due_at=when.due_at,  # type: ignore[arg-type]
            tz_stated=when.tz_stated,
            unconfirmed=when.source != "check",
        )
        for save, reading, when, check in rows
    ]
    local = now.astimezone(ZoneInfo(user_tz))
    return TodayOut(date=local.date().isoformat(), cards=cards)
