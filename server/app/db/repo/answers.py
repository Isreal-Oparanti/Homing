"""Reads for the four answers on a save card, and for Today. Always scoped to one user."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Check, Job, Save, Thread, ThreadSave, When

ANSWER_JOBS = {"check": "true", "place": "for", "when": "when"}


def working_on(db: Session, save_id: str) -> set[str]:
    """The answers whose agents still have a live job for this save."""
    keys = [f"{prefix}:{save_id}" for prefix in ANSWER_JOBS]
    live = db.scalars(
        select(Job.dedupe_key).where(
            Job.dedupe_key.in_(keys), Job.status.in_(("queued", "running"))
        )
    ).all()
    return {ANSWER_JOBS[key.split(":", 1)[0]] for key in live if key}


def get_check(db: Session, save_id: str) -> Check | None:
    return db.get(Check, save_id)


def get_when(db: Session, save_id: str) -> When | None:
    return db.get(When, save_id)


def threads_of(db: Session, save: Save) -> list[tuple[Thread, int, int]]:
    """(thread, this save's position in it by save time, saves in it)."""
    rows = db.scalars(
        select(Thread)
        .join(ThreadSave, ThreadSave.thread_id == Thread.id)
        .where(ThreadSave.save_id == save.id, Thread.user_id == save.user_id)
    ).all()
    out = []
    for thread in rows:
        members = (
            select(Save.saved_at)
            .join(ThreadSave, ThreadSave.save_id == Save.id)
            .where(ThreadSave.thread_id == thread.id)
        )
        total = db.scalar(select(func.count()).select_from(members.subquery())) or 0
        before = db.scalar(
            select(func.count()).select_from(
                members.where(Save.saved_at <= save.saved_at).subquery()
            )
        )
        out.append((thread, before or 0, total))
    return out
