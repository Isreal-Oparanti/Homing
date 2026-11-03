"""Prep sheets: what your saved videos say for a moment coming up, each point at its second.

See docs/03-agents.md (card.prep). Two model calls, each checked by code:
1. per video, points with a start second and a quote, kept only if the quote is in the
   captions at that second (verify/timestamps.py);
2. across videos, what they agree and disagree on and a checklist, kept only where every
   citation names a point from step 1.
"""

from dataclasses import dataclass, field
from itertools import zip_longest
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Card, Moment, Reading, Save, SaveEmbedding, Snapshot, Thread, ThreadSave
from app.events.emitter import emit
from app.jobs.errors import PermanentError
from app.jobs.runner import JobContext
from app.llm.gateway import ModelGateway
from app.schemas.agents import PrepSheet, VideoPoints
from app.search import hybrid
from app.verify.timestamps import (
    CheckedPoint,
    check_point,
    duration_of,
    keep_known_cites,
    numbers_supported,
)

TRANSCRIPT_CHARS = 60_000


@dataclass
class Video:
    id: str  # V1, V2, … as the model sees them
    title: str
    url: str  # https://www.youtube.com/watch?v=…
    segments: list[dict[str, Any]]  # [{t, text}] from the captions
    author: str | None = None
    duration_s: float | None = None
    save_id: str | None = None
    thread: str | None = None  # the goal it was saved under, e.g. "Speaking better"
    points: list[CheckedPoint] = field(default_factory=list)
    dropped: int = 0


def transcript_lines(segments: list[dict[str, Any]]) -> str:
    lines, size = [], 0
    for s in segments:
        line = f"[{int(s['t'])}] {' '.join(str(s['text']).split())}"
        size += len(line) + 1
        if size > TRANSCRIPT_CHARS:
            break
        lines.append(line)
    return "\n".join(lines)


def read_video(gateway: ModelGateway, video: Video, *, moment: str, user_id: str | None) -> Video:
    """Step 1: the video's useful points, each checked against its captions."""
    out: VideoPoints = gateway.run(
        "video.points",
        user_id=user_id,
        inputs={
            "moment": moment,
            "video": {"title": video.title, "channel": video.author},
            "transcript": transcript_lines(video.segments),
        },
        save_ids=[video.save_id] if video.save_id else [],
    )
    duration = duration_of(video.segments, video.duration_s)
    for p in out.points:
        checked = check_point(
            p.point, p.t_start, p.t_end, p.quote, video.segments, duration, context=moment
        )
        if checked is None:
            video.dropped += 1
        else:
            video.points.append(checked)
    return video


def build_sheet(
    gateway: ModelGateway, videos: list[Video], *, moment: str, user_id: str | None
) -> dict[str, Any]:
    """Step 2: the sheet, with every citation pointing at a checked point."""
    with_points = [v for v in videos if v.points]
    sheet: PrepSheet = gateway.run(
        "prep.sheet",
        user_id=user_id,
        inputs={
            "moment": moment,
            "points": [
                {
                    "video": v.id,
                    "title": v.title,
                    "thread": v.thread,
                    "points": [{"t": p.t_start, "point": p.point} for p in v.points],
                }
                for v in with_points
            ],
        },
        save_ids=[v.save_id for v in with_points if v.save_id],
    )
    known = {(v.id, p.t_start) for v in with_points for p in v.points}
    said = {(v.id, p.t_start): f"{p.point} {p.quote}" for v in with_points for p in v.points}
    raw = sheet.model_dump()

    def supported(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # A sheet line may only use numbers its cited points (or the moment) contain.
        return [
            i
            for i in items
            if numbers_supported(
                i["text"], moment, *(said.get((c["video"], int(c["t"])), "") for c in i["cites"])
            )
        ]

    agree, d1 = keep_known_cites(raw["agree"], known)
    checklist, d2 = keep_known_cites(raw["checklist"], known)
    agree, checklist = supported(agree), supported(checklist)
    disagree, d3 = [], 0
    for topic in raw["disagree"]:
        sides, dropped = keep_known_cites(topic["sides"], known)
        sides = supported(sides)
        d3 += dropped
        if len(sides) >= 2:  # a disagreement needs two sides that both hold up
            disagree.append({"topic": topic["topic"], "sides": sides})
    return {
        "agree": agree,
        "disagree": disagree,
        "checklist": checklist,
        "dropped_cites": d1 + d2 + d3,
    }


# The card.prep job (S12) -----------------------------------------------------------------------

MAX_VIDEOS = 8
REEL_MAX_S = 180
REEL_BEFORE_S, REEL_AFTER_S = 3, 12
NO_WORDS = {"instagram", "tiktok", "facebook"}  # reels: no captions we may fetch

# Tests swap this for a fake; agents never build clients themselves.
gateway_factory: Any = ModelGateway


def _ranked(db: Session, user_id: str, save_ids: list[str], text: str) -> list[str]:
    """The saves closest in meaning to the moment first (code, from the saved embeddings)."""
    if not save_ids:
        return []
    vector = hybrid.embedder_factory().embed([text], "query")[0]
    near = db.scalars(
        select(SaveEmbedding.save_id)
        .where(SaveEmbedding.user_id == user_id, SaveEmbedding.save_id.in_(save_ids))
        .order_by(SaveEmbedding.embedding.cosine_distance(vector))
    ).all()
    return list(dict.fromkeys([*near, *save_ids]))


def videos_for(
    db: Session, user_id: str, thread_ids: list[str], moment: str
) -> tuple[list[Video], dict[str, int]]:
    """The goals' videos that have timed captions, best for the moment first, and how many
    saves couldn't be used, and why."""
    rows_t = db.execute(select(Thread.id, Thread.title).where(Thread.id.in_(thread_ids)))
    titles = {i: t for i, t in rows_t}
    rows = db.execute(
        select(Save, Reading, ThreadSave.thread_id)
        .join(Reading, Reading.save_id == Save.id)
        .join(ThreadSave, ThreadSave.save_id == Save.id)
        .where(
            ThreadSave.thread_id.in_(thread_ids),
            Save.user_id == user_id,
            Save.visibility == "normal",
        )
    ).all()
    saves = {s.id: (s, r, titles.get(t)) for s, r, t in rows}
    timed: dict[str, Snapshot] = {}
    for snap in db.scalars(
        select(Snapshot)
        .where(Snapshot.save_id.in_(list(saves)), Snapshot.kind == "transcript")
        .order_by(Snapshot.fetched_at)
    ):
        if (snap.meta or {}).get("segments"):
            timed[snap.save_id] = snap  # the latest wins
    youtube = sum(1 for s, _, _ in saves.values() if s.platform == "youtube")
    skipped = {
        "no_captions": youtube - sum(1 for i in timed if saves[i][0].platform == "youtube"),
        "reels": sum(1 for s, _, _ in saves.values() if s.platform in NO_WORDS),
    }
    skipped["others"] = len(saves) - len(timed) - skipped["no_captions"] - skipped["reels"]
    videos = []
    # Each goal the moment needs takes its turn, its best match first, so one big goal
    # doesn't crowd out the others.
    by_goal: dict[str | None, list[str]] = {}
    for save_id in _ranked(db, user_id, list(timed), moment):
        by_goal.setdefault(saves[save_id][2], []).append(save_id)
    turns = zip_longest(*by_goal.values())
    picked = [i for turn in turns for i in turn if i is not None][:MAX_VIDEOS]
    for n, save_id in enumerate(picked, 1):
        save, reading, thread = saves[save_id]
        snap = timed[save_id]
        meta = snap.meta or {}
        videos.append(
            Video(
                id=f"V{n}",
                title=reading.title,
                url=snap.source_url or save.url or "",
                segments=meta["segments"],
                author=meta.get("channel"),
                duration_s=meta.get("duration_s"),
                save_id=save_id,
                thread=thread,
            )
        )
    return videos, skipped


def make_reel(sheet: dict[str, Any], videos: list[Video]) -> list[dict[str, Any]]:
    """The cited moments, checklist first, padded a little and merged where they touch, at
    most three minutes in all."""
    by_id = {v.id: v for v in videos}
    reel: list[dict[str, Any]] = []
    total = 0
    items = [*sheet["checklist"], *sheet["agree"]]
    for cite in (c for item in items for c in item["cites"]):
        video = by_id.get(cite["video"])
        if video is None:
            continue
        point = next((p for p in video.points if p.t_start == int(cite["t"])), None)
        if point is None:
            continue
        start = max(0, point.t_start - REEL_BEFORE_S)
        end = min(duration_of(video.segments, video.duration_s), point.t_end + REEL_AFTER_S)
        if end <= start:
            continue
        same = next(
            (r for r in reel if r["video"] == video.id and start <= r["end"] and end >= r["start"]),
            None,
        )
        if same is not None:
            lo, hi = min(start, same["start"]), max(end, same["end"])
            grown = (hi - lo) - (same["end"] - same["start"])
            if total + grown <= REEL_MAX_S:
                same["start"], same["end"] = lo, hi
                total += grown
            continue
        if total + (end - start) > REEL_MAX_S:
            continue
        reel.append({"video": video.id, "start": start, "end": end})
        total += end - start
    return reel


def _said(video: Video, moment: str) -> str:
    found = (
        f"{len(video.points)} points, each found in the captions at its second"
        if video.points
        else "nothing for this moment"
    )
    weren_t = "that wasn't" if video.dropped == 1 else "that weren't"
    dropped = f"; dropped {video.dropped} {weren_t}" if video.dropped else ""
    return f"Went through '{video.title}' for {moment}: {found}{dropped}."


def prepare(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Job card.prep: a prep card's sheet, from the videos its goals hold (docs/03 · card.prep)."""
    card = ctx.db.get(Card, payload.get("card_id"))
    if card is None or card.user_id != ctx.user_id or card.kind != "prep":
        raise PermanentError("That prep card no longer exists.")
    moment = ctx.db.get(Moment, card.moment_id) if card.moment_id else None
    if moment is None:
        raise PermanentError("That moment no longer exists.")
    card.payload = {**card.payload, "sheet": {"status": "working"}}
    ctx.db.commit()
    try:
        videos, skipped = videos_for(ctx.db, card.user_id, list(card.thread_ids), moment.text)
        gateway = gateway_factory(ctx.db)
        for video in videos:
            read_video(gateway, video, moment=moment.text, user_id=card.user_id)
            emit(
                ctx.db,
                user_id=card.user_id,
                agent="when",
                action="watched",
                summary=_said(video, moment.text),
                save_id=video.save_id,
                card_id=card.id,
            )
            ctx.db.commit()
        used = [v for v in videos if v.points]
        if used:
            sheet = build_sheet(gateway, used, moment=moment.text, user_id=card.user_id)
        else:
            sheet = {"agree": [], "disagree": [], "checklist": [], "dropped_cites": 0}
    except Exception:
        if ctx.attempt >= ctx.max_attempts:
            ctx.db.rollback()
            card.payload = {**card.payload, "sheet": {"status": "failed"}}
            ctx.db.commit()
        raise
    card.payload = {
        **card.payload,
        "sheet": {
            "status": "ready",
            **sheet,
            "videos": {
                v.id: {
                    "save_id": v.save_id,
                    "title": v.title,
                    "url": v.url,
                    "thread": v.thread,
                    "points": [
                        {"t_start": p.t_start, "t_end": p.t_end, "point": p.point, "quote": p.quote}
                        for p in v.points
                    ],
                }
                for v in used
            },
            "reel": make_reel(sheet, used),
            "watched": len(videos),
            "dropped_points": sum(v.dropped for v in videos),
            "skipped": skipped,
        },
    }
    steps = len(sheet["checklist"])
    emit(
        ctx.db,
        user_id=card.user_id,
        agent="when",
        action="prep_ready",
        summary=(
            f"Prep sheet ready for {moment.text}: {steps} steps from {len(used)} of your"
            " videos, each at the second it's said."
            if steps
            else f"Went through {len(videos)} of your videos for {moment.text}; none had steps"
            " I could point to."
        ),
        card_id=card.id,
    )
