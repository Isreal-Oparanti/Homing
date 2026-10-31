from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import is_it_true, what_is_it, whats_it_for
from app.agents.whats_it_for import clean_title
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import AgentEvent
from app.db.session import get_db
from app.ingest.ats import _pick_job, workable_parts
from app.ingest.gather import Gathered, SnapshotIn
from app.jobs.handlers import HANDLERS
from app.jobs.runner import Runner
from app.main import create_app
from app.schemas.agents import (
    DateFact,
    KeyFacts,
    LanguageNeed,
    Placement,
    ProposedCheck,
    ProposedFinding,
    ProposedRule,
    Reading,
)
from app.verify.sources import official_candidates
from app.verify.status import is_closed

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}
OFFICIAL_URL = "https://apply.workable.com/afreximbank/j/A424364E0D/"


def _day(days: int) -> str:
    d = datetime.now(UTC) + timedelta(days=days)
    return f"{d.day} {d:%B} {d.year}"


POST = (
    "Afreximbank Internship Programme closes soon! Requirements: aged 20–32. "
    f"Apply: https://apply.workable.com/afreximbank/ Deadline: {_day(5)}."
)
OFFICIAL = (
    "Internship Opportunities\nLocation: Cairo, Cairo Governorate, Egypt\nWorkplace: on-site\n"
    "Candidates must be aged between 20 and 32 in the year in which they apply.\n"
    "Fluency in English or French and a working knowledge of the other.\n"
    f"Applications close on {_day(3)}."
)
LANGUAGE_RULE = ProposedRule(
    rule="language",
    strength="required",
    quote="Fluency in English or French and a working knowledge of the other.",
    plain="English or French, plus a working knowledge of the other",
    languages_any=[
        LanguageNeed(code="en", level="fluent"),
        LanguageNeed(code="fr", level="fluent"),
    ],
    languages_all=[
        LanguageNeed(code="en", level="working"),
        LanguageNeed(code="fr", level="working"),
    ],
)


class FakeModels:
    """Answers each purpose the way the real model would, and records every call."""

    calls: list[str] = []
    dates: list[DateFact] = []
    checkable = True
    deadline_quote: str | None = None
    rules: list[ProposedRule] = []

    def __init__(self, db: Session):
        pass

    def run(self, purpose: str, **kwargs: Any) -> Any:
        FakeModels.calls.append(purpose)
        if purpose == "read.text":
            return Reading(
                title="Afreximbank internship call",
                what="An internship call from Afreximbank.",
                key_facts=KeyFacts(dates=FakeModels.dates, organisations=["Afreximbank"]),
                is_checkable=FakeModels.checkable,
                is_opportunity=FakeModels.checkable,
            )
        if purpose == "check.compare":
            return ProposedCheck(
                is_same_opportunity=True,
                findings=[
                    ProposedFinding(
                        point="It's on-site in Cairo.",
                        quote="Cairo, Cairo Governorate, Egypt",
                        kind="left_out",
                    ),
                    # Not on the page: code must drop it.
                    ProposedFinding(
                        point="You need Swahili.",
                        quote="Applicants must speak Swahili fluently",
                        kind="left_out",
                    ),
                ],
                deadline_quote=FakeModels.deadline_quote,
                rules=FakeModels.rules,
            )
        if purpose == "place.assign":
            threads = kwargs["inputs"]["threads"]
            if threads:
                return Placement(thread_id=threads[0]["id"], reason="Another opportunity.")
            return Placement(new_thread_title="Funding and opportunities", reason="An opening.")
        raise AssertionError(purpose)


@pytest.fixture
def client(sessions: sessionmaker[Session]) -> TestClient:
    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeModels.calls = []
    FakeModels.dates = [DateFact(text=f"Deadline: {_day(5)}.", role="deadline")]
    FakeModels.checkable = True
    FakeModels.deadline_quote = f"Applications close on {_day(3)}."
    FakeModels.rules = []
    for agent in (what_is_it, is_it_true, whats_it_for):
        monkeypatch.setattr(agent, "gateway_factory", FakeModels)
    monkeypatch.setattr(what_is_it, "_gather", lambda save: Gathered())
    monkeypatch.setattr(
        is_it_true,
        "_find_official",
        lambda save, reading: (OFFICIAL_URL, SnapshotIn("page_text", OFFICIAL, OFFICIAL_URL)),
    )


def _save_and_run(client: TestClient, sessions: sessionmaker[Session], text: str) -> str:
    save_id = client.post("/api/v1/saves", json={"text": text}, headers=HEADERS).json()["id"]
    runner = Runner(sessions, HANDLERS, threads=1, worker_id="t")
    while runner.run_once():
        pass
    return save_id


@pytest.mark.integration
def test_all_four_answers_fill_in(client: TestClient, sessions: sessionmaker[Session]) -> None:
    save_id = _save_and_run(client, sessions, POST)
    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()

    assert card["pending"] == []
    true = card["true"]
    assert true["verdict"] == "fits_you"  # the page opened and no rule excludes you
    assert true["official_url"] == OFFICIAL_URL
    assert [f["point"] for f in true["findings"]] == ["It's on-site in Cairo."]  # Swahili dropped
    assert true["deadline"]["source_text"] == f"Applications close on {_day(3)}."

    assert card["for"]["threads"][0]["title"] == "Funding and opportunities"
    assert card["for"]["threads"][0]["position"] == 1

    when = card["when"]
    assert (when["kind"], when["source"]) == ("date", "check")  # the official date wins
    assert when["explanation"].endswith("per the official page.")

    with sessions() as db:
        actions = db.scalars(select(AgentEvent.action).where(AgentEvent.save_id == save_id)).all()
    assert {"read", "checked", "placed", "when_set"} <= set(actions)

    today = client.get("/api/v1/today", headers=HEADERS).json()
    assert [c["save_id"] for c in today["cards"]] == [save_id]
    assert today["cards"][0]["next_step"] == "It fits you. Apply before it closes."
    assert today["cards"][0]["unconfirmed"] is False


@pytest.mark.integration
def test_the_posts_date_is_used_when_the_official_page_has_none(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    FakeModels.deadline_quote = None
    save_id = _save_and_run(client, sessions, POST)
    when = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()["when"]
    assert (when["kind"], when["source"]) == ("date", "reading")
    assert when["explanation"].endswith("if the post is right.")
    card = client.get("/api/v1/today", headers=HEADERS).json()["cards"][0]
    assert card["unconfirmed"] is True


@pytest.mark.integration
def test_nothing_to_check_and_no_date(client: TestClient, sessions: sessionmaker[Session]) -> None:
    FakeModels.checkable = False
    FakeModels.dates = []
    save_id = _save_and_run(client, sessions, "A talk on speaking https://example.com/talk")
    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
    assert card["true"] == {"verdict": "nothing_to_check"}
    assert card["when"]["kind"] == "none"
    assert "check.compare" not in FakeModels.calls
    assert client.get("/api/v1/today", headers=HEADERS).json()["cards"] == []


@pytest.mark.integration
def test_a_repeat_is_merged_without_asking_the_model(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    first = _save_and_run(client, sessions, POST)
    second = _save_and_run(client, sessions, POST)
    card = client.get(f"/api/v1/saves/{second}", headers=HEADERS).json()
    assert card["for"]["duplicate_of"] == first
    assert card["for"]["threads"][0]["count"] == 2
    assert FakeModels.calls.count("place.assign") == 1
    with sessions() as db:
        merged = db.scalars(
            select(AgentEvent.summary).where(
                AgentEvent.save_id == second, AgentEvent.action == "merged"
            )
        ).one()
    assert merged.startswith("You saved this before, on ")


@pytest.mark.integration
def test_a_save_we_cant_see_inside_isnt_placed(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    FakeModels.checkable = False
    FakeModels.dates = []
    save_id = _save_and_run(client, sessions, "https://www.instagram.com/reel/ABC123/")
    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
    assert card["for"] == {"threads": [], "duplicate_of": None}
    assert "place.assign" not in FakeModels.calls


# Pure code ---------------------------------------------------------------------------------


def test_thread_titles_are_goals_never_labels_about_the_person() -> None:
    assert clean_title("getting into YC") == "Getting into YC"
    assert clean_title("Your procrastination habits") is None
    assert clean_title("Introverted founder traits") is None
    assert clean_title("x" * 61) is None
    assert clean_title("🔥🔥") is None


def test_a_linkedin_job_page_counts_but_a_linkedin_post_does_not() -> None:
    urls = [
        "https://www.linkedin.com/posts/someone_hiring-activity-123",
        "https://www.linkedin.com/jobs/view/4012345678/",
    ]
    assert official_candidates(urls, []) == ["https://www.linkedin.com/jobs/view/4012345678/"]


def test_official_candidates_prefer_application_sites_and_skip_chat_links() -> None:
    urls = [
        "https://whatsapp.com/channel/0029VbDa9OiLY6dCMm0lpA2G/205",
        "https://example.org/blog/afreximbank-internship",
        "https://apply.workable.com/afreximbank/",
        "https://x.com/someone/status/1",
    ]
    assert official_candidates(urls, ["Afreximbank"]) == [
        "https://apply.workable.com/afreximbank/",
        "https://example.org/blog/afreximbank-internship",
    ]


def test_closed_signals_come_from_the_page() -> None:
    closed = is_closed("Applications are now closed. Thank you.")
    assert closed is not None and closed.quote == "Applications are now closed"
    assert is_closed("Apply now", http_status=404).kind == "dead_link"
    assert is_closed("Applications close on 3 November") is None


def test_workable_links_and_picking_the_job() -> None:
    assert workable_parts("https://apply.workable.com/afreximbank/j/a424364e0d/") == (
        "afreximbank",
        "A424364E0D",
    )
    assert workable_parts("https://apply.workable.com/j/A424364E0D") == (None, "A424364E0D")
    assert workable_parts("https://apply.workable.com/afreximbank/") == ("afreximbank", None)
    jobs = [
        {"title": "Investment Manager", "shortcode": "878EE60088"},
        {"title": "Internship Opportunities", "shortcode": "A424364E0D"},
    ]
    picked = _pick_job(jobs, "Afreximbank Internship Programme 2027/2028")
    assert picked is not None and picked["shortcode"] == "A424364E0D"
    assert _pick_job(jobs, None) is None
    assert _pick_job(jobs, "Scholarship for engineers") is None


@pytest.mark.integration
def test_one_answer_rejudges_every_opportunity(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    FakeModels.rules = [LANGUAGE_RULE]
    first = _save_and_run(client, sessions, POST)
    second = _save_and_run(client, sessions, POST.replace("Internship", "Fellowship"))

    card = client.get(f"/api/v1/saves/{first}", headers=HEADERS).json()
    assert card["true"]["verdict"] == "needs_your_answer"
    assert [q["id"] for q in card["true"]["questions"]] == ["language:en", "language:fr"]
    assert card["true"]["rules"][0]["quote"] == LANGUAGE_RULE.quote
    today = client.get("/api/v1/today", headers=HEADERS).json()["cards"]
    assert today[0]["next_step"] == "Answer 2 questions to see if it fits you."

    def answer(qid: str, value: str) -> str:
        res = client.post(
            f"/api/v1/saves/{first}/answer",
            json={"question_id": qid, "value": value},
            headers=HEADERS,
        )
        assert res.status_code == 200
        return res.json()["summary"]

    assert answer("language:en", "fluent") == "Saved your answer."  # still waiting on French
    summary = answer("language:fr", "basic")
    assert summary == "Used your answer on 2 saved opportunities: 2 aren't for you."
    for save_id in (first, second):
        card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
        assert card["true"]["verdict"] == "not_for_you"
        assert card["true"]["rules"][0]["result"] == "fails"
    assert client.get("/api/v1/today", headers=HEADERS).json()["cards"] == []

    profile = client.get("/api/v1/me/profile", headers=HEADERS).json()
    assert profile["languages"] == {"en": "fluent", "fr": "basic"}
    res = client.put(
        "/api/v1/me/profile",
        json={"question_id": "language:fr", "value": "working"},
        headers=HEADERS,
    )
    assert res.status_code == 200
    card = client.get(f"/api/v1/saves/{first}", headers=HEADERS).json()
    assert card["true"]["verdict"] == "fits_you"


@pytest.mark.integration
def test_a_bad_answer_is_refused(client: TestClient, sessions: sessionmaker[Session]) -> None:
    save_id = _save_and_run(client, sessions, POST)
    res = client.post(
        f"/api/v1/saves/{save_id}/answer",
        json={"question_id": "birth_year", "value": 1850},
        headers=HEADERS,
    )
    assert res.status_code == 422


@pytest.mark.integration
def test_without_an_official_page_rules_come_from_the_post(
    client: TestClient, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(is_it_true, "_find_official", lambda save, reading: None)
    FakeModels.rules = [
        ProposedRule(
            rule="age",
            strength="required",
            quote="Requirements: aged 20–32",
            plain="Aged 20-32",
            min_age=20,
            max_age=32,
        ),
        # Not in the post: code must drop it.
        ProposedRule(
            rule="other",
            strength="required",
            quote="Must hold a Swahili certificate",
            plain="Swahili certificate",
            question="Do you hold a Swahili certificate?",
        ),
    ]
    save_id = _save_and_run(client, sessions, POST)
    true = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()["true"]
    assert true["from_post"] is True and true["official_url"] is None
    assert [r["plain"] for r in true["rules"]] == ["Aged 20-32"]
    assert true["verdict"] == "needs_your_answer"
    assert "post's own words" in true["note"]


@pytest.mark.integration
def test_without_an_official_page_a_passed_post_deadline_means_closed(
    client: TestClient, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(is_it_true, "_find_official", lambda save, reading: None)
    FakeModels.dates = [
        DateFact(text="Applications close 20 July 2025", role="deadline"),
        DateFact(text="Pitch day 30 July 2025", role="event"),
    ]
    FakeModels.rules = [
        ProposedRule(
            rule="age",
            strength="required",
            quote="Requirements: aged 20–32",
            plain="Aged 20-32",
            min_age=20,
            max_age=32,
        )
    ]
    save_id = _save_and_run(client, sessions, POST)
    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
    assert card["true"]["verdict"] == "closed" and card["true"]["questions"] == []
    # Over: "When" names the closing date, not the later pitch day.
    assert card["when"]["explanation"].startswith("Closed on Sun 20 Jul")
