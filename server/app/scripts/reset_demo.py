"""Put the shared demo account back the way it was: every visitor shares it (docs/09).

  python -m uv run python -m app.scripts.reset_demo --snapshot   # record the clean state
  python -m uv run python -m app.scripts.reset_demo --reset      # go back to it

The snapshot keeps what visitors can change on existing saves (the profile and its answers,
goals and placements, checks, dates, what agents remember) plus the time it was taken. A reset
deletes what visitors added after that time (saves, imports, moments, questions, steps,
finds), clears
Today's cards so they're chosen afresh, and puts the recorded rows back exactly.
Model calls are kept: they're the record of what was spent.

A reset also adds one moment coming up tomorrow evening ("recording my demo video", tied to the
demo's speaking goal), so every visitor finds a prep card on Today with its sheet.
"""

import pickle
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Table, delete, insert, select

from app.core.auth import DEMO_USER_ID
from app.db.models import (
    AgentEvent,
    AgentMemory,
    Ask,
    Card,
    Check,
    Find,
    Import,
    Moment,
    Profile,
    Save,
    Thread,
    ThreadSave,
    When,
)
from app.db.session import session_factory

BASELINE = Path("data/demo_baseline.pkl")
MOMENT_TEXT = "recording my demo video"
MOMENT_GOAL = "Speaking better"
MOMENT_AT = time(18, 0)  # tomorrow evening, Lagos time


def _rows(db: Any, table: Table, where: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in db.execute(select(table).where(where))]


def _scopes(db: Any) -> dict[str, tuple[Table, Any]]:
    saves = select(Save.id).where(Save.user_id == DEMO_USER_ID)
    threads = select(Thread.id).where(Thread.user_id == DEMO_USER_ID)
    return {
        "profiles": (Profile.__table__, Profile.__table__.c.user_id == DEMO_USER_ID),
        "threads": (Thread.__table__, Thread.__table__.c.user_id == DEMO_USER_ID),
        "thread_saves": (ThreadSave.__table__, ThreadSave.__table__.c.thread_id.in_(threads)),
        "checks": (Check.__table__, Check.__table__.c.save_id.in_(saves)),
        "whens": (When.__table__, When.__table__.c.save_id.in_(saves)),
        "agent_memory": (AgentMemory.__table__, AgentMemory.__table__.c.user_id == DEMO_USER_ID),
    }


def snapshot() -> None:
    with session_factory()() as db:
        state = {name: _rows(db, t, w) for name, (t, w) in _scopes(db).items()}
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_bytes(pickle.dumps({"at": datetime.now(UTC), "state": state}))
    print("Recorded:", {k: len(v) for k, v in state.items()})


def reset() -> None:
    if not BASELINE.exists():
        raise SystemExit("No snapshot yet: run with --snapshot first.")
    baseline = pickle.loads(BASELINE.read_bytes())  # our own file, written by snapshot()
    at, state = baseline["at"], baseline["state"]
    with session_factory()() as db:
        demo = DEMO_USER_ID
        gone = {
            "saves": db.execute(delete(Save).where(Save.user_id == demo, Save.created_at > at)),
            "imports": db.execute(
                delete(Import).where(Import.user_id == demo, Import.created_at > at)
            ),
            "moments": db.execute(delete(Moment).where(Moment.user_id == demo)),
            "cards": db.execute(delete(Card).where(Card.user_id == demo)),
            "finds": db.execute(delete(Find).where(Find.user_id == demo, Find.created_at > at)),
            "questions": db.execute(delete(Ask).where(Ask.user_id == demo, Ask.created_at > at)),
            "steps": db.execute(
                delete(AgentEvent).where(AgentEvent.user_id == demo, AgentEvent.created_at > at)
            ),
        }
        # Children before parents when clearing, parents before children when restoring.
        scopes = _scopes(db)
        for name in ("thread_saves", "checks", "whens", "agent_memory", "threads", "profiles"):
            table, where = scopes[name]
            db.execute(delete(table).where(where))
        for name in ("profiles", "threads", "thread_saves", "checks", "whens", "agent_memory"):
            if state[name]:
                db.execute(insert(scopes[name][0]), state[name])
        goal = next((t["id"] for t in state["threads"] if t["title"] == MOMENT_GOAL), None)
        if goal:
            lagos = ZoneInfo("Africa/Lagos")
            tomorrow = datetime.now(lagos).date() + timedelta(days=1)
            when = datetime.combine(tomorrow, MOMENT_AT, tzinfo=lagos).astimezone(UTC)
            db.add(Moment(user_id=demo, text=MOMENT_TEXT, at=when, thread_ids=[goal]))
        db.commit()
    print("Removed:", {k: v.rowcount for k, v in gone.items()})
    print("Restored:", {k: len(v) for k, v in state.items()}, "as of", f"{at:%d %b %H:%M} UTC")


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        snapshot()
    elif "--reset" in sys.argv:
        reset()
    else:
        raise SystemExit(__doc__)
