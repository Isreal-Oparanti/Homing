"""Prep sheets: what your saved videos say for a moment coming up, each point at its second.

See docs/03-agents.md (card.prep). Two model calls, each checked by code:
1. per video, points with a start second and a quote, kept only if the quote is in the
   captions at that second (verify/timestamps.py);
2. across videos, what they agree and disagree on and a checklist, kept only where every
   citation names a point from step 1.
"""

from dataclasses import dataclass, field
from typing import Any

from app.llm.gateway import ModelGateway
from app.schemas.agents import PrepSheet, VideoPoints
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
