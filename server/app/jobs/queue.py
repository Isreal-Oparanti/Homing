"""The job queue, kept in Postgres. See docs/adr/0002-postgres-job-queue.md.

Every function takes the caller's session and leaves committing to the caller,
so a save and its first job can be written in one transaction.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Job

BACKOFF_BASE_S = 10
BACKOFF_CAP_S = 30 * 60
STUCK_AFTER = timedelta(minutes=15)

PRIORITY_USER = 10
PRIORITY_NORMAL = 50
PRIORITY_BACKLOG = 90


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    kind: str
    user_id: str | None
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


def backoff_seconds(attempts: int) -> int:
    """Delay before retry number `attempts`: 20s, 40s, 80s … capped at 30 minutes."""
    return min(BACKOFF_BASE_S * 2**attempts, BACKOFF_CAP_S)


def enqueue(
    db: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    user_id: str | None = None,
    priority: int = PRIORITY_NORMAL,
    dedupe_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 5,
) -> int | None:
    """Add a job. Returns its id, or None when a live job with the same dedupe key exists."""
    stmt = (
        insert(Job)
        .values(
            kind=kind,
            payload=payload or {},
            lane=get_settings().job_lane,
            user_id=user_id,
            priority=priority,
            dedupe_key=dedupe_key,
            # The database's clock, not ours: a fast local clock would make a new job look
            # like it's not due yet.
            run_after=run_after or func.now(),
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"],
            index_where=Job.status.in_(["queued", "running"]),
        )
        .returning(Job.id)
    )
    return db.execute(stmt).scalar_one_or_none()


_CLAIM = text(
    """
    UPDATE jobs
       SET status = 'running', locked_by = :worker, locked_at = now(),
           attempts = attempts + 1, updated_at = now()
     WHERE id = (
            SELECT id FROM jobs
             WHERE status = 'queued' AND lane = :lane AND run_after <= now()
             ORDER BY priority, run_after, id
             FOR UPDATE SKIP LOCKED
             LIMIT 1)
    RETURNING id, kind, user_id, payload, attempts, max_attempts
    """
)


def claim(db: Session, worker_id: str) -> ClaimedJob | None:
    """Take the next ready job in this worker's lane. Safe with many workers: each row goes
    to exactly one."""
    params = {"worker": worker_id, "lane": get_settings().job_lane}
    row = db.execute(_CLAIM, params).mappings().first()
    return ClaimedJob(**row) if row else None


def complete(db: Session, job_id: int) -> None:
    db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="done", locked_by=None, locked_at=None, last_error=None)
    )


def fail(db: Session, job: ClaimedJob, error: str, *, retryable: bool) -> str:
    """Record a failure. Returns the job's new status: queued (retry), failed or dead."""
    if not retryable:
        status, run_after = "failed", None
    elif job.attempts >= job.max_attempts:
        status, run_after = "dead", None
    else:
        status = "queued"
        run_after = func.now() + timedelta(seconds=backoff_seconds(job.attempts))
    values: dict[str, Any] = {
        "status": status,
        "locked_by": None,
        "locked_at": None,
        "last_error": error[:2000],
    }
    if run_after is not None:
        values["run_after"] = run_after
    db.execute(update(Job).where(Job.id == job.id).values(**values))
    return status


def defer(db: Session, job: ClaimedJob, until: datetime, reason: str) -> None:
    """Put a job back until `until`. The attempt it just used doesn't count."""
    db.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            status="queued",
            run_after=until,
            attempts=Job.attempts - 1,
            locked_by=None,
            locked_at=None,
            last_error=reason[:2000],
        )
    )


def requeue_stuck(db: Session, older_than: timedelta = STUCK_AFTER) -> int:
    """Put back jobs whose worker probably died mid-run. Returns how many were requeued."""
    cutoff = datetime.now(UTC) - older_than
    result = db.execute(
        update(Job)
        .where(Job.status == "running", Job.lane == get_settings().job_lane)
        .where(Job.locked_at < cutoff)
        .values(status="queued", locked_by=None, locked_at=None)
    )
    return result.rowcount or 0
