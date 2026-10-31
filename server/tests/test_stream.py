import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1 import team
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.repo.users import ensure_user
from app.events.emitter import emit
from app.main import create_app

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}


@pytest.fixture
def client(sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # The stream reads through session_factory(), so point it at the test schema.
    monkeypatch.setattr(team, "session_factory", lambda: sessions)
    monkeypatch.setattr(team, "STREAM_MAX_S", 0.2)
    monkeypatch.setattr(team, "POLL_S", 0.05)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    return TestClient(app)


def _read(client: TestClient, headers: dict[str, str]) -> str:
    with client.stream("GET", "/api/v1/events/stream", headers=headers) as res:
        assert res.status_code == 200
        return "".join(res.iter_text())


@pytest.mark.integration
def test_stream_opens_with_resume_point_and_replays_after_it(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    with sessions() as db:
        ensure_user(db, ALICE)
        first = emit(db, user_id=ALICE.id, agent="system", action="echo", summary="one")
        db.commit()
        first_id = first.id

    # A fresh stream starts from now, and says so, so a reconnect resumes rather than skips.
    body = _read(client, HEADERS)
    assert body.startswith(f"id: {first_id}\n")
    assert "event: agent_event" not in body

    with sessions() as db:
        second = emit(db, user_id=ALICE.id, agent="system", action="echo", summary="two")
        db.commit()
        second_id = second.id

    # Reconnecting with that id replays only what came after it.
    body = _read(client, {**HEADERS, "Last-Event-ID": str(first_id)})
    assert f"id: {second_id}\nevent: agent_event" in body
    assert '"summary":"one"' not in body
