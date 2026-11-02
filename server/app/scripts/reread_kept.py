"""Read again the files that were only kept: videos, voice notes and documents saved before
What is it? could read them (S8 step 2). Then organise the pile again, so they find goals.

Run: python -m uv run python -m app.scripts.reread_kept <user_id>
Only queues jobs, in this machine's lane (JOB_LANE); the worker in that lane does the reading.
"""

import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.agents.what_is_it import KEPT_WORDS
from app.core.config import get_settings
from app.db.models import Reading, Save
from app.db.session import session_factory
from app.jobs import queue

user_id = sys.argv[1]
with session_factory()() as db:
    kept = db.scalars(
        select(Save)
        .join(Reading, Reading.save_id == Save.id)
        .where(
            Save.user_id == user_id,
            Save.kind.in_(KEPT_WORDS),
            Save.visibility == "normal",
            Reading.model == "none",
        )
    ).all()
    for save in kept:
        save.status = "received"
        queue.enqueue(
            db,
            "save.read",
            {"save_id": save.id},
            user_id=user_id,
            priority=queue.PRIORITY_BACKLOG,
            dedupe_key=f"read:{save.id}",
        )
    queue.enqueue(
        db,
        "threads.rebuild",
        {"since": datetime.now(UTC).isoformat()},
        user_id=user_id,
        priority=queue.PRIORITY_BACKLOG,
        dedupe_key=f"rebuild:{user_id}",
    )
    db.commit()
    print(
        f"Queued {len(kept)} kept files to read again, then a rebuild, in lane {get_settings().job_lane!r}."
    )
