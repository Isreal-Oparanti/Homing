"""Closed signals, found by code in the official page's own words (docs/05)."""

import re
from dataclasses import dataclass

_CLOSED = re.compile(
    r"applications? (?:are |is )?(?:now )?closed"
    r"|no longer accepting"
    r"|this (?:position|opportunity|call|programme|program) (?:has|is) (?:now )?(?:closed|expired)"
    r"|deadline (?:has )?passed"
    r"|candidatures? (?:sont )?closes?",
    re.I,
)


@dataclass(frozen=True)
class ClosedSignal:
    kind: str  # dead_link · says_closed
    quote: str  # the words that show it, from the page


def is_closed(page_text: str, http_status: int | None = None) -> ClosedSignal | None:
    if http_status in (404, 410):
        return ClosedSignal("dead_link", f"The page answered {http_status}.")
    if m := _CLOSED.search(page_text or ""):
        return ClosedSignal("says_closed", m.group(0))
    return None
