"""When will you need it? Gives every save a "when", worked out by code from dated words.

See docs/03-agents.md#when-will-you-need-it. S4 sets the "when" from a verified official
deadline or a date in the reading. Moments, thread dates and the tick come later.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db.models import Check, Reading, Save, User, When
from app.db.repo import saves as saves_repo
from app.events.emitter import emit
from app.jobs.errors import PermanentError
from app.jobs.runner import JobContext
from app.verify.dates import Deadline, bring_back_at, city_of, display, parse_deadline

NO_DATE = "No date. It'll come back when you save something related or search for it."


@dataclass(frozen=True)
class Dated:
    deadline: Deadline
    role: str  # deadline · event
    source: str  # check · reading
    closed_at: datetime | None = None  # the official date, passed, when a later one is used


def _from_check(check: Check | None, user_tz: str) -> Dated | None:
    if check is None or check.deadline_at is None or not check.deadline_source_text:
        return None
    d = parse_deadline(check.deadline_source_text, base=check.checked_at, user_tz=user_tz)
    return Dated(d, "deadline", "check") if d else None


def _from_reading(save: Save, reading: Reading, user_tz: str, now: datetime) -> Dated | None:
    """The soonest coming deadline, else the soonest coming event, else the latest past deadline."""
    found: list[Dated] = []
    for fact in (reading.key_facts or {}).get("dates", []):
        role = fact.get("role")
        if role not in ("deadline", "event"):
            continue
        if d := parse_deadline(fact.get("text", ""), base=save.saved_at, user_tz=user_tz):
            found.append(Dated(d, role, "reading"))
    for role in ("deadline", "event"):
        coming = [x for x in found if x.role == role and x.deadline.at > now]
        if coming:
            return min(coming, key=lambda x: x.deadline.at)
    # All past: the closing date says most ("Closed on 20 Jul"), so prefer it over events.
    past = [x for x in found if x.role == "deadline"] or found
    return max(past, key=lambda x: x.deadline.at) if past else None


def _explain(dated: Dated, user_tz: str, now: datetime) -> str:
    shown = display(dated.deadline.at, user_tz)
    past = dated.deadline.at <= now
    if dated.closed_at is not None:
        closed = display(dated.closed_at, user_tz).removesuffix(f" {city_of(user_tz)} time")
        return f"Applications closed on {closed}. Next on the page: {shown}."
    if dated.source == "check":
        return (
            f"Closed on {shown}, per the official page."
            if past
            else (f"Closes {shown}, per the official page.")
        )
    if dated.role == "event":
        return f"That was on {shown}." if past else f"On {shown}, if the post is right."
    return (
        f"Closed on {shown}, if the post was right."
        if past
        else (f"Closes {shown}, if the post is right.")
    )


def explain_now(when: When, now: datetime) -> str:
    """The explanation is written when the date is set; once the date has passed, say so
    ("Closes Sat 31 Oct…" read on 3 Nov must be "Closed on Sat 31 Oct…")."""
    text = when.explanation or ""
    if when.due_at is None or when.due_at > now:
        return text
    if text.startswith("Closes "):
        return ("Closed on " + text.removeprefix("Closes ")).replace(
            "if the post is right", "if the post was right"
        )
    if text.startswith("On ") and text.endswith(", if the post is right."):
        return f"That was on {text.removeprefix('On ').removesuffix(', if the post is right.')}."
    if "Next on the page: " in text:
        return text.replace("Next on the page: ", "The next date on the page has passed too: ")
    return text


def set_when(ctx: JobContext, payload: dict[str, Any]) -> None:
    if ctx.user_id is None:
        raise PermanentError("save.when needs a user.")
    save = saves_repo.get_save(ctx.db, ctx.user_id, str(payload.get("save_id")))
    if save is None:
        raise PermanentError("That save no longer exists.")
    reading = saves_repo.get_reading(ctx.db, save.id)
    if save.visibility == "private" or reading is None:
        return
    user = ctx.db.get(User, save.user_id)
    user_tz = user.tz if user else "Africa/Lagos"
    now = datetime.now(UTC)

    checked = _from_check(ctx.db.get(Check, save.id), user_tz)
    read = _from_reading(save, reading, user_tz, now)
    dated = checked or read
    # The official date has passed but the page has one still ahead ("Applications closed
    # 25 Oct" and "submissions due 4 Nov"): the one ahead is when you'll need it.
    if checked and checked.deadline.at <= now and read and read.deadline.at > now:
        dated = Dated(read.deadline, read.role, "reading", closed_at=checked.deadline.at)
    when = ctx.db.get(When, save.id) or When(save_id=save.id)
    if dated is None:
        when.kind, when.source, when.explanation = "none", "reading", NO_DATE
        when.due_at = when.bring_back_at = when.source_text = None
        when.tz_stated = when.time_stated = False
        ctx.db.add(when)
        return

    d = dated.deadline
    when.kind = "date"
    when.source = dated.source
    when.due_at = d.at
    when.bring_back_at = bring_back_at(d.at, now=now, user_tz=user_tz)
    when.source_text = d.source_text
    when.tz_stated = d.tz_stated
    when.time_stated = d.time_stated
    when.explanation = _explain(dated, user_tz, now)
    ctx.db.add(when)

    if when.bring_back_at is None:
        return  # already past: nothing to bring back
    if when.bring_back_at <= now:
        summary = f"Put this on Today: {when.explanation[0].lower()}{when.explanation[1:]}"
    else:
        summary = f"Will bring this back on {display(when.bring_back_at, user_tz)}."
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="when",
        action="when_set",
        summary=summary,
        save_id=save.id,
        evidence=[{"label": "The date, as written", "quote": d.source_text}],
    )
