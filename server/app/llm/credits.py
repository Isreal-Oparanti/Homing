"""Which Meta model did each step: the gateway notes every model call (cached ones too: the
answer is still that model's work) with the saves it was about, and each event records the
models behind it. A step with no model call records none, and the app says "by code".
"""

from contextvars import ContextVar

Call = tuple[str, frozenset[str]]  # the model, and the saves the call was about
_calls: ContextVar[list[Call] | None] = ContextVar("model_calls", default=None)


def start() -> None:
    """A new job or request: nothing has been called yet."""
    _calls.set([])


def note(model: str, save_ids: list[str]) -> None:
    calls = _calls.get()
    if calls is None:
        calls = []
        _calls.set(calls)
    calls.append((model, frozenset(save_ids)))


def models_for(save_id: str | None) -> list[str]:
    """The models called for this save in this job; for a step about no one save, every model
    the job called. In the order first used."""
    calls = _calls.get() or []
    chosen = [m for m, saves in calls if save_id is None or save_id in saves]
    return list(dict.fromkeys(chosen))
