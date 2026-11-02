from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import Ask, Job, Reading, Save, SaveEmbedding, Snapshot
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.jobs.runner import JobContext
from app.main import create_app
from app.schemas.agents import AskAnswer, AskPick, AskPoint
from app.search import ask as ask_module
from app.search import hybrid
from app.search.hybrid import any_word, embed_saves, rrf, search

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}
TIPS = (
    "Y Combinator partners say: talk to users every week, launch before the interview, "
    "and show growth. The batch invests $500,000 in each company. " * 3
)


class FakeEmbedder:
    """Three topics, so search by meaning can be tested without the real model."""

    calls = 0

    def embed(self, texts: list[str], kind: str) -> list[list[float]]:
        FakeEmbedder.calls += 1
        out = []
        for text in texts:
            t = text.lower()
            v = [0.0] * 384
            if "yc" in t or "combinator" in t or "accelerator" in t:
                v[0] = 1.0
            elif "drum" in t:
                v[1] = 1.0
            else:
                v[2] = 1.0
            out.append(v)
        return out


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeEmbedder.calls = 0
    monkeypatch.setattr(hybrid, "embedder_factory", FakeEmbedder)


def _save(
    db: Session, title: str, *, copy: str | None = None, private: bool = False, n: int = 0
) -> Save:
    save = Save(
        user_id=ALICE.id,
        kind="note",
        origin="paste",
        text=title,
        content_hash=f"h-{title}-{n}",
        status="ready",
        visibility="private" if private else "normal",
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
            model="spark",
            prompt_version="v",
        )
    )
    if copy:
        db.add(Snapshot(save_id=save.id, kind="page_text", text=copy, meta={}))
    db.flush()
    return save


def _pile(db: Session) -> dict[str, Save]:
    ensure_user(db, ALICE)
    pile = {
        "tips": _save(db, "Tips on getting into Y Combinator", copy=TIPS),
        "interview": _save(db, "What the YC interview is like"),
        "drums": _save(db, "Worship drum short"),
        "secret": _save(db, "Combinator bank code 4417", private=True),
    }
    db.commit()
    rows = db.execute(select(Save, Reading).join(Reading, Reading.save_id == Save.id)).all()
    embed_saves(db, [(s, r) for s, r in rows])
    db.commit()
    return pile


# Pure code ----------------------------------------------------------------------------------


def test_rrf_puts_saves_both_lists_agree_on_first() -> None:
    merged = rrf(["a", "b", "c"], ["c", "a", "d"])
    assert [h.save_id for h in merged][:2] == ["a", "c"]
    assert merged[0].score == pytest.approx(1 / 61 + 1 / 62)


def test_a_question_matches_any_meaningful_word() -> None:
    assert any_word("How do I raise money for my startup?") == "raise:* | money:* | startup:*"
    assert any_word("the") == "the:*"  # nothing but filler: keep what there is


# With the database ---------------------------------------------------------------------------


@pytest.mark.integration
def test_search_finds_by_meaning_and_by_words_and_never_private(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as db:
        pile = _pile(db)
        assert (
            db.scalar(select(SaveEmbedding).where(SaveEmbedding.save_id == pile["secret"].id))
            is None
        )
        found = [f.save.id for f in search(db, ALICE.id, "YC")]
        # "YC" isn't a word in "Tips on getting into Y Combinator": only meaning finds it.
        assert pile["tips"].id in found and pile["interview"].id in found
        assert found.index(pile["interview"].id) < found.index(pile["drums"].id)
        assert pile["secret"].id not in found
        assert [f.save.id for f in search(db, ALICE.id, "drums")][0] == pile["drums"].id
        before = FakeEmbedder.calls
        rows = db.execute(select(Save, Reading).join(Reading, Reading.save_id == Save.id)).all()
        assert embed_saves(db, [(s, r) for s, r in rows]) == 0  # nothing changed: no work
        assert FakeEmbedder.calls == before


class FakeGateway:
    calls: list[dict[str, Any]] = []

    def __init__(self, db: Session):
        pass

    def run(self, purpose: str, **kwargs: Any) -> Any:
        FakeGateway.calls.append({"purpose": purpose, **kwargs})
        if purpose == "ask.select":
            lines = kwargs["inputs"]["saves"].split("\n")
            wanted = [i for i, line in enumerate(lines, 1) if "Combinator" in line or "YC" in line]
            return AskPick(saves=wanted)
        return AskAnswer(
            points=[
                AskPoint(
                    point="Talk to users every week.", save=1, quote="talk to users every week"
                ),
                AskPoint(point="Get a warm intro.", save=1, quote="ask a partner for a warm intro"),
                AskPoint(point="It invests $900,000.", save=1, quote="The batch invests $500,000"),
                AskPoint(point="Launch first.", save=7, quote="launch before the interview"),
            ],
            not_covered=["When the next batch closes."],
        )


@pytest.mark.integration
def test_ask_shows_only_points_whose_quotes_are_in_the_save(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeGateway.calls = []
    monkeypatch.setattr(ask_module, "gateway_factory", FakeGateway)
    with sessions() as db:
        pile = _pile(db)
        ask = Ask(user_id=ALICE.id, question="How do I prepare for YC?")
        db.add(ask)
        db.commit()
        ask_module.answer(JobContext(db, 0, "ask.answer", ALICE.id), {"ask_id": ask.id})
        db.commit()
        answer = ask.answer
        assert ask.status == "done" and answer is not None
        # Only the tips save has real content; the interview video is known by its title only.
        sent = FakeGateway.calls[1]["inputs"]["sources"]
        assert [s["title"] for s in sent] == ["Tips on getting into Y Combinator"]
        assert [p["point"] for p in answer["points"]] == ["Talk to users every week."]
        assert answer["points"][0]["save_id"] == pile["tips"].id
        assert answer["dropped"] == 3  # not in the save; a number it doesn't say; no such save
        assert answer["also"] == [
            {"save_id": pile["interview"].id, "title": "What the YC interview is like"}
        ]
        assert answer["not_covered"] == ["When the next batch closes."]
        assert all(pile["secret"].id not in c["save_ids"] for c in FakeGateway.calls)


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
def test_search_and_ask_endpoints(client: TestClient, sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        _pile(db)
    items = client.get("/api/v1/search", params={"q": "drums"}, headers=HEADERS).json()["items"]
    assert items[0]["title"] == "Worship drum short"
    made = client.post(
        "/api/v1/asks", json={"question": "  How do I  prepare for YC? "}, headers=HEADERS
    )
    assert made.status_code == 202 and made.json()["question"] == "How do I prepare for YC?"
    with sessions() as db:
        job = db.scalars(select(Job).where(Job.kind == "ask.answer")).one()
        assert job.priority == 10 and job.payload == {"ask_id": made.json()["id"]}
    bob = {**HEADERS, "X-Homing-User-Id": "u-bob", "X-Homing-User-Email": "bob@example.com"}
    assert client.get(f"/api/v1/asks/{made.json()['id']}", headers=bob).status_code == 404
