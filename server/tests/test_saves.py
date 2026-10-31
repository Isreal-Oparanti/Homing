from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import what_is_it
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import AgentEvent, Job, Reading, Save, Snapshot
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.ingest.gather import Gathered, SnapshotIn
from app.jobs.handlers import HANDLERS
from app.jobs.runner import Runner
from app.main import create_app
from app.schemas.agents import KeyFacts
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

    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
    assert card["what"]["title"] == "Afreximbank internship call"
    assert "what" not in card["pending"] and "for" in card
    assert FakeGateway.calls[0]["purpose"] == "read.text"


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
