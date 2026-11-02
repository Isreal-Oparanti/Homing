from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import today as today_agent
from app.agents.today import act, compose, match_moment, priority
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import (
    AgentEvent,
    Card,
    Job,
    Moment,
    Reading,
    Save,
    Thread,
    ThreadSave,
    User,
    When,
)
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs.runner import JobContext
from app.main import create_app
from app.schemas.agents import MomentMatch
from app.verify.dates import parse_moment

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}
NOW = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)  # Monday, 11:00 in Lagos


# Pure code ----------------------------------------------------------------------------------


def test_priority_is_urgency_plus_importance_minus_fatigue() -> None:
    soon = NOW + timedelta(hours=10)
    assert priority(soon, NOW) == 100
    assert priority(NOW + timedelta(hours=50), NOW, opportunity=True) == 70 + 20
    assert priority(NOW + timedelta(days=5), NOW, prep=True, thread_saves=16) == 40 + 15 + 10
    assert priority(NOW + timedelta(days=10), NOW) == 10
    assert priority(soon, NOW, dismissals=2) == 100 - 30


def test_a_moment_is_read_from_the_persons_words() -> None:
    demo = parse_moment("recording my demo on Tuesday evening", now=NOW, user_tz="Africa/Lagos")
    assert demo is not None and demo.at == datetime(2026, 11, 3, 17, 0, tzinfo=UTC)  # 18:00 Lagos
    pitch = parse_moment("pitch on 9 November at 2pm", now=NOW, user_tz="Africa/Lagos")
    assert pitch is not None and pitch.at == datetime(2026, 11, 9, 13, 0, tzinfo=UTC)
    tonight = parse_moment("pitch tonight", now=NOW, user_tz="Africa/Lagos")
    assert tonight is not None and tonight.at == datetime(2026, 11, 2, 19, 0, tzinfo=UTC)
    assert parse_moment("someday soon", now=NOW, user_tz="Africa/Lagos") is None
    assert parse_moment("interview on 11/12", now=NOW, user_tz="Africa/Lagos") is None


# Composing Today -----------------------------------------------------------------------------


def _due(db: Session, title: str, hours: float, *, thread: Thread | None = None) -> Save:
    save = Save(
        user_id=ALICE.id,
        kind="note",
        origin="paste",
        text=title,
        content_hash=f"h-{title}",
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
            is_opportunity=True,
            model="spark",
            prompt_version="v",
        )
    )
    db.add(
        When(
            save_id=save.id,
            kind="date",
            due_at=NOW + timedelta(hours=hours),
            bring_back_at=NOW - timedelta(minutes=1),
            source="reading",
            explanation="Closes soon, if the post is right.",
        )
    )
    if thread is not None:
        db.add(ThreadSave(thread_id=thread.id, save_id=save.id, added_by="agent"))
    db.flush()
    return save


def _user(db: Session) -> User:
    ensure_user(db, ALICE)
    user = db.get(User, ALICE.id)
    assert user is not None
    return user


@pytest.mark.integration
def test_never_more_than_three_new_cards_a_day_and_dismissed_never_return(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as db:
        user = _user(db)
        for i, hours in enumerate([10, 20, 30, 40, 46]):
            _due(db, f"Grant {i}", hours)
        db.commit()

        first = compose(db, user, NOW)
        db.commit()
        assert [c.title for c in first] == ["Grant 0", "Grant 1", "Grant 2"]  # most urgent first
        assert len(compose(db, user, NOW + timedelta(hours=2))) == 3  # same three, no more

        act(db, user, first[0], "dismiss", NOW)
        db.commit()
        # Dismissing doesn't open a slot today: three new cards a day, whatever happens to them.
        assert [c.title for c in compose(db, user, NOW + timedelta(hours=3))] == [
            "Grant 1",
            "Grant 2",
        ]

        tomorrow = NOW + timedelta(days=1)
        titles = [c.title for c in compose(db, user, tomorrow)]
        db.commit()
        # Grant 0 never comes back; Grant 1's date has passed; Grant 2 stays until acted on;
        # two new ones fill the room.
        assert titles == ["Grant 2", "Grant 3", "Grant 4"]
        surfaced = db.scalars(select(AgentEvent).where(AgentEvent.action == "surfaced")).all()
        assert len(surfaced) == 3 + 2


@pytest.mark.integration
def test_later_brings_a_card_back_the_next_morning(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        user = _user(db)
        _due(db, "Fellowship", 40)
        db.commit()
        card = compose(db, user, NOW)[0]
        act(db, user, card, "later", NOW)
        db.commit()
        assert card.later_until == datetime(2026, 11, 3, 8, 0, tzinfo=UTC)  # 09:00 Lagos
        assert compose(db, user, NOW + timedelta(hours=1)) == []
        back = compose(db, user, datetime(2026, 11, 3, 8, 30, tzinfo=UTC))
        assert [c.title for c in back] == ["Fellowship"]


@pytest.mark.integration
def test_a_moment_whose_goals_hold_three_saves_gets_a_prep_card(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as db:
        user = _user(db)
        demo = Thread(user_id=ALICE.id, title="Making a demo video")
        thin = Thread(user_id=ALICE.id, title="Learning guitar")
        db.add_all([demo, thin])
        db.flush()
        for i in range(3):
            _due(db, f"Demo tip {i}", 24 * 30, thread=demo)  # due far off: no deadline card
        _due(db, "Chord chart", 24 * 30, thread=thin)
        db.add_all(
            [
                Moment(
                    user_id=ALICE.id,
                    text="recording my demo",
                    at=NOW + timedelta(hours=20),
                    thread_ids=[demo.id],
                ),
                Moment(
                    user_id=ALICE.id,
                    text="guitar lesson",
                    at=NOW + timedelta(hours=20),
                    thread_ids=[thin.id],
                ),
            ]
        )
        db.commit()
        cards = [c for c in compose(db, user, NOW) if c.kind == "prep"]
        assert [c.title for c in cards] == ["Get ready: recording my demo"]  # 1 save isn't enough
        assert (
            cards[0].next_step
            == "3 of your saves can help: Making a demo video. Go over them first."
        )


class FakeGateway:
    def __init__(self, db: Session):
        pass

    def run(self, purpose: str, **kwargs: Any) -> MomentMatch:
        assert purpose == "when.match_moment"
        return MomentMatch(threads=["T1", "T9", "T2"])  # T9 isn't one of theirs


@pytest.mark.integration
def test_matching_a_moment_keeps_only_real_goals(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(today_agent, "gateway_factory", FakeGateway)
    with sessions() as db:
        _user(db)
        goals = [
            Thread(user_id=ALICE.id, title=t) for t in ("Demo video", "Speaking", "YC", "Drums")
        ]
        db.add_all(goals)
        db.flush()
        moment = Moment(user_id=ALICE.id, text="recording my demo", at=NOW + timedelta(days=1))
        db.add(moment)
        db.commit()
        match_moment(JobContext(db, 0, "moment.match", ALICE.id), {"moment_id": moment.id})
        db.commit()
        assert moment.thread_ids == [goals[0].id, goals[1].id]  # only real goals
        event = db.scalars(select(AgentEvent).where(AgentEvent.action == "moment_set")).one()
        assert event.summary.startswith("Noted: recording my demo,")


# API ------------------------------------------------------------------------------------------


@pytest.fixture
def client(sessions: sessionmaker[Session]) -> TestClient:
    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


@pytest.mark.integration
def test_moments_cards_and_calendar_over_the_api(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    made = client.post(
        "/api/v1/moments", json={"text": "demo day on Friday at 3pm"}, headers=HEADERS
    )
    assert made.status_code == 202 and made.json()["display"].endswith("15:00 Lagos time")
    vague = client.post("/api/v1/moments", json={"text": "someday soon"}, headers=HEADERS)
    assert vague.status_code == 422
    with sessions() as db:
        assert db.scalars(select(Job).where(Job.kind == "moment.match")).one()
        save = _due(db, "Grant & fund; apply", 12)
        db.commit()
        save_id = save.id

    page = client.get("/api/v1/today", headers=HEADERS).json()
    assert [m["text"] for m in page["moments"]] == ["demo day on Friday at 3pm"]
    card = page["cards"][0]
    assert card["save_id"] == save_id and card["kind"] == "deadline"
    done = client.post(f"/api/v1/cards/{card['id']}/act", json={"action": "use"}, headers=HEADERS)
    assert done.status_code == 200
    assert client.get("/api/v1/today", headers=HEADERS).json()["cards"] == []
    bad = client.post(f"/api/v1/cards/{card['id']}/act", json={"action": "delete"}, headers=HEADERS)
    assert bad.status_code == 422

    ics = client.get(f"/api/v1/saves/{save_id}/calendar.ics", headers=HEADERS)
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Grant & fund\\; apply" in ics.text and "TRIGGER:-P1D" in ics.text
    with sessions() as db:
        assert db.scalars(select(Card).where(Card.state == "used")).one()
