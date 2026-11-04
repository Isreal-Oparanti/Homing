"""Worker process: `python -m app.worker`. Runs the agents' jobs (docs/01-architecture.md)."""

import signal
import threading

from app.agents.keep_watching import start_watching
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import session_factory
from app.jobs.handlers import HANDLERS
from app.jobs.runner import Runner


def build_runner() -> Runner:
    return Runner(session_factory(), HANDLERS, threads=get_settings().worker_threads)


def main() -> None:
    setup_logging()
    with session_factory()() as db:
        start_watching(db)  # one Keep watching tick is always waiting
    runner = build_runner()
    runner.start()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    stop.wait()
    runner.stop()


if __name__ == "__main__":
    main()
