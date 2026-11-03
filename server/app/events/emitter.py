"""Writes lines to The team feed. Every agent action that the user should see goes through here."""

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentEvent
from app.llm import credits

AGENTS = frozenset({"what", "true", "for", "when", "system"})


def emit(
    db: Session,
    *,
    user_id: str,
    agent: str,
    action: str,
    summary: str,
    save_id: str | None = None,
    thread_id: str | None = None,
    card_id: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    models: list[str] | None = None,  # say who did it when it isn't the job's model calls
) -> AgentEvent:
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}")
    event = AgentEvent(
        user_id=user_id,
        agent=agent,
        action=action,
        summary=summary,
        save_id=save_id,
        thread_id=thread_id,
        card_id=card_id,
        evidence=evidence or [],
        # The Meta models behind this step; none means code did it.
        models=credits.models_for(save_id) if models is None else models,
    )
    db.add(event)
    db.flush()
    return event
