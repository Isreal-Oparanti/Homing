"""Video timestamps, checked by code (docs/05 · Video timestamps).

A point taken from a video survives only if its second is a real caption start inside the
video and its quote is in the captions around that second. Sheet citations survive only if
they name a point that survived.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.verify.quotes import match_quote

MAX_SEGMENT_S = 120  # longer stretches are trimmed around the start
WINDOW_PAD_S = 4  # captions just outside the stretch still count for the quote
SNAP_S = 2  # how far a cited second may be from a real caption start
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass(frozen=True)
class CheckedPoint:
    point: str
    t_start: int
    t_end: int
    quote: str  # as it appears in the captions


def _seconds(segments: list[dict[str, Any]]) -> list[int]:
    return [int(s["t"]) for s in segments]


def numbers_supported(text: str, *sources: str) -> bool:
    """Every number in `text` appears in the sources: rewording mustn't add "10 minutes"."""
    have = {n for source in sources for n in _NUMBER.findall(source)}
    return set(_NUMBER.findall(text)) <= have


def duration_of(segments: list[dict[str, Any]], stated: float | None = None) -> int:
    """The video's length: stated by YouTube when we have it, else the last caption plus a bit."""
    if stated:
        return int(stated)
    return int(segments[-1]["t"]) + 10 if segments else 0


def check_point(
    point: str,
    t_start: int,
    t_end: int,
    quote: str,
    segments: list[dict[str, Any]],
    duration: int,
    context: str = "",
) -> CheckedPoint | None:
    """`context` is the moment, whose own numbers ("a 3-minute demo") the point may use."""
    if not segments or not (0 <= t_start < duration):
        return None
    starts = _seconds(segments)
    nearest = min(starts, key=lambda s: abs(s - t_start))
    if abs(nearest - t_start) > SNAP_S:
        return None  # not a real caption start: the model made the second up
    t_start = nearest
    t_end = min(max(t_end, t_start + 1), duration, t_start + MAX_SEGMENT_S)
    window = " ".join(
        s["text"]
        for s, at in zip(segments, starts, strict=True)
        if t_start - WINDOW_PAD_S <= at <= t_end + WINDOW_PAD_S
    )
    found = match_quote(quote, window)
    if found is None or not numbers_supported(point, window, context):
        return None
    return CheckedPoint(point, t_start, t_end, window[found.start : found.end])


def keep_known_cites(
    items: list[dict[str, Any]], known: set[tuple[str, int]]
) -> tuple[list[dict[str, Any]], int]:
    """Drop citations that don't name a checked point, then items left with none."""
    kept, dropped = [], 0
    for item in items:
        cites = [c for c in item["cites"] if (c["video"], int(c["t"])) in known]
        dropped += len(item["cites"]) - len(cites)
        if cites:
            kept.append({**item, "cites": cites})
    return kept, dropped
