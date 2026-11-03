from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.calendar_ics import Event, calendar, fold
from app.core.auth import CurrentUser, calendar_token, user_from_calendar_token
from app.core.config import Settings, get_settings
from app.db.models import Card, Check, Moment, Reading, Save, When
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.main import create_app

ALICE = CurrentUser(id="google:123", email="alice@example.com")
BOB = CurrentUser(id="u-bob", email="bob@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}


def test_a_feed_link_opens_only_its_own_calendar() -> None:
    token = calendar_token(ALICE.id, "s")
    assert user_from_calendar_token(token, "s") == ALICE.id
    assert user_from_calendar_token(token, "other secret") is None
    body, _, sig = token.partition(".")
    bob_body = calendar_token(BOB.id, "s").partition(".")[0]
    assert user_from_calendar_token(f"{bob_body}.{sig}", "s") is None  # Alice's signature
    assert user_from_calendar_token("nonsense", "s") is None


def test_long_lines_are_folded_at_75_bytes() -> None:
    line = "DESCRIPTION:" + "Closes Thu 5 Nov, 03:00 Lagos time – é " * 6
    folded = fold(line)
    parts = folded.split("\r\n")
    assert all(len(p.encode()) <= 75 for p in parts)
    assert "".join(p.removeprefix(" ") for p in parts) == line
    text = calendar(
        [
            Event(
                uid="x", start=datetime(2026, 11, 5, tzinfo=UTC), summary="a, b; c", description="d"
            )
        ]
    )
    assert "SUMMARY:a\\, b\\; c" in text and text.endswith("END:VCALENDAR\r\n")


def _save(
    db: Session, user: CurrentUser, title: str, days: float, verdict: str | None = None
) -> Save:
    save = Save(user_id=user.id, kind="note", origin="paste", text=title, content_hash=f"h-{title}")
    db.add(save)
    db.flush()
    db.add(
        Reading(
            save_id=save.id, title=title, what="x", key_facts={}, model="spark", prompt_version="v"
        )
    )
    due = datetime.now(UTC) + timedelta(days=days)
    db.add(
        When(
            save_id=save.id,
            kind="date",
            due_at=due,
            bring_back_at=due - timedelta(days=2),
            source="reading",
            explanation="Closes soon, if the post is right.",
        )
    )
    if verdict:
        db.add(Check(save_id=save.id, verdict=verdict, model="spark", prompt_version="v"))
    db.flush()
    return save


@pytest.mark.integration
def test_the_feed_holds_your_dates_and_moments(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        for u in (ALICE, BOB):
            ensure_user(db, u)
        db.flush()
        grant = _save(db, ALICE, "Grant for founders", 6)
        _save(db, ALICE, "Not for me fellowship", 6, verdict="not_for_you")
        _save(db, BOB, "Bob's grant", 6)
        moment = Moment(
            user_id=ALICE.id, text="recording my demo", at=datetime.now(UTC) + timedelta(days=1)
        )
        db.add(moment)
        db.flush()
        card = Card(
            user_id=ALICE.id,
            kind="prep",
            moment_id=moment.id,
            title="Get ready",
            why_now="soon",
            next_step="Go over them.",
            dedupe_key=f"prep:{moment.id}",
        )
        db.add(card)
        db.commit()
        grant_id, card_id = grant.id, card.id

    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    settings = Settings(
        proxy_secret="s", public_api_url="https://api.test", web_url="https://web.test"
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    links = client.get("/api/v1/me/calendar", headers=HEADERS).json()
    assert links["webcal_url"].startswith("webcal://api.test/api/v1/calendar/")
    assert links["google_url"].startswith(
        "https://calendar.google.com/calendar/r?cid=webcal%3A%2F%2F"
    )

    # No sign-in: the calendar app only has the link.
    feed = client.get(links["https_url"].removeprefix("https://api.test"))
    assert feed.status_code == 200 and feed.headers["content-type"].startswith("text/calendar")
    text = feed.text.replace("\r\n ", "")  # unfold
    assert "X-WR-CALNAME:Homing" in text
    assert "SUMMARY:Grant for founders" in text and f"https://web.test/saves/{grant_id}" in text
    assert "TRIGGER;VALUE=DATE-TIME:" in text  # reminded when Homing brings it back
    assert "Not for me fellowship" not in text and "Bob's grant" not in text
    assert "SUMMARY:Recording my demo" in text and f"https://web.test/cards/{card_id}" in text

    assert client.get("/api/v1/calendar/forged.token.ics").status_code == 404
