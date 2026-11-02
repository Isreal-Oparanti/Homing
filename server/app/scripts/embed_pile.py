"""Embed every readable save of a user (or of everyone) for search by meaning (S10).

New saves are embedded by the save.embed job after they're read; this catches up the rest.
Run: python -m uv run python -m app.scripts.embed_pile <user_id | all>
"""

import sys
import time

from sqlalchemy import select

from app.db.models import Reading, Save
from app.db.session import session_factory
from app.search.hybrid import embed_saves

who = sys.argv[1]
with session_factory()() as db:
    q = (
        select(Save, Reading)
        .join(Reading, Reading.save_id == Save.id)
        .where(Save.visibility == "normal", Save.status == "ready")
    )
    if who != "all":
        q = q.where(Save.user_id == who)
    rows = [(s, r) for s, r in db.execute(q).all()]
    started = time.perf_counter()
    done = embed_saves(db, rows)
    db.commit()
    print(f"{len(rows)} saves, {done} embedded in {time.perf_counter() - started:.0f}s.")
