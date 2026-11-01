from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import whats_it_for
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import AgentEvent, Job, Reading, Save, Thread, ThreadSave
from app.db.repo.saves import content_hash
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs.errors import DeferredError
from app.jobs.runner import JobContext
from app.main import create_app
from app.schemas.agents import GoalThread, Rebuild

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}
START = datetime(2026, 1, 1, tzinfo=UTC)


class FakeGateway:
    calls: list[dict[str, Any]] = []
    plan: Rebuild = Rebuild(threads=[])

    def __init__(self, db: Session):
        pass

    def run(self, purpose: str, **kwargs: Any) -> Rebuild:
        FakeGateway.calls.append({"purpose": purpose, **kwargs})
        return FakeGateway.plan


@pytest.fixture
def client(sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    FakeGateway.calls = []
    monkeypatch.setattr(whats_it_for, "gateway_factory", FakeGateway)

    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _save(
    db: Session, n: int, title: str, *, text: str | None = None, model: str = "spark"
) -> Save:
    text = text or f"Note {n}: {title}"
    save = Save(
        user_id=ALICE.id,
        kind="note",
        origin="whatsapp",
        text=text,
        content_hash=content_hash(text),
        saved_at=START + timedelta(days=n),
        status="ready",
    )
    db.add(save)
    db.flush()
    db.add(
        Reading(
            save_id=save.id,
            title=title,
            what=f"About {title}.",
            key_facts={},
            is_checkable=False,
            is_opportunity=False,
            model=model,
            prompt_version="v",
        )
    )
    return save


def _pile(db: Session) -> dict[str, Any]:
    ensure_user(db, ALICE)
    s = [
        _save(db, n, t)
        for n, t in enumerate(
            ["YC tips", "YC deadline", "Pitch talk", "Voice drills", "Stage fright", "Random meme"],
            1,
        )
    ]
    bare = _save(
        db, 7, "An Instagram post you saved", text="https://instagram.com/p/x/", model="none"
    )
    repeat = _save(db, 8, "YC tips again", text=s[0].text)
    locked = Thread(
        user_id=ALICE.id,
        title="My YC plan",
        locked_by_user=True,
        created_by="user",
        created_at=START,
    )
    old = Thread(
        user_id=ALICE.id,
        title="Old thread",
        created_by="agent",
        created_at=START + timedelta(seconds=1),
    )
    db.add_all([locked, old])
    db.flush()
    db.add_all(
        [
            ThreadSave(thread_id=locked.id, save_id=s[1].id, added_by="agent"),
            ThreadSave(thread_id=old.id, save_id=s[2].id, added_by="agent"),
        ]
    )
    db.commit()
    return {"saves": s, "bare": bare, "repeat": repeat, "locked": locked, "old": old}


@pytest.mark.integration
def test_rebuild_organises_the_pile_and_code_checks_the_plan(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    FakeGateway.plan = Rebuild(
        threads=[
            GoalThread(title="Getting into YC", keep="T1", why="YC advice.", saves=[1, 2]),
            GoalThread(title="Your lazy habits", why="About the person.", saves=[3, 4]),
            GoalThread(title="Speaking better", why="Talks and drills.", saves=[3, 4, 5, 99]),
            GoalThread(title="Memes", why="One save.", saves=[6]),
        ]
    )
    with sessions() as db:
        pile = _pile(db)
        whats_it_for.rebuild(JobContext(db, 0, "threads.rebuild", ALICE.id), {})
        db.commit()

        sent = FakeGateway.calls[0]["inputs"]
        lines = sent["saves"].split("\n")
        assert len(lines) == 6  # the bare link and the repeat aren't sent
        assert lines[0].startswith("1 | 2026-01-02 | YC tips | About YC tips.")
        assert [t["id"] for t in sent["threads"]] == ["T1", "T2"]

        s = pile["saves"]
        locked = db.get(Thread, pile["locked"].id)
        assert locked is not None and locked.title == "My YC plan"  # the person's name stays

        def members(thread_id: str) -> set[str]:
            return set(
                db.scalars(select(ThreadSave.save_id).where(ThreadSave.thread_id == thread_id))
            )

        repeat = db.get(Save, pile["repeat"].id)
        assert repeat is not None and repeat.duplicate_of == s[0].id
        assert members(locked.id) == {s[0].id, s[1].id, repeat.id}  # the repeat follows
        speaking = db.scalars(select(Thread).where(Thread.title == "Speaking better")).one()
        assert members(speaking.id) == {s[2].id, s[3].id, s[4].id}  # line 99 ignored
        assert db.scalars(select(Thread).where(Thread.title.ilike("%lazy%"))).first() is None
        assert db.scalars(select(Thread).where(Thread.title == "Memes")).first() is None
        old = db.get(Thread, pile["old"].id)
        assert old is not None and old.archived_at is not None  # empty: archived, not deleted

        rebuilt = db.scalars(select(AgentEvent).where(AgentEvent.action == "rebuilt")).one()
        assert rebuilt.summary == (
            "Organised 5 saves into 2 goals, like 'Speaking better' (3) and 'My YC plan' (2)."
        )
        merged = db.scalars(select(AgentEvent).where(AgentEvent.action == "merged")).one()
        assert merged.summary == "You saved this before, on 2 Jan."

    listed = client.get("/api/v1/threads", headers=HEADERS).json()
    assert [t["title"] for t in listed["items"]] == ["My YC plan", "Speaking better"]
    assert listed["unplaced"] == 2  # the meme and the bare link

    detail = client.get(f"/api/v1/threads/{speaking.id}", headers=HEADERS).json()
    assert [i["title"] for i in detail["items"]] == ["Stage fright", "Voice drills", "Pitch talk"]

    bad = client.patch(
        f"/api/v1/threads/{speaking.id}", json={"title": "Your flaws"}, headers=HEADERS
    )
    assert bad.status_code == 422
    renamed = client.patch(
        f"/api/v1/threads/{speaking.id}", json={"title": "Talking on stage"}, headers=HEADERS
    ).json()
    assert renamed["title"] == "Talking on stage" and renamed["locked"] is True


@pytest.mark.integration
def test_rebuild_waits_while_an_import_is_still_being_read(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    with sessions() as db:
        _pile(db)
        unread = _save(db, 9, "Still reading")
        unread.status = "received"
        db.commit()
        since = datetime.now(UTC).isoformat()
        with pytest.raises(DeferredError):
            whats_it_for.rebuild(JobContext(db, 0, "threads.rebuild", ALICE.id), {"since": since})
        assert FakeGateway.calls == []

    assert client.post("/api/v1/threads/rebuild", headers=HEADERS).status_code == 202
    with sessions() as db:
        job = db.scalars(select(Job).where(Job.kind == "threads.rebuild")).one()
        assert job.payload == {} and job.priority == 10  # asked for: no waiting


@pytest.mark.integration
def test_a_second_look_places_what_the_first_pass_left_out(
    client: TestClient, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    plans = [
        Rebuild(threads=[GoalThread(title="Speaking better", why="Talks.", saves=[1, 2])]),
        Rebuild(
            threads=[
                GoalThread(title="Speaking better", keep="T1", why="Talks.", saves=[1, 2, 3]),
                GoalThread(title="A lone idea", why="One save.", saves=[4]),
                GoalThread(title="Cooking at home", why="Recipes.", saves=[5, 6]),
            ]
        ),
    ]

    class TwoPasses(FakeGateway):
        def run(self, purpose: str, **kwargs: Any) -> Rebuild:
            FakeGateway.calls.append({"purpose": purpose, **kwargs})
            return plans.pop(0)

    monkeypatch.setattr(whats_it_for, "gateway_factory", TwoPasses)
    with sessions() as db:
        ensure_user(db, ALICE)
        saves = [_save(db, n, f"Save {n}") for n in range(1, 15)]
        db.commit()
        whats_it_for.rebuild(JobContext(db, 0, "threads.rebuild", ALICE.id), {})
        db.commit()

        second = FakeGateway.calls[1]["inputs"]
        assert second["note"] == whats_it_for.SECOND_LOOK
        assert [t["title"] for t in second["threads"]] == ["Speaking better"]
        assert len(second["saves"].split("\n")) == 12  # only what the first pass left out

        def titles_of(save: Save) -> set[str]:
            return set(
                db.scalars(
                    select(Thread.title)
                    .join(ThreadSave, ThreadSave.thread_id == Thread.id)
                    .where(ThreadSave.save_id == save.id)
                )
            )

        # Leftovers renumber from 1: lines 1-3 are saves 3-5, 5-6 are saves 7-8.
        assert all(titles_of(s) == {"Speaking better"} for s in saves[:5])
        assert titles_of(saves[5]) == set()  # "A lone idea": a new goal needs two saves
        assert titles_of(saves[6]) == titles_of(saves[7]) == {"Cooking at home"}
        rebuilt = db.scalars(select(AgentEvent).where(AgentEvent.action == "rebuilt")).one()
        assert rebuilt.summary.startswith("Organised 7 saves into 2 goals")
