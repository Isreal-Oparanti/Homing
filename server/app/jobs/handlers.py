"""Job kind → handler. Agents register their handlers here as each slice lands."""

from typing import Any

from app.agents.is_it_true import check, check_item
from app.agents.what_is_it import read_batch, read_one
from app.agents.whats_it_for import place, rebuild
from app.agents.when_needed import set_when
from app.events.emitter import emit
from app.ingest.whatsapp.importer import import_whatsapp
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
    "save.read": read_one,
    "save.read_batch": read_batch,
    "save.check": check,
    "save.check_item": check_item,
    "save.place": place,
    "threads.rebuild": rebuild,
    "save.when": set_when,
    "import.whatsapp": import_whatsapp,
}
