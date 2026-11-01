from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import what_is_it
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import AgentEvent, Import, Job, Reading, Save, Snapshot
from app.db.repo.saves import new_save_from_text
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.ingest.gather import Gathered, SnapshotIn
from app.jobs.handlers import HANDLERS
from app.jobs.runner import JobContext, Runner
from app.main import create_app
from app.schemas.agents import BatchItem, BatchReadings, DateFact, KeyFacts
from app.schemas.agents import Reading as ReadingOut

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}
AFREXIM = (
    "Afreximbank Internship Programme 2027/2028 closes TOMORROW! Requirements: aged 20–32. "
    "Apply: https://apply.workable.com/afreximbank/ Deadline: 31 October 2026."
)


class FakeGateway:
    """Replays a reading and records every call, so tests catch unexpected model calls."""

    calls: list[dict[str, Any]] = []

    def __init__(self, db: Session):
        self.db = db

    def run(self, purpose: str, **kwargs: Any) -> ReadingOut:
        FakeGateway.calls.append({"purpose": purpose, **kwargs})
        return ReadingOut(
            title="Afreximbank internship call",
            what="An internship programme in Cairo for students aged 20–32.",
            key_facts=KeyFacts(),
            is_checkable=True,
            is_opportunity=True,
        )


@pytest.fixture
def client(sessions: sessionmaker[Session]) -> TestClient:
    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeGateway.calls = []
    monkeypatch.setattr(what_is_it, "gateway_factory", FakeGateway)
    monkeypatch.setattr(
        what_is_it,
        "_gather",
        lambda save: Gathered(
            snapshots=[SnapshotIn("page_text", "Internship Opportunities. Cairo, Egypt.", save.url)]
        ),
    )


@pytest.mark.integration
def test_new_save_is_queued_once(client: TestClient, sessions: sessionmaker[Session]) -> None:
    res = client.post("/api/v1/saves", json={"text": AFREXIM}, headers=HEADERS)
    assert res.status_code == 202
    body = res.json()
    assert (body["kind"], body["platform"], body["status"]) == ("link", "web", "received")
    with sessions() as db:
        jobs = db.scalars(select(Job)).all()
        assert [(j.kind, j.dedupe_key) for j in jobs] == [("save.read", f"read:{body['id']}")]


@pytest.mark.integration
def test_secret_looking_note_is_private_and_not_echoed(client: TestClient) -> None:
    res = client.post("/api/v1/saves", json={"text": "8XK2-9QPL 7MZT-4WQR"}, headers=HEADERS)
    body = res.json()
    assert body["visibility"] == "private" and body["text"] is None

    keyed = "https://example.com/api?key=sk-abc123def456ghi789jkl012"
    body = client.post("/api/v1/saves", json={"text": keyed}, headers=HEADERS).json()
    assert body["visibility"] == "private"
    assert (body["text"], body["url"], body["label"]) == (None, None, None)


@pytest.mark.integration
def test_read_one_writes_reading_snapshot_and_event(
    client: TestClient, sessions: sessionmaker[Session], fakes: None
) -> None:
    save_id = client.post("/api/v1/saves", json={"text": AFREXIM}, headers=HEADERS).json()["id"]
    assert Runner(sessions, HANDLERS, threads=1, worker_id="t").run_once()

    with sessions() as db:
        save = db.get(Save, save_id)
        assert save is not None and save.status == "ready"
        assert db.get(Reading, save_id).title == "Afreximbank internship call"  # type: ignore[union-attr]
        assert db.scalars(select(Snapshot.kind).where(Snapshot.save_id == save_id)).all() == [
            "page_text"
        ]
        event = db.scalars(select(AgentEvent).where(AgentEvent.save_id == save_id)).one()
        assert (event.agent, event.action) == ("what", "read")
        assert event.summary.startswith("Read a page: ")
        assert [e["label"] for e in event.evidence] == ["Our copy of the page", "Original link"]

    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
    assert card["what"]["title"] == "Afreximbank internship call"
    assert "what" not in card["pending"] and "for" in card
    assert [(c["kind"], c["excerpt"]) for c in card["copies"]] == [
        ("page_text", "Internship Opportunities. Cairo, Egypt.")
    ]
    assert FakeGateway.calls[0]["purpose"] == "read.text"

    listed = client.get("/api/v1/saves", headers=HEADERS).json()["items"]
    assert listed[0]["title"] == "Afreximbank internship call"


@pytest.mark.integration
def test_any_error_on_the_last_attempt_fails_the_save(
    client: TestClient,
    sessions: sessionmaker[Session],
    fakes: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(save: Save) -> Gathered:
        raise UnicodeDecodeError("utf-8", b"", 0, 1, "bad page")

    monkeypatch.setattr(what_is_it, "_gather", broken)
    save_id = client.post("/api/v1/saves", json={"text": AFREXIM}, headers=HEADERS).json()["id"]
    with sessions() as db:
        with pytest.raises(UnicodeDecodeError):
            last_try = JobContext(db, 0, "save.read", ALICE.id, attempt=5, max_attempts=5)
            what_is_it.read_one(last_try, {"save_id": save_id})
        save = db.get(Save, save_id)
        assert save is not None and save.status == "failed"
        events = db.scalars(select(AgentEvent.action).where(AgentEvent.save_id == save_id)).all()
        assert events == ["failed"]


@pytest.mark.integration
def test_private_save_never_reaches_the_model(
    client: TestClient, sessions: sessionmaker[Session], fakes: None
) -> None:
    save_id = client.post(
        "/api/v1/saves", json={"text": "OPAY 8123456789"}, headers=HEADERS
    ).json()["id"]
    assert Runner(sessions, HANDLERS, threads=1, worker_id="t").run_once()
    assert FakeGateway.calls == []
    with sessions() as db:
        assert db.get(Reading, save_id).title == "Kept private"  # type: ignore[union-attr]


@pytest.mark.integration
def test_only_the_owner_can_reveal_a_private_save(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    save_id = client.post(
        "/api/v1/saves", json={"text": "8XK2-9QPL 7MZT-4WQR"}, headers=HEADERS
    ).json()["id"]
    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
    assert card["save"]["text"] is None

    res = client.get(f"/api/v1/saves/{save_id}/reveal", headers=HEADERS)
    assert res.json() == {"text": "8XK2-9QPL 7MZT-4WQR"}
    assert res.headers["cache-control"] == "no-store"

    with sessions() as db:
        ensure_user(db, CurrentUser(id="u-bob", email="bob@example.com"))
        db.commit()
    bob = {**HEADERS, "X-Homing-User-Id": "u-bob", "X-Homing-User-Email": "bob@example.com"}
    assert client.get(f"/api/v1/saves/{save_id}/reveal", headers=bob).status_code == 404


@pytest.mark.integration
def test_users_cannot_see_each_others_saves(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    save_id = client.post("/api/v1/saves", json={"text": "my note"}, headers=HEADERS).json()["id"]
    with sessions() as db:
        ensure_user(db, CurrentUser(id="u-bob", email="bob@example.com"))
        db.commit()
    bob = {**HEADERS, "X-Homing-User-Id": "u-bob", "X-Homing-User-Email": "bob@example.com"}
    assert client.get(f"/api/v1/saves/{save_id}", headers=bob).status_code == 404
    assert client.get("/api/v1/saves", headers=bob).json()["items"] == []


@pytest.mark.integration
def test_a_link_with_nothing_to_read_is_kept_without_a_model_guessing(
    client: TestClient, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeGateway.calls = []
    monkeypatch.setattr(what_is_it, "gateway_factory", FakeGateway)
    note = "Instagram post. We can't see inside it. Add the video or a screenshot if it matters."
    monkeypatch.setattr(what_is_it, "_gather", lambda save: Gathered(notes=[note]))
    bare = client.post(
        "/api/v1/saves", json={"text": "https://www.instagram.com/p/abc/"}, headers=HEADERS
    ).json()["id"]
    Runner(sessions, HANDLERS, threads=1, worker_id="t").run_once()
    with sessions() as db:
        reading = db.get(Reading, bare)
        assert reading is not None and reading.model == "none"
        assert (reading.title, reading.what) == ("An Instagram post you saved", note)
        event = db.scalars(select(AgentEvent).where(AgentEvent.save_id == bare)).one()
        assert event.action == "nothing_to_read"
    assert FakeGateway.calls == []

    # Words of the person's own are something to read: the agent reads them.
    labelled = client.post(
        "/api/v1/saves",
        json={"text": "https://www.instagram.com/p/xyz/ pitch deck tips"},
        headers=HEADERS,
    ).json()["id"]
    Runner(sessions, HANDLERS, threads=1, worker_id="t").run_once()
    assert [c["purpose"] for c in FakeGateway.calls] == ["read.text"]
    with sessions() as db:
        assert db.get(Reading, labelled).model != "none"  # type: ignore[union-attr]


class DatedGateway(FakeGateway):
    deadline = "Deadline: 30 June 2025"

    def run(self, purpose: str, **kwargs: Any) -> ReadingOut:
        FakeGateway.calls.append({"purpose": purpose, **kwargs})
        return ReadingOut(
            title="Fellowship call",
            what="A fellowship for founders.",
            key_facts=KeyFacts(dates=[DateFact(text=DatedGateway.deadline, role="deadline")]),
            is_checkable=True,
            is_opportunity=True,
        )


def _imported_link(db: Session, url: str, saved_at: datetime) -> str:
    ensure_user(db, ALICE)
    imp = Import(user_id=ALICE.id, storage_key="x.upload", status="done", counts={})
    db.add(imp)
    db.flush()
    save = new_save_from_text(ALICE.id, url, origin="whatsapp")
    save.import_id, save.saved_at, save.status = imp.id, saved_at, "received"
    db.add(save)
    db.commit()
    return save.id


@pytest.mark.integration
def test_an_imported_opportunity_that_closed_waits_for_check_it_now(
    client: TestClient, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeGateway.calls = []
    monkeypatch.setattr(what_is_it, "gateway_factory", DatedGateway)
    monkeypatch.setattr(
        what_is_it,
        "_gather",
        lambda save: Gathered(snapshots=[SnapshotIn("page_text", "Fellowship.", save.url)]),
    )
    with sessions() as db:
        old = _imported_link(db, "https://example.org/old", datetime(2025, 6, 1, tzinfo=UTC))
        what_is_it.read_one(JobContext(db, 0, "save.read", ALICE.id), {"save_id": old})
        db.commit()
        mine = select(Job).where(Job.payload["save_id"].astext == old)
        jobs = {j.kind: j for j in db.scalars(mine)}
        assert "save.check" not in jobs and jobs["save.when"].priority == 90
        assert "save.place" not in jobs  # placed later, with the whole pile (S9)
        held = db.scalars(
            select(AgentEvent).where(AgentEvent.save_id == old, AgentEvent.agent == "true")
        ).one()
        assert held.action == "held_off" and "date passed" in held.summary

    card = client.get(f"/api/v1/saves/{old}", headers=HEADERS).json()
    assert card["true"]["verdict"] == "not_checked"
    assert client.post(f"/api/v1/saves/{old}/check", headers=HEADERS).status_code == 202
    with sessions() as db:
        check = db.scalars(select(Job).where(Job.dedupe_key == f"check:{old}")).one()
        assert check.priority == 10  # asked for by the person: ahead of the backlog

    # Still open: checked, at the backlog's priority.
    DatedGateway.deadline = "Deadline: 30 June 2099"
    with sessions() as db:
        open_ = _imported_link(db, "https://example.org/open", datetime(2025, 6, 1, tzinfo=UTC))
        what_is_it.read_one(JobContext(db, 0, "save.read", ALICE.id), {"save_id": open_})
        db.commit()
        check = db.scalars(select(Job).where(Job.dedupe_key == f"check:{open_}")).one()
        assert check.priority == 90
    DatedGateway.deadline = "Deadline: 30 June 2025"


class BatchGateway(FakeGateway):
    """Reads S1 and S3, skips S2, and slips a date from another save into S1's facts."""

    def run(self, purpose: str, **kwargs: Any) -> Any:
        FakeGateway.calls.append({"purpose": purpose, **kwargs})
        if purpose == "read.text":
            return ReadingOut(
                title="A long page", what="A long page.", is_checkable=False, is_opportunity=False
            )
        assert [s["id"] for s in kwargs["inputs"]["saves"]] == ["S1", "S2", "S3"]
        facts = KeyFacts(
            dates=[
                DateFact(text="Deadline: 30 June 2099", role="deadline"),
                DateFact(text="Closes 1 May 2099", role="deadline"),  # S3's date, not S1's
            ]
        )
        return BatchReadings(
            readings=[
                BatchItem(
                    id="S1",
                    title="Founders grant",
                    what="A grant for founders.",
                    key_facts=facts,
                    is_checkable=True,
                    is_opportunity=True,
                ),
                BatchItem(
                    id="S3",
                    title="Design meetup",
                    what="A meetup.",
                    is_checkable=False,
                    is_opportunity=False,
                ),
            ]
        )


@pytest.mark.integration
def test_small_saves_are_read_together_and_keep_only_their_own_facts(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeGateway.calls = []
    monkeypatch.setattr(what_is_it, "gateway_factory", BatchGateway)
    pages = {
        "https://example.org/hack": "Hackathon in Lagos.",
        "https://example.org/big": "A very long page. " * 200,
    }
    monkeypatch.setattr(
        what_is_it,
        "_gather",
        lambda save: (
            Gathered(snapshots=[SnapshotIn("page_text", pages[save.url], save.url)])
            if save.url
            else Gathered()
        ),
    )
    when = datetime(2026, 10, 1, tzinfo=UTC)
    with sessions() as db:
        grant = _imported_link(db, "Founders grant. Deadline: 30 June 2099. Apply soon.", when)
        hack = _imported_link(db, "https://example.org/hack", when)
        big = _imported_link(db, "https://example.org/big", when)
        meetup = _imported_link(db, "Design meetup next week. Closes 1 May 2099.", when)
        ids = [grant, hack, big, meetup]
        what_is_it.read_batch(JobContext(db, 0, "save.read_batch", ALICE.id), {"save_ids": ids})
        db.commit()

        # The big page had a call of its own; the three small saves shared one.
        assert [c["purpose"] for c in FakeGateway.calls] == ["read.text", "read.batch"]
        dates = [d["text"] for d in db.get(Reading, grant).key_facts["dates"]]  # type: ignore[union-attr]
        assert dates == ["Deadline: 30 June 2099"]  # the borrowed date is dropped
        assert db.get(Reading, big).title == "A long page"  # type: ignore[union-attr]
        assert db.get(Reading, meetup).prompt_version == "read_batch.v1"  # type: ignore[union-attr]
        # Skipped by the model: queued to be read on its own.
        assert db.get(Reading, hack) is None
        assert db.scalars(select(Job).where(Job.dedupe_key == f"read:{hack}")).one()
        event = db.scalars(select(AgentEvent).where(AgentEvent.action == "read_batch")).one()
        assert event.summary == "Read 2 small saves together in one go, to save effort."
