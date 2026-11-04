from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import is_it_true, keep_watching
from app.core.auth import CurrentUser
from app.db.models import AgentEvent, Check, Job, Reading, Save, Snapshot, Thread, ThreadSave
from app.db.repo.users import ensure_user
from app.jobs.runner import JobContext
from tests.test_finds_more import FakeFetcher

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
URL = "https://fund.example.org/apply"


def _watched(db: Session, last_copy: str) -> Save:
    ensure_user(db, ALICE)
    save = Save(
        user_id=ALICE.id,
        kind="link",
        origin="paste",
        url=URL,
        content_hash="w",
        status="ready",
    )
    thread = Thread(user_id=ALICE.id, title="Finding funding")
    db.add_all([save, thread])
    db.flush()
    db.add_all(
        [
            Reading(
                save_id=save.id,
                title="Lagos Founders Fund",
                what="A grant.",
                key_facts={},
                is_opportunity=True,
                model="spark",
                prompt_version="v",
            ),
            Check(
                save_id=save.id,
                verdict="fits_you",
                official_url=URL,
                model="spark",
                prompt_version="v",
            ),
            Snapshot(save_id=save.id, kind="official_text", source_url=URL, text=last_copy),
            ThreadSave(thread_id=thread.id, save_id=save.id),
        ]
    )
    db.commit()
    return save


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(is_it_true, "fetcher_factory", FakeFetcher)


@pytest.mark.integration
def test_a_changed_official_page_is_checked_again(
    sessions: sessionmaker[Session], web: None
) -> None:
    with sessions() as db:
        save = _watched(db, "Applications close on 30 November. Open to everyone.")
        keep_watching.watch_user(JobContext(db, 0, "watch.user", ALICE.id), {})
        db.commit()
        jobs = {(j.kind, j.payload.get("recheck")) for j in db.scalars(select(Job))}
        assert ("save.check", True) in jobs  # the changed page is checked again
        assert ("goal.find", None) in jobs  # and What's it for? looks for more for the goal
        said = db.scalar(select(AgentEvent.summary).where(AgentEvent.action == "watched"))
        assert said == (
            "Kept watching: re-read 1 official page. 1 had new words "
            "(Lagos Founders Fund), so it's checked again."
        )
        assert save.id


@pytest.mark.integration
def test_an_unchanged_page_costs_nothing(sessions: sessionmaker[Session], web: None) -> None:
    same = is_it_true._fetch_source(URL, "Lagos Founders Fund", FakeFetcher())
    assert same is not None
    with sessions() as db:
        _watched(db, same.text)
        keep_watching.watch_user(JobContext(db, 0, "watch.user", ALICE.id), {})
        db.commit()
        assert db.scalar(select(Job.id).where(Job.kind == "save.check")) is None
        said = db.scalar(select(AgentEvent.summary).where(AgentEvent.action == "watched"))
        assert said == "Kept watching: re-read 1 official page. Nothing changed."


@pytest.mark.integration
def test_one_tick_is_always_waiting(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        keep_watching.start_watching(db)
        keep_watching.start_watching(db)  # the worker restarting doesn't add a second
        ticks = db.scalars(select(Job).where(Job.kind == "watch.tick")).all()
        assert len(ticks) == 1
        assert ticks[0].run_after == keep_watching.next_watch(datetime.now(UTC))
        ticks[0].status = "done"  # it ran: the tick queues the next one before anything else
        keep_watching.tick(JobContext(db, 0, "watch.tick", None), {})
        db.commit()
        waiting = db.scalars(
            select(Job).where(Job.kind == "watch.tick", Job.status == "queued")
        ).all()
        assert len(waiting) == 1


def test_watching_runs_at_five_in_the_morning_and_evening_lagos_time() -> None:
    assert keep_watching.next_watch(datetime(2026, 11, 4, 3, 30, tzinfo=UTC)) == datetime(
        2026, 11, 4, 4, 0, tzinfo=UTC
    )
    assert keep_watching.next_watch(datetime(2026, 11, 4, 16, 30, tzinfo=UTC)) == datetime(
        2026, 11, 5, 4, 0, tzinfo=UTC
    )


def test_a_recheck_says_exactly_what_changed() -> None:
    from app.agents.is_it_true import what_changed

    before = (datetime(2026, 11, 12, 22, 59, tzinfo=UTC), "fits_you", 2)
    moved = Check(deadline_at=datetime(2026, 11, 15, 22, 59, tzinfo=UTC), verdict="fits_you")
    moved.eligibility = [{}, {}]
    assert what_changed(before, moved, "Africa/Lagos") == [
        "the deadline moved from 12 Nov to 15 Nov"
    ]
    closed = Check(deadline_at=before[0], verdict="closed")
    closed.eligibility = [{}, {}, {}]
    assert what_changed(before, closed, "Africa/Lagos") == [
        "it's now closed",
        "who can apply changed",
    ]
    same = Check(deadline_at=before[0], verdict="fits_you")
    same.eligibility = [{}, {}]
    assert what_changed(before, same, "Africa/Lagos") == []
