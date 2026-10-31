"""The verdict on an opportunity, decided by code in a fixed order (docs/03 · Is it true?, step 6).

The same inputs always give the same verdict. Models never decide it.
"""

from typing import Any


def decide(
    *,
    closed: bool,
    past_deadline: bool,
    source_opened: bool,
    rules: list[dict[str, Any]],
    is_opportunity: bool = True,
) -> str:
    required = [r for r in rules if r.get("strength") == "required"]
    if closed or past_deadline:
        return "closed"
    if not is_opportunity:
        # Fitting you only means something for an opportunity; anything else is just checked.
        return "checked" if source_opened else "couldnt_confirm"
    if any(r.get("result") == "fails" for r in required):
        return "not_for_you"
    if any(r.get("result") == "unknown" for r in required):
        return "needs_your_answer"
    if not source_opened:
        return "couldnt_confirm"
    return "fits_you"
