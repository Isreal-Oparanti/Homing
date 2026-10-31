"""Runs jobs from the queue on a few threads. See docs/03-agents.md#job-catalogue."""

import os
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.jobs import queue
from app.jobs.errors import PermanentError

log = get_logger("jobs")

IDLE_WAIT_S = 0.5
STUCK_CHECK_EVERY_S = 60.0


@dataclass(frozen=True)
class JobContext:
    db: Session
    job_id: int
    kind: str
    user_id: str | None


Handler = Callable[[JobContext, dict[str, Any]], None]


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


class Runner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        handlers: dict[str, Handler],
        *,
        threads: int = 3,
        worker_id: str | None = None,
    ):
        self._sessions = session_factory
        self._handlers = handlers
        self._threads = threads
        self.worker_id = worker_id or default_worker_id()
        self._stop = threading.Event()
        self._pool: list[threading.Thread] = []

    def run_once(self) -> bool:
        """Claim and run one job. Returns False when nothing was ready."""
        with self._sessions() as db:
            job = queue.claim(db, self.worker_id)
            db.commit()
        if job is None:
            return False

        fields = {"job_id": job.id, "kind": job.kind, "attempt": job.attempts}
        started = time.perf_counter()
        try:
            handler = self._handlers.get(job.kind)
            if handler is None:
                raise PermanentError(f"No handler for job kind {job.kind!r}.")
            with self._sessions() as db:
                handler(JobContext(db, job.id, job.kind, job.user_id), job.payload)
                db.commit()
            with self._sessions() as db:
                queue.complete(db, job.id)
                db.commit()
            ms = round((time.perf_counter() - started) * 1000)
            log.info("job.done", extra={"fields": {**fields, "ms": ms}})
        except PermanentError as exc:
            self._record_failure(job, str(exc), retryable=False, fields=fields)
        except Exception as exc:  # anything unexpected is retried with backoff
            self._record_failure(job, f"{type(exc).__name__}: {exc}", retryable=True, fields=fields)
        return True

    def _record_failure(
        self, job: queue.ClaimedJob, error: str, *, retryable: bool, fields: dict[str, Any]
    ) -> None:
        with self._sessions() as db:
            status = queue.fail(db, job, error, retryable=retryable)
            db.commit()
        log.warning("job.failed", extra={"fields": {**fields, "status": status, "error": error}})

    def _loop(self, index: int) -> None:
        last_stuck_check = 0.0
        while not self._stop.is_set():
            try:
                if index == 0 and time.monotonic() - last_stuck_check > STUCK_CHECK_EVERY_S:
                    last_stuck_check = time.monotonic()
                    with self._sessions() as db:
                        if n := queue.requeue_stuck(db):
                            log.warning("job.requeued_stuck", extra={"fields": {"count": n}})
                        db.commit()
                if not self.run_once():
                    self._stop.wait(IDLE_WAIT_S)
            except Exception as exc:  # keep the loop alive through DB blips
                log.error("runner.loop_error", extra={"fields": {"error": repr(exc)}})
                self._stop.wait(5.0)

    def start(self) -> None:
        self._stop.clear()
        for i in range(self._threads):
            t = threading.Thread(target=self._loop, args=(i,), name=f"runner-{i}", daemon=True)
            t.start()
            self._pool.append(t)
        log.info("runner.started", extra={"fields": {"threads": self._threads}})

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        for t in self._pool:
            t.join(timeout)
        self._pool.clear()
        log.info("runner.stopped")
