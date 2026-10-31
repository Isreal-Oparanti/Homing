from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import AgentEvent, Job, User
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.events.emitter import emit
from app.jobs import queue
from app.jobs.errors import PermanentError, RetryableError
from app.jobs.handlers import HANDLERS
from app.jobs.runner import JobContext, Runner
from app.main import create_app

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
BOB = CurrentUser(id="u-bob", email="bob@example.com")


def test_backoff_doubles_and_caps() -> None:
    assert [queue.backoff_seconds(n) for n in (1, 2, 3)] == [20, 40, 80]
    assert queue.backoff_seconds(20) == 30 * 60


def _job(db: Session, job_id: int) -> Job:
    db.expire_all()
    return db.get(Job, job_id)  # type: ignore[return-value]


@pytest.mark.integration
def test_dedupe_allows_one_live_job_per_key(db: Session) -> None:
    first = queue.enqueue(db, "system.echo", dedupe_key="read:s1")
    second = queue.enqueue(db, "system.echo", dedupe_key="read:s1")
    db.commit()
    assert first is not None and second is None

    job = queue.claim(db, "w1")
    assert job is not None
    queue.complete(db, job.id)
    db.commit()
    assert queue.enqueue(db, "system.echo", dedupe_key="read:s1") is not None  # key free again


@pytest.mark.integration
def test_claim_takes_highest_priority_ready_job(db: Session) -> None:
    later = datetime.now(UTC) + timedelta(hours=1)
    queue.enqueue(db, "backlog", priority=queue.PRIORITY_BACKLOG)
    urgent = queue.enqueue(db, "user", priority=queue.PRIORITY_USER)
    queue.enqueue(db, "not-yet", priority=1, run_after=later)
    db.commit()

    job = queue.claim(db, "w1")
    db.commit()
    assert job is not None and job.id == urgent and job.attempts == 1
    assert _job(db, urgent).status == "running"


@pytest.mark.integration
def test_retryable_failure_backs_off_then_dies(db: Session) -> None:
    job_id = queue.enqueue(db, "flaky", max_attempts=2)
    db.commit()

    job = queue.claim(db, "w1")
    assert job is not None
    assert queue.fail(db, job, "timeout", retryable=True) == "queued"
    db.commit()
    row = _job(db, job_id)  # type: ignore[arg-type]
    assert row.run_after > datetime.now(UTC) and row.last_error == "timeout"

    # The database's clock, not ours: a small skew would make the job look not yet due.
    db.execute(update(Job).where(Job.id == job_id).values(run_after=func.now()))
    job = queue.claim(db, "w1")
    assert job is not None and job.attempts == 2
    assert queue.fail(db, job, "timeout again", retryable=True) == "dead"


@pytest.mark.integration
def test_permanent_failure_is_not_retried(db: Session) -> None:
    queue.enqueue(db, "bad")
    job = queue.claim(db, "w1")
    assert job is not None
    assert queue.fail(db, job, "unsupported file", retryable=False) == "failed"


@pytest.mark.integration
def test_stuck_jobs_are_requeued(db: Session) -> None:
    job_id = queue.enqueue(db, "slow")
    queue.claim(db, "w1")
    old = datetime.now(UTC) - timedelta(minutes=30)
    db.execute(update(Job).where(Job.id == job_id).values(locked_at=old))
    assert queue.requeue_stuck(db) == 1
    assert _job(db, job_id).status == "queued"  # type: ignore[arg-type]


@pytest.mark.integration
def test_runner_runs_echo_into_the_team_feed(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        ensure_user(db, ALICE)
        queue.enqueue(db, "system.echo", {"message": "hello"}, user_id=ALICE.id)
        db.commit()

    runner = Runner(sessions, HANDLERS, threads=1, worker_id="test")
    assert runner.run_once() is True
    assert runner.run_once() is False  # nothing left

    with sessions() as db:
        event = db.scalars(select(AgentEvent)).one()
        assert (event.user_id, event.agent, event.action, event.summary) == (
            ALICE.id,
            "system",
            "echo",
            "hello",
        )
        assert db.scalars(select(Job)).one().status == "done"


@pytest.mark.integration
def test_runner_records_handler_failures(sessions: sessionmaker[Session]) -> None:
    def flaky(ctx: JobContext, payload: dict[str, Any]) -> None:
        raise RetryableError("model timed out")

    def broken(ctx: JobContext, payload: dict[str, Any]) -> None:
        raise PermanentError("We can't read this file type yet.")

    with sessions() as db:
        retry_id = queue.enqueue(db, "flaky")
        fail_id = queue.enqueue(db, "broken")
        missing_id = queue.enqueue(db, "no-such-kind")
        db.commit()

    runner = Runner(sessions, {"flaky": flaky, "broken": broken}, threads=1, worker_id="test")
    while runner.run_once():
        pass

    with sessions() as db:
        assert _job(db, retry_id).status == "queued"  # type: ignore[arg-type]
        assert _job(db, fail_id).status == "failed"  # type: ignore[arg-type]
        assert _job(db, missing_id).status == "failed"  # type: ignore[arg-type]


@pytest.mark.integration
def test_team_feed_is_per_user(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        for user in (ALICE, BOB):
            ensure_user(db, user)
        db.flush()
        emit(db, user_id=ALICE.id, agent="system", action="echo", summary="for alice")
        emit(db, user_id=BOB.id, agent="system", action="echo", summary="for bob")
        db.commit()

    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    headers = {
        "X-Homing-Proxy-Secret": "s",
        "X-Homing-User-Id": ALICE.id,
        "X-Homing-User-Email": ALICE.email,
    }
    items = client.get("/api/v1/team", headers=headers).json()["items"]
    assert [i["summary"] for i in items] == ["for alice"]


@pytest.mark.integration
def test_me_creates_the_user_once(sessions: sessionmaker[Session]) -> None:
    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    headers = {
        "X-Homing-Proxy-Secret": "s",
        "X-Homing-User-Id": ALICE.id,
        "X-Homing-User-Email": ALICE.email,
    }
    for _ in range(2):
        response = client.get("/api/v1/me", headers=headers)
        assert response.json() == {"id": ALICE.id, "email": ALICE.email, "name": None}
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
