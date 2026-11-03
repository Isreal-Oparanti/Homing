from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import what_is_it
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import Job, Save, Snapshot
from app.db.session import get_db
from app.ingest.gather import Gathered, SnapshotIn
from app.ingest.pasted import parse_transcript
from app.jobs.runner import JobContext
from app.main import create_app
from app.schemas.agents import KeyFacts, Reading

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}
# As YouTube's "Show transcript" copies it, screen-reader labels and all.
COPIED = """0:00
0 seconds
welcome back to the channel
0:12
12 seconds
never ever start off with
I'm glad to be here
1:35
1 minute, 35 seconds
before you speak have a moment of silence"""


def test_youtube_transcript_copies_are_read_with_their_seconds() -> None:
    assert parse_transcript(COPIED) == [
        {"t": 0.0, "text": "welcome back to the channel"},
        {"t": 12.0, "text": "never ever start off with I'm glad to be here"},
        {"t": 95.0, "text": "before you speak have a moment of silence"},
    ]
    inline = "0:12 welcome back\n0:15 today we look at\nthree things\n1:02:05 and that's it"
    assert [s["t"] for s in parse_transcript(inline)] == [12.0, 15.0, 3725.0]


def test_text_without_timestamps_is_not_a_transcript() -> None:
    assert parse_transcript("A great talk about speaking.\nWatch it twice.") == []
    assert parse_transcript("Version 2:30 of the doc\nhello\nworld") == []


@pytest.fixture
def client(sessions: sessionmaker[Session]) -> TestClient:
    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _video(db: Session, platform: str = "youtube") -> Save:
    save = Save(
        user_id=ALICE.id,
        kind="link",
        origin="paste",
        url="https://www.youtube.com/watch?v=t260757b_vU",
        platform=platform,
        content_hash=f"v-{platform}",
        status="ready",
    )
    db.add(save)
    db.flush()
    return save


@pytest.mark.integration
def test_a_pasted_transcript_is_kept_and_read_again(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    client.get("/api/v1/me", headers=HEADERS)  # the user exists
    with sessions() as db:
        video_id, page_id = _video(db).id, _video(db, "web").id
        db.commit()

    bad = client.post(
        f"/api/v1/saves/{video_id}/transcript",
        json={"text": "no stamps here at all"},
        headers=HEADERS,
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "no_timestamps"
    page = client.post(
        f"/api/v1/saves/{page_id}/transcript", json={"text": COPIED}, headers=HEADERS
    )
    assert page.status_code == 422

    ok = client.post(f"/api/v1/saves/{video_id}/transcript", json={"text": COPIED}, headers=HEADERS)
    assert ok.status_code == 202 and ok.json() == {"lines": 3}
    with sessions() as db:
        snap = db.scalars(select(Snapshot).where(Snapshot.save_id == video_id)).one()
        assert snap.kind == "transcript" and snap.meta["source"] == "pasted"
        assert snap.text.startswith("[0:00] welcome back")
        assert db.scalars(select(Job.kind).where(Job.kind == "save.read")).one()


class SeesInputs:
    seen: dict[str, Any] = {}

    def __init__(self, db: Session):
        pass

    def run(self, purpose: str, **kwargs: Any) -> Reading:
        SeesInputs.seen = kwargs["inputs"]
        return Reading(
            title="3-2-1 speaking trick",
            what="A talk on speaking.",
            key_facts=KeyFacts(),
            is_checkable=False,
            is_opportunity=False,
        )


@pytest.mark.integration
def test_reading_again_uses_the_captions_we_already_have(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The server gets the title only; the transcript the person pasted is read too.
    monkeypatch.setattr(
        what_is_it,
        "_gather",
        lambda save: Gathered(snapshots=[SnapshotIn("metadata", "3-2-1 speaking trick", save.url)]),
    )
    monkeypatch.setattr(what_is_it, "gateway_factory", SeesInputs)
    with sessions() as db:
        from app.db.repo.users import ensure_user

        ensure_user(db, ALICE)
        video = _video(db)
        db.add(
            Snapshot(
                save_id=video.id,
                kind="transcript",
                source_url=video.url,
                text="[0:12] never ever start off with I'm glad to be here",
                meta={"segments": parse_transcript(COPIED), "source": "pasted"},
            )
        )
        db.commit()
        what_is_it.read_one(JobContext(db, 0, "save.read", ALICE.id), {"save_id": video.id})
        db.commit()
    kinds = [c["kind"] for c in SeesInputs.seen["content"]]
    assert kinds == ["metadata", "transcript"]
