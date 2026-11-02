"""Ask: one question, one answer page from the person's own saves (ADR 0003, S10).

1. **Find:** hybrid search, top 40, plus the other saves in the goals those hits belong to.
2. **Pick** (`ask.select`, Spark): which candidates actually help, 12 at most.
3. **Answer** (`ask.answer`, Spark): points from the picked saves' own content, each quoting
   one save, and what the saves don't cover.
4. **Verify** (code): every quote must be found in that save's text, and a point may only use
   numbers its quote has. Points that fail are dropped, never shown.
Not a chat: a follow-up is a new question.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Ask, Reading, Save, Snapshot, ThreadSave
from app.events.emitter import emit
from app.jobs.errors import PermanentError
from app.jobs.runner import JobContext
from app.llm.gateway import ModelGateway
from app.schemas.agents import AskAnswer, AskPick
from app.search.hybrid import search
from app.verify.quotes import match_quote
from app.verify.timestamps import numbers_supported

FOUND = 40  # from search
NEIGHBOURS_OF = 8  # top hits whose goals bring in their other saves
MAX_CANDIDATES = 60
SOURCE_CHARS = 6_000  # of each picked save's content
SOURCES_CHARS = 40_000  # in all
# Less than this and Homing only knows the title (a YouTube video without captions, a post it
# couldn't open): listed for the person to open, never dressed up as a point.
THIN_CHARS = 300

# Tests swap this for a fake; agents never build clients themselves.
gateway_factory: Any = ModelGateway


def _candidates(db: Session, user_id: str, question: str) -> list[tuple[Save, Reading]]:
    found = search(db, user_id, question, limit=FOUND)
    seen = {f.save.id for f in found}
    pairs = [(f.save, f.reading) for f in found]
    goals = select(ThreadSave.thread_id).where(
        ThreadSave.save_id.in_([f.save.id for f in found[:NEIGHBOURS_OF]])
    )
    neighbours = db.execute(
        select(Save, Reading)
        .join(Reading, Reading.save_id == Save.id)
        .join(ThreadSave, ThreadSave.save_id == Save.id)
        .where(
            ThreadSave.thread_id.in_(goals),
            Save.user_id == user_id,
            Save.visibility == "normal",
            Save.status == "ready",
        )
        .order_by(Save.saved_at.desc())
    ).all()
    for save, reading in neighbours:
        if save.id not in seen and len(pairs) < MAX_CANDIDATES:
            seen.add(save.id)
            pairs.append((save, reading))
    return pairs


def _line(n: int, save: Save, reading: Reading) -> str:
    parts = [
        str(n),
        f"{save.saved_at:%Y-%m-%d}",
        reading.title,
        reading.what or "",
        save.label or "",
    ]
    return " | ".join(" ".join(p.split()) for p in parts)[:240]


def _source_text(db: Session, save: Save) -> str:
    """The save's own words and our copy of its content: what quotes are checked against."""
    copies = db.scalars(
        select(Snapshot.text).where(Snapshot.save_id == save.id).order_by(Snapshot.id)
    ).all()
    own = [save.label or "", save.text or ""]
    return "\n".join(t for t in [*own, *copies] if t.strip())[:SOURCE_CHARS]


def answer(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Job ask.answer."""
    ask = ctx.db.get(Ask, payload.get("ask_id"))
    if ask is None or ask.user_id != ctx.user_id:
        raise PermanentError("That question doesn't exist.")
    try:
        result = _answer(ctx, ask)
    except Exception:
        if ctx.attempt >= ctx.max_attempts:
            ctx.db.rollback()
            ask.status = "failed"
            ask.error = "Homing couldn't answer this one. Try asking again."
            ask.finished_at = datetime.now(UTC)
            ctx.db.commit()
        raise
    ask.answer = result
    ask.status = "done"
    ask.finished_at = datetime.now(UTC)
    used = len({p["save_id"] for p in result["points"]})
    emit(
        ctx.db,
        user_id=ask.user_id,
        agent="system",
        action="answered",
        summary=(
            f"Answered “{ask.question[:80]}” from {used} of your saves."
            if used
            else f"Looked for “{ask.question[:80]}”: your saves don't cover it yet."
        ),
    )


def _answer(ctx: JobContext, ask: Ask) -> dict[str, Any]:
    db, uid, question = ctx.db, ask.user_id, ask.question
    candidates = _candidates(db, uid, question)
    empty = {"points": [], "not_covered": [], "considered": len(candidates), "read": 0}
    if not candidates:
        return {**empty, "not_covered": ["Nothing you've saved seems to be about this yet."]}

    gateway = gateway_factory(db)
    pick: AskPick = gateway.run(
        "ask.select",
        user_id=uid,
        inputs={
            "question": question,
            "saves": "\n".join(_line(n, s, r) for n, (s, r) in enumerate(candidates, 1)),
        },
        save_ids=[s.id for s, _ in candidates],
    )
    picked = [candidates[n - 1] for n in dict.fromkeys(pick.saves) if 1 <= n <= len(candidates)]
    if not picked:
        return {**empty, "not_covered": ["None of your saves answer this yet."]}

    sources, also, budget = [], [], SOURCES_CHARS
    for save, reading in picked:
        text = _source_text(db, save)[: max(budget, 0)]
        if len(text) < THIN_CHARS:
            also.append({"save_id": save.id, "title": reading.title})
            continue
        budget -= len(text)
        sources.append((save, reading, text))
    if not sources:
        return {
            **empty,
            "also": also,
            "not_covered": ["Your saves on this only show Homing their titles, so open them."],
        }
    out: AskAnswer = gateway.run(
        "ask.answer",
        user_id=uid,
        inputs={
            "question": question,
            "sources": [
                {"n": n, "title": r.title, "saved": f"{s.saved_at:%d %b %Y}", "text": text}
                for n, (s, r, text) in enumerate(sources, 1)
            ],
        },
        save_ids=[s.id for s, _, _ in sources],
    )

    points, dropped = [], 0
    for p in out.points:
        if not 1 <= p.save <= len(sources):
            dropped += 1
            continue
        save, reading, text = sources[p.save - 1]
        found = match_quote(p.quote, text)
        if found is None or not numbers_supported(p.point, text[found.start : found.end]):
            dropped += 1  # not in the save, or a number the save doesn't say
            continue
        points.append(
            {
                "point": p.point,
                "quote": text[found.start : found.end],
                "save_id": save.id,
                "title": reading.title,
                "saved_at": save.saved_at.isoformat(),
            }
        )
    return {
        "points": points,
        "also": also,
        "not_covered": out.not_covered,
        "considered": len(candidates),
        "read": len(sources),
        "dropped": dropped,
    }
