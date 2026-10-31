"""Job kind → handler. Agents register their handlers here as each slice lands."""

from typing import Any

from app.events.emitter import emit
from app.jobs.errors import PermanentError
from app.jobs.runner import Handler, JobContext


def system_echo(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Writes one line to The team. Used to check the queue → feed → live stream path."""
    if ctx.user_id is None:
        raise PermanentError("system.echo needs a user.")
    emit(
        ctx.db,
        user_id=ctx.user_id,
        agent="system",
        action="echo",
        summary=str(payload.get("message") or "The team is listening."),
    )


HANDLERS: dict[str, Handler] = {
    "system.echo": system_echo,
}
