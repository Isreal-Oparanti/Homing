"""Today: at most three things that need you now, chosen by code (docs/03 · Compose Today).

When will you need it? decides. Cards are made from what's due back and from moments the
person typed ("recording my demo on Tuesday evening"), scored by a fixed formula, and at most
three new ones enter Today each day. A dismissed card never comes back; "later" brings it back
the next morning. Today is composed when it's opened: there's no push, so a timer would add
nothing the person sees.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agents import is_it_true
from app.db.models import Card, Check, Moment, Reading, Save, Thread, ThreadSave, User, When
from app.events.emitter import emit
from app.jobs import queue
from app.jobs.errors import PermanentError
from app.jobs.runner import JobContext
from app.llm.gateway import ModelGateway
from app.schemas.agents import MomentMatch
from app.verify.dates import display
from app.verify.eligibility import assess

MAX_NEW_A_DAY = 3
PREP_WITHIN = timedelta(hours=36)
PREP_MIN_SAVES = 3
FATIGUE_DAYS = 14
MORNING = time(9, 0)

# Tests swap this for a fake; agents never build clients themselves.
gateway_factory: Any = ModelGateway


def priority(
    due_at: datetime,
    now: datetime,
    *,
    opportunity: bool = False,
    prep: bool = False,
    thread_saves: int = 0,
    dismissals: int = 0,
) -> int:
    """urgency + importance − fatigue (docs/03 · Compose Today)."""
    left = due_at - now
    if left < timedelta(hours=24):
        urgency = 100
    elif left < timedelta(hours=72):
        urgency = 70
    elif left < timedelta(days=7):
        urgency = 40
    else:
        urgency = 10
    importance = (20 if opportunity else 0) + (15 if prep else 0) + (10 if thread_saves >= 5 else 0)
    return urgency + importance - 15 * dismissals


def next_step(reading: Reading, check: Check | None, questions: int = 0) -> str:
    """What to do now, decided by code from what the agents found."""
    if check is not None and check.verdict == "closed":
        return "Applications are closed. If you're in, this is your next date."
    if check is not None and check.verdict == "needs_your_answer" and questions:
        asks = "question" if questions == 1 else f"{questions} questions"
        return f"Answer {'a ' if questions == 1 else ''}{asks} to see if it fits you."
    if check is not None and check.verdict == "fits_you":
        return "It fits you. Apply before it closes."
    gaps = [
        f for f in (check.findings if check else []) if f.get("kind") in ("left_out", "differs")
    ]
    if gaps:
        things = "thing" if len(gaps) == 1 else "things"
        return f"Read the {len(gaps)} {things} the post left out, then decide."
    if reading.is_opportunity:
        return "Decide whether to apply before it closes."
    return "Open it before then."


def _why_now(when: When, tz: str) -> str:
    assert when.due_at is not None
    verb = "Closes" if when.source == "check" or "Closes" in when.explanation else "On"
    return f"{verb} {display(when.due_at, tz)}"


def _unconfirmed(when: When, check: Check | None) -> bool:
    """The date comes from the post, not the official page. A closed save's next date was
    read on the page the check opened."""
    if when.source == "check":
        return False
    return not (
        check is not None
        and check.verdict == "closed"
        and when.explanation.startswith("Applications closed")
    )


def _open_questions(db: Session, user_id: str, check: Check | None) -> int:
    if check is None or check.verdict != "needs_your_answer":
        return 0
    facts = is_it_true.facts_for(db, user_id, check)
    ref_year = (check.deadline_at or datetime.now(UTC)).year
    return len(assess(check.eligibility or [], facts, ref_year=ref_year).questions)


def _threads(db: Session, user_id: str) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Each save's goals, and how many saves each goal holds."""
    rows = db.execute(
        select(ThreadSave.save_id, ThreadSave.thread_id)
        .join(Thread, Thread.id == ThreadSave.thread_id)
        .where(Thread.user_id == user_id, Thread.archived_at.is_(None))
    ).all()
    of: dict[str, list[str]] = {}
    size: dict[str, int] = {}
    for save_id, thread_id in rows:
        of.setdefault(save_id, []).append(thread_id)
        size[thread_id] = size.get(thread_id, 0) + 1
    return of, size


def _candidates(db: Session, user: User, now: datetime) -> list[dict[str, Any]]:
    tz = user.tz
    dismissed = db.execute(
        select(Card.save_id, Card.moment_id, Card.thread_ids, Card.updated_at).where(
            Card.user_id == user.id, Card.state == "dismissed"
        )
    ).all()
    gone_saves = {s for s, _, _, _ in dismissed if s}
    gone_moments = {m for _, m, _, _ in dismissed if m}
    recent = [
        set(t or []) for _, _, t, at in dismissed if at and at > now - timedelta(days=FATIGUE_DAYS)
    ]
    threads_of, size = _threads(db, user.id)

    def tired(thread_ids: list[str]) -> int:
        return sum(1 for d in recent if d & set(thread_ids))

    out: list[dict[str, Any]] = []
    rows = db.execute(
        select(Save, Reading, When, Check)
        .join(Reading, Reading.save_id == Save.id)
        .join(When, When.save_id == Save.id)
        .outerjoin(Check, Check.save_id == Save.id)
        .where(
            Save.user_id == user.id,
            Save.visibility == "normal",
            When.kind == "date",
            When.bring_back_at <= now,
            When.due_at > now,
            # A closed save stays only while its page has a date ahead (the "when" moved on).
            or_(Check.verdict.is_(None), Check.verdict != "not_for_you"),
        )
    ).all()
    for save, reading, when, check in rows:
        if save.id in gone_saves:
            continue
        goals = threads_of.get(save.id, [])
        assert when.due_at is not None
        out.append(
            {
                "kind": "deadline",
                "save_id": save.id,
                "moment_id": None,
                "thread_ids": goals,
                "title": reading.title,
                "why_now": _why_now(when, tz),
                "next_step": next_step(reading, check, _open_questions(db, user.id, check)),
                "due_at": when.due_at,
                "payload": {"tz_stated": when.tz_stated, "unconfirmed": _unconfirmed(when, check)},
                "priority": priority(
                    when.due_at,
                    now,
                    opportunity=reading.is_opportunity,
                    thread_saves=max((size.get(t, 0) for t in goals), default=0),
                    dismissals=tired(goals),
                ),
                "dedupe_key": f"deadline:{save.id}:{when.due_at:%Y%m%d}",
            }
        )

    moments = db.scalars(
        select(Moment).where(
            Moment.user_id == user.id, Moment.at > now, Moment.at <= now + PREP_WITHIN
        )
    ).all()
    for moment in moments:
        held = sum(size.get(t, 0) for t in moment.thread_ids)
        if moment.id in gone_moments or held < PREP_MIN_SAVES:
            continue
        titles = db.scalars(select(Thread.title).where(Thread.id.in_(moment.thread_ids))).all()
        out.append(
            {
                "kind": "prep",
                "save_id": None,
                "moment_id": moment.id,
                "thread_ids": list(moment.thread_ids),
                "title": f"Get ready: {moment.text}",
                "why_now": display(moment.at, tz),
                "next_step": (
                    f"{held} of your saves can help: {', '.join(titles)}. Go over them first."
                ),
                "due_at": moment.at,
                "payload": {"saves": held, "threads": list(titles)},
                "priority": priority(
                    moment.at,
                    now,
                    prep=True,
                    thread_saves=held,
                    dismissals=tired(moment.thread_ids),
                ),
                "dedupe_key": f"prep:{moment.id}",
            }
        )
    return out


def compose(db: Session, user: User, now: datetime) -> list[Card]:
    """Today's cards: refresh the candidates, then let at most three new ones in today."""
    today: date = now.astimezone(ZoneInfo(user.tz)).date()
    # "Later" cards whose time has come wait their turn again.
    db.execute(
        update(Card)
        .where(Card.user_id == user.id, Card.state == "later", Card.later_until <= now)
        .values(state="new", surfaced_on=None, later_until=None)
    )
    candidates = _candidates(db, user, now)
    live = {c["dedupe_key"] for c in candidates}
    for c in candidates:
        stmt = insert(Card).values(user_id=user.id, state="new", **c)
        fresh: dict[str, Any] = {
            k: stmt.excluded[k] for k in ("title", "why_now", "next_step", "priority")
        }
        # Merged, so what a job added (a prep card's sheet) stays.
        fresh["payload"] = Card.__table__.c.payload.op("||")(stmt.excluded.payload)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Card.dedupe_key], set_=fresh, where=Card.state == "new"
            )
        )
    # A card whose save no longer needs you (closed, not for you, date passed) leaves Today.
    db.execute(
        update(Card)
        .where(Card.user_id == user.id, Card.state == "new", Card.dedupe_key.notin_(live or {""}))
        .values(state="gone")
    )
    room = MAX_NEW_A_DAY - (
        db.scalar(
            select(func.count())
            .select_from(Card)
            .where(Card.user_id == user.id, Card.surfaced_on == today)
        )
        or 0
    )
    if room > 0:
        waiting = db.scalars(
            select(Card)
            .where(Card.user_id == user.id, Card.state == "new", Card.surfaced_on.is_(None))
            .order_by(Card.priority.desc(), Card.due_at)
            .limit(room)
        ).all()
        for card in waiting:
            card.surfaced_on = today
            emit(
                db,
                user_id=user.id,
                agent="when",
                action="surfaced",
                summary=f"Put on Today: {card.title}. {card.why_now}.",
                save_id=card.save_id,
                card_id=card.id,
            )
    db.flush()
    shown = list(
        db.scalars(
            select(Card)
            .where(Card.user_id == user.id, Card.state == "new", Card.surfaced_on == today)
            .order_by(Card.priority.desc(), Card.due_at)
        ).all()
    )
    for card in shown:
        if card.kind == "prep" and "sheet" not in card.payload:
            ask_for_sheet(db, card)
    return shown


def ask_for_sheet(db: Session, card: Card) -> None:
    """Queue the prep sheet once; the card says it's being made until the job is done."""
    card.payload = {**card.payload, "sheet": {"status": "queued"}}
    queue.enqueue(
        db,
        "card.prep",
        {"card_id": card.id},
        user_id=card.user_id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"prep:{card.id}",
    )


def act(db: Session, user: User, card: Card, action: str, now: datetime) -> None:
    """use: done with it. dismiss: never again. later: back tomorrow morning."""
    if action == "use":
        card.state = "used"
    elif action == "dismiss":
        card.state = "dismissed"
        emit(
            db,
            user_id=user.id,
            agent="when",
            action="dismissed",
            summary=f"Won't bring back: {card.title}.",
            save_id=card.save_id,
            card_id=card.id,
        )
    elif action == "later":
        tz = ZoneInfo(user.tz)
        tomorrow = now.astimezone(tz).date() + timedelta(days=1)
        card.state = "later"
        card.later_until = datetime.combine(tomorrow, MORNING, tzinfo=tz).astimezone(UTC)
    else:
        raise ValueError(action)


def match_moment(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Job moment.match: which of the person's goals a coming moment needs (the model picks
    from goal titles; code keeps only real ones, three at most)."""
    moment = ctx.db.get(Moment, payload.get("moment_id"))
    if moment is None or moment.user_id != ctx.user_id:
        raise PermanentError("That moment no longer exists.")
    user = ctx.db.get(User, moment.user_id)
    tz = user.tz if user else "Africa/Lagos"
    _, size = _threads(ctx.db, moment.user_id)
    threads = sorted(
        ctx.db.scalars(
            select(Thread).where(Thread.user_id == moment.user_id, Thread.archived_at.is_(None))
        ).all(),
        key=lambda t: -size.get(t.id, 0),
    )[:60]
    picked: list[Thread] = []
    if threads:
        ids = {f"T{i}": t for i, t in enumerate(threads, 1)}
        out: MomentMatch = gateway_factory(ctx.db).run(
            "when.match_moment",
            user_id=moment.user_id,
            inputs={
                "moment": moment.text,
                "threads": [
                    {"id": tid, "title": t.title, "saves": size.get(t.id, 0)}
                    for tid, t in ids.items()
                ],
            },
            save_ids=[],
        )
        picked = [ids[t] for t in dict.fromkeys(out.threads) if t in ids][:3]
    moment.thread_ids = [t.id for t in picked]
    held = sum(size.get(t.id, 0) for t in picked)
    goals = ", ".join(f"'{t.title}'" for t in picked)
    emit(
        ctx.db,
        user_id=moment.user_id,
        agent="when",
        action="moment_set",
        summary=(
            f"Noted: {moment.text}, {display(moment.at, tz)}. {held} saves in {goals} can help."
            if picked
            else f"Noted: {moment.text}, {display(moment.at, tz)}. No goal of yours matches it yet."
        ),
    )
