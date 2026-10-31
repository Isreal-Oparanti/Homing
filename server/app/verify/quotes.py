"""Quote checks: a claim is shown only if its quote is really in the source (docs/05).

Pure functions, no I/O. Models propose quotes; this decides whether they're real.
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

ACCEPT_SCORE = 92  # fuzzy matches below this are rejected
MIN_FUZZY_CHARS = 12  # shorter quotes must match exactly
MAX_QUOTE_CHARS = 400  # longer means the model is pasting, not quoting
MIN_WORDS = 3

_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "–": "-", "—": "-"})
# Soft hyphen, zero-width spaces and joiners, word joiner, byte-order mark.
_INVISIBLE = {chr(c) for c in (0x00AD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF)}
_DATE_OR_AMOUNT = re.compile(r"\d")


@dataclass(frozen=True)
class QuoteMatch:
    score: float  # 100 for an exact match
    start: int  # offsets in the original, un-normalised source
    end: int


def _normalise(text: str) -> tuple[str, list[int]]:
    """Normalised text, plus the original index of every normalised character."""
    out: list[str] = []
    where: list[int] = []
    for i, ch in enumerate(text):
        if ch in _INVISIBLE:
            continue
        for c in unicodedata.normalize("NFKC", ch).translate(_QUOTES).lower():
            if c.isspace():
                if not out or out[-1] == " ":
                    continue
                c = " "
            out.append(c)
            where.append(i)
    while out and out[-1] == " ":
        out.pop()
        where.pop()
    return "".join(out), where


def accepts(score: float, quote_chars: int) -> bool:
    """The thresholds, kept apart so they can be tested exactly."""
    if quote_chars < MIN_FUZZY_CHARS:
        return score == 100
    return score >= ACCEPT_SCORE


def match_quote(quote: str, source: str) -> QuoteMatch | None:
    q, _ = _normalise(quote)
    src, where = _normalise(source)
    if not q or not src or len(q) > MAX_QUOTE_CHARS:
        return None
    # Very short quotes prove little, except a date or an amount that matches exactly.
    short = len(q.split()) < MIN_WORDS
    if short and not _DATE_OR_AMOUNT.search(q):
        return None

    at = src.find(q)
    if at >= 0:
        return QuoteMatch(100.0, where[at], where[at + len(q) - 1] + 1)
    if short:
        return None

    found = fuzz.partial_ratio_alignment(q, src, score_cutoff=ACCEPT_SCORE)
    if found is None or not accepts(found.score, len(q)):
        return None
    start, end = found.dest_start, found.dest_end
    if end <= start:
        return None
    return QuoteMatch(round(found.score, 1), where[start], where[end - 1] + 1)
