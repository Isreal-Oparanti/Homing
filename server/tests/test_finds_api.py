from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import goal_memory
from app.agents.finds_more import queue_find
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import Find, Save, Thread
from app.db.session import get_db
from app.jobs import queue
from app.main import create_app

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}


@pytest.fixture
def client(sessions: sessionmaker[Session]) -> TestClient:
    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _find(thread: Thread, name: str, verdict: str, days: int | None) -> Find:
    return Find(
        user_id=ALICE.id,
        thread_id=thread.id,
        from_save_ids=[],
        name=name,
        what=f"{name}, a grant.",
        url=f"https://{name.lower().replace(' ', '')}.example.org/apply",
        deadline_at=datetime.now(UTC) + timedelta(days=days) if days is not None else None,
        verdict=verdict,
        rules=[],
        quotes=[],
    )


@pytest.mark.integration
def test_finds_come_best_first_and_teach_the_next_run(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    client.get("/api/v1/me", headers=HEADERS)
    with sessions() as db:
        thread = Thread(user_id=ALICE.id, title="Finding funding")
        db.add(thread)
        db.flush()
        db.add_all(
            [
                _find(thread, "Open Fund", "checked", 3),
                _find(thread, "Fit Late", "fits_you", 30),
                _find(thread, "Fit Soon", "fits_you", 5),
                _find(thread, "Check Fund", "needs_your_answer", 2),
                _find(thread, "Gone Fund", "fits_you", -1),  # closed: never listed
            ]
        )
        db.commit()
        thread_id = thread.id

    listed = client.get("/api/v1/finds", headers=HEADERS).json()
    assert [f["name"] for f in listed] == ["Fit Soon", "Fit Late", "Check Fund", "Open Fund"]
    by_name = {f["name"]: f["id"] for f in listed}

    kept = client.post(f"/api/v1/finds/{by_name['Fit Soon']}/keep", headers=HEADERS)
    assert kept.status_code == 200 and kept.json()["state"] == "kept"
    no = client.post(
        f"/api/v1/finds/{by_name['Open Fund']}/dismiss",
        json={"why": "not_my_stage"},
        headers=HEADERS,
    )
    assert no.status_code == 204
    bad = client.post(
        f"/api/v1/finds/{by_name['Fit Late']}/dismiss", json={"why": "hate it"}, headers=HEADERS
    )
    assert bad.status_code == 422

    with sessions() as db:
        memory = goal_memory.load(db, ALICE.id, thread_id)
        assert memory["kept"] == [{"name": "Fit Soon", "site": "fitsoon.example.org"}]
        assert memory["dismissed"][0]["why"] == "not_my_stage"
        assert db.scalar(select(Save.origin).where(Save.url.like("%fitsoon%"))) == "found"

    assert client.get(f"/api/v1/threads/{thread_id}/find", headers=HEADERS).json() == {
        "looking": False
    }
    with sessions() as db:
        queue_find(db, ALICE.id, thread_id, priority=queue.PRIORITY_USER, asked=True)
        db.commit()
    assert client.get(f"/api/v1/threads/{thread_id}/find", headers=HEADERS).json() == {
        "looking": True
    }


@pytest.mark.integration
def test_telling_homing_about_you_rejudges_what_it_found(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    client.get("/api/v1/me", headers=HEADERS)
    rule = {
        "rule": "residence",
        "strength": "required",
        "quote": "Open to founders based in Nigeria",
        "plain": "Based in Nigeria",
        "countries": ["NG"],
        "result": "unknown",
    }
    with sessions() as db:
        thread = Thread(user_id=ALICE.id, title="Finding funding")
        db.add(thread)
        db.flush()
        find = _find(thread, "Lagos Fund", "needs_your_answer", 10)
        find.rules = [rule]
        db.add(find)
        db.commit()

    assert [f["fit"] for f in client.get("/api/v1/finds", headers=HEADERS).json()] == [
        "Check one thing to see if it fits you"
    ]
    client.put(
        "/api/v1/me/profile",
        json={"question_id": "residence_country", "value": "NG"},
        headers=HEADERS,
    )
    assert [f["fit"] for f in client.get("/api/v1/finds", headers=HEADERS).json()] == ["Fits you"]
    client.put(
        "/api/v1/me/profile",
        json={"question_id": "residence_country", "value": "GH"},
        headers=HEADERS,
    )
    assert client.get("/api/v1/finds", headers=HEADERS).json() == []  # not for them: gone
