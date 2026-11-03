"""A transcript the person pasted from YouTube ("… → Show transcript", then copy).

YouTube doesn't give captions to our server, and the only official captions API is for a
video's owner; copying what YouTube shows anyone is the person's own step. The copy comes as
timestamps and lines, sometimes with screen-reader labels ("1 minute, 5 seconds") between
them; any of these shapes works:

    0:12                    0:12 welcome back           1:02:05
    welcome back            0:15 today we'll look       and that's the idea
"""

import re
from typing import Any

_STAMP = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b\s*(.*)$")
# Screen-reader labels YouTube adds under each timestamp: "5 seconds", "1 minute, 2 seconds".
_SPOKEN = re.compile(r"^\s*(\d+\s+(hours?|minutes?|seconds?),?\s*)+$", re.I)
MIN_SEGMENTS = 3
MAX_CHARS = 200_000


def parse_transcript(text: str) -> list[dict[str, Any]]:
    """[{t, text}] in order, or [] when it doesn't look like a timed transcript."""
    segments: list[dict[str, Any]] = []
    for line in text[:MAX_CHARS].splitlines():
        if not line.strip() or _SPOKEN.match(line):
            continue
        stamp = _STAMP.match(line)
        if stamp and (not segments or _seconds(stamp) >= segments[-1]["t"]):
            segments.append({"t": float(_seconds(stamp)), "text": stamp.group(4).strip()})
        elif segments:
            words = " ".join(line.split())
            segments[-1]["text"] = f"{segments[-1]['text']} {words}".strip()
    segments = [s for s in segments if s["text"]]
    return segments if len(segments) >= MIN_SEGMENTS else []


def _seconds(m: re.Match[str]) -> int:
    hours = int(m.group(1) or 0)
    return hours * 3600 + int(m.group(2)) * 60 + int(m.group(3))
