"""What What's it for? remembers about looking for more for one goal, between runs.

Kept in agent_memory (agent "for", key "finds:<goal id>"): the searches it ran and what they
gave, the sites Homing refused and why, what the person kept, what they said wasn't for them
and why, and the lessons the agent wrote for itself at the end of each run. The next run
starts from it, so it doesn't repeat itself and learns what the person doesn't want.
Bounded lists: the newest KEEP of each.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import AgentMemory

KEEP = 12
LISTS = ("searched", "refused", "kept", "dismissed", "lessons")
# One tap on "Not for me": the reason becomes something the next run rules out.
WHY_NOT = {
    "wrong_country": "it's for people in another country",
    "not_my_stage": "it's for a different stage",
    "already_applied": "they've already applied or know it",
    "not_interested": "not what they're after",
}


def _key(thread_id: str) -> str:
    return f"finds:{thread_id}"


def load(db: Session, user_id: str, thread_id: str) -> dict[str, Any]:
    row = db.get(AgentMemory, (user_id, "for", _key(thread_id)))
    return dict(row.value) if row is not None else {}


def remember(db: Session, user_id: str, thread_id: str, **add: list[Any]) -> None:
    """Add to the memory's lists: newest last, the newest KEEP of each kept."""
    memory = load(db, user_id, thread_id)
    for name, items in add.items():
        assert name in LISTS, name
        memory[name] = (list(memory.get(name, [])) + list(items))[-KEEP:]
    memory["updated"] = datetime.now(UTC).isoformat()
    stmt = insert(AgentMemory).values(
        user_id=user_id, agent="for", key=_key(thread_id), value=memory
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["user_id", "agent", "key"], set_={"value": stmt.excluded.value}
        )
    )


def brief(memory: dict[str, Any]) -> str:
    """The memory as the agent reads it at the start of a run. Empty: this is the first run."""
    if not memory:
        return "WHAT YOU KNOW FROM BEFORE: nothing yet. This is the first time you look."
    parts = ["WHAT YOU KNOW FROM BEFORE (use it: don't repeat what failed):"]
    if memory.get("lessons"):
        parts.append("Your lessons: " + " | ".join(memory["lessons"][-4:]))
    if memory.get("searched"):
        tried = [f"“{s['query']}” ({s['found']} found)" for s in memory["searched"]]
        parts.append("Searched before: " + "; ".join(tried))
    if memory.get("refused"):
        parts.append(
            "Homing refused before: "
            + "; ".join(f"{r['site']} ({r['why']})" for r in memory["refused"])
        )
    if memory.get("dismissed"):
        parts.append(
            "The person said these aren't for them: "
            + "; ".join(
                f"{d['name']} ({WHY_NOT.get(d.get('why', ''), 'no reason given')})"
                for d in memory["dismissed"]
            )
            + ". Rule out things like these, for the same reasons."
        )
    if memory.get("kept"):
        parts.append(
            "The person kept these (find more like them): "
            + "; ".join(k["name"] for k in memory["kept"])
        )
    return "\n".join(parts)
