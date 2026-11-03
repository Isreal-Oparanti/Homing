from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import what_is_it
from app.core.auth import CurrentUser
from app.core.config import Settings
from app.db.models import AgentEvent, Job, ModelCall, Save
from app.db.repo.saves import new_save_from_text
from app.db.repo.users import ensure_user
from app.ingest.gather import Gathered
from app.jobs import queue
from app.jobs.errors import DeferredError
from app.jobs.runner import JobContext, Runner
from app.llm.gateway import BudgetExceeded, ModelGateway

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
DEMO = CurrentUser(id="demo", email="demo@homing.local")
READING = (
    '{"title": "t", "what": "w", "key_facts": {}, "is_checkable": false, "is_opportunity": false}'
)
INPUTS = {"save": {"text": "hello"}}


def _settings(total: int = 1_000_000, per_user: int = 10_000, demo: int = 5_000) -> Settings:
    return Settings(
        model_daily_token_budget=total,
        model_user_daily_token_budget=per_user,
        model_demo_daily_token_budget=demo,
    )


def _used(db: Session, user_id: str, tokens: int, *, days_ago: int = 0) -> None:
    db.add(
        ModelCall(
            user_id=user_id,
            purpose="read.text",
            model="m",
            prompt_version="v",
            input_hash=f"h-{user_id}-{tokens}-{days_ago}",
            status="ok",
            tokens_in=tokens,
            tokens_out=0,
            created_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stand in for the model: count calls and return a valid reading."""
    made: list[str] = []

    def complete(self: ModelGateway, p: Any, model: str, *args: Any) -> str:
        made.append(p.name)
        return READING

    monkeypatch.setattr(ModelGateway, "_complete", complete)
    return made


@pytest.mark.integration
def test_user_over_budget_is_deferred_without_a_call(
    sessions: sessionmaker[Session], calls: list[str]
) -> None:
    with sessions() as db:
        ensure_user(db, ALICE)
        _used(db, ALICE.id, 9_000)
        with pytest.raises(BudgetExceeded) as exc:
            ModelGateway(db, _settings()).run(
                "read.text", user_id=ALICE.id, inputs=INPUTS, save_ids=[]
            )
    assert calls == []
    assert exc.value.until > datetime.now(UTC)


@pytest.mark.integration
def test_yesterday_does_not_count(sessions: sessionmaker[Session], calls: list[str]) -> None:
    with sessions() as db:
        ensure_user(db, ALICE)
        _used(db, ALICE.id, 9_000, days_ago=1)
        ModelGateway(db, _settings()).run("read.text", user_id=ALICE.id, inputs=INPUTS, save_ids=[])
    assert calls == ["read.text"]


@pytest.mark.integration
def test_the_shared_demo_has_its_own_cap(sessions: sessionmaker[Session], calls: list[str]) -> None:
    with sessions() as db:
        ensure_user(db, ALICE)
        ensure_user(db, DEMO)
        _used(db, ALICE.id, 4_000)
        _used(db, DEMO.id, 4_000)
        gateway = ModelGateway(db, _settings())
        gateway.run("read.text", user_id=ALICE.id, inputs=INPUTS, save_ids=[])
        with pytest.raises(BudgetExceeded):
            gateway.run("read.text", user_id=DEMO.id, inputs={"save": {"text": "x"}}, save_ids=[])
    assert calls == ["read.text"]


@pytest.mark.integration
def test_everyones_total_is_capped_too(sessions: sessionmaker[Session], calls: list[str]) -> None:
    with sessions() as db:
        ensure_user(db, ALICE)
        _used(db, ALICE.id, 2_000)
        with pytest.raises(BudgetExceeded):
            ModelGateway(db, _settings(total=3_000, per_user=1_000_000)).run(
                "read.text", user_id=ALICE.id, inputs=INPUTS, save_ids=[]
            )
    assert calls == []


@pytest.mark.integration
def test_cached_answers_are_free_even_over_budget(
    sessions: sessionmaker[Session], calls: list[str]
) -> None:
    with sessions() as db:
        ensure_user(db, ALICE)
        ModelGateway(db, _settings()).run("read.text", user_id=ALICE.id, inputs=INPUTS, save_ids=[])
        _used(db, ALICE.id, 50_000)
        ModelGateway(db, _settings()).run("read.text", user_id=ALICE.id, inputs=INPUTS, save_ids=[])
    assert calls == ["read.text"]


@pytest.mark.integration
def test_deferred_job_keeps_its_attempt(sessions: sessionmaker[Session]) -> None:
    until = datetime.now(UTC) + timedelta(hours=5)

    def over_budget(ctx: JobContext, payload: dict[str, Any]) -> None:
        raise DeferredError("Today's model budget is used up.", until)

    with sessions() as db:
        job_id = queue.enqueue(db, "costly")
        db.commit()
    assert Runner(sessions, {"costly": over_budget}, threads=1, worker_id="t").run_once()
    with sessions() as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert (job.status, job.attempts) == ("queued", 0)
        assert abs((job.run_after - until).total_seconds()) < 1


@pytest.mark.integration
def test_paused_saves_say_so_and_the_team_hears_once(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    class OverBudget:
        def __init__(self, db: Session):
            pass

        def run(self, purpose: str, **kwargs: Any) -> Any:
            raise BudgetExceeded("Today's model budget is used up.", datetime.now(UTC))

    monkeypatch.setattr(what_is_it, "gateway_factory", OverBudget)
    monkeypatch.setattr(what_is_it, "_gather", lambda save: Gathered())
    with sessions() as db:
        ensure_user(db, ALICE)
        ids = []
        for text in ("first note", "second note"):
            save = new_save_from_text(ALICE.id, text)
            db.add(save)
            db.flush()
            ids.append(save.id)
        db.commit()
        for sid in ids:
            with pytest.raises(BudgetExceeded):
                what_is_it.read_one(JobContext(db, 0, "save.read", ALICE.id), {"save_id": sid})
        for sid in ids:
            save = db.get(Save, sid)
            assert save is not None
            assert (save.status, save.error) == ("received", what_is_it.PAUSED)
        paused = db.scalar(
            select(func.count()).select_from(AgentEvent).where(AgentEvent.action == "paused")
        )
        assert paused == 1
