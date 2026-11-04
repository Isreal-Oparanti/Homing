from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.read_agent import FOUND_BY, dig, is_thin
from app.agents.web_tools import Web
from app.core.auth import CurrentUser
from app.db.models import AgentEvent, Save
from app.db.repo.users import ensure_user
from app.jobs.runner import JobContext
from tests.test_finds_more import FakeFetcher, FakeSearch, _call, _message

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
BLOG = "https://www.opportunitydesk.org/nigeria-grants"


class FakeWonder:
    def __init__(self, script: list[tuple[str, dict[str, Any]]]) -> None:
        self.script = script
        self.turn = 0

    def prompt(self, purpose: str) -> str:
        return "instructions"

    def chat_tools(self, purpose: str, **kw: Any) -> Any:
        assert purpose == "read.agent"
        name, args = self.script[self.turn]
        self.turn += 1
        return _message(_call(name, args, self.turn))


def _save(db: Session, text: str) -> Save:
    ensure_user(db, ALICE)
    save = Save(
        user_id=ALICE.id,
        kind="note",
        origin="paste",
        text=text,
        content_hash=text[:8],
        status="reading",
    )
    db.add(save)
    db.commit()
    return save


def test_only_thin_link_saves_dig() -> None:
    def save(**kw: Any) -> Save:
        return Save(user_id="u", origin="paste", content_hash="h", **kw)

    post = save(kind="note", text=f"this 👇 {BLOG}")
    assert is_thin(post, ["Grants"])
    assert not is_thin(post, ["word " * 60])  # the first read got enough
    wall = "Please enable JavaScript to view this page. " + "Menu Home About Contact " * 12
    assert is_thin(post, [wall])  # words, but only a wall's
    link = save(kind="link", url="https://example.org/a-blank-app-page")
    assert is_thin(link, [])  # any link, not just posts: a page that loaded blank
    assert not is_thin(save(kind="note", text="call mum"), [])  # nothing to follow
    assert not is_thin(save(kind="note", text=f"this {BLOG}", import_id="i"), [])  # imports
    assert not is_thin(save(kind="image"), [])


@pytest.mark.integration
def test_wonder_follows_the_posts_link(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        save = _save(db, f"this 👇 {BLOG}")
        found = dig(
            JobContext(db, 0, "save.read", ALICE.id),
            save,
            [""],
            gateway=FakeWonder(
                [
                    ("open_page", {"ref": "W1"}),  # the link in the post
                    ("read_this", {"page": "P1", "about_quote": "grants Nigerian founders"}),
                ]
            ),
            web=Web(None, FakeFetcher()),  # type: ignore[arg-type]
        )
        assert found is not None
        assert found.source_url == BLOG and found.meta["found_by"] == FOUND_BY
        assert "Lagos Founders Fund" in found.text
        steps = list(db.scalars(select(AgentEvent.action).order_by(AgentEvent.id)))
    assert steps == ["dig_started", "dig_opened", "dig_found"]


@pytest.mark.integration
def test_a_searched_page_must_name_what_the_save_names(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        save = _save(db, "Lagos Founders Fund 👀 https://x.com/i/status/123")
        found = dig(
            JobContext(db, 0, "save.read", ALICE.id),
            save,
            [""],
            gateway=FakeWonder(
                [
                    ("web_search", {"query": "Lagos Founders Fund"}),  # W2: the blog
                    ("open_page", {"ref": "W2"}),
                    ("open_page", {"ref": "L1"}),  # its Apply link: the official page
                    # Not reached from the save's links, and these words aren't in the save.
                    ("read_this", {"page": "P2", "about_quote": "N5 million in equity-free"}),
                    ("read_this", {"page": "P2", "about_quote": "Lagos Founders Fund"}),
                ]
            ),
            web=Web(FakeSearch(), FakeFetcher()),  # type: ignore[arg-type]
        )
        assert found is not None and found.source_url == "https://fund.example.org/apply"
        refused = db.scalar(select(AgentEvent.summary).where(AgentEvent.action == "dig_refused"))
    assert refused is not None and "aren't in the save" in refused


@pytest.mark.integration
def test_wonder_can_decide_the_save_says_enough(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        save = _save(db, f"Applications close Friday {BLOG}")
        found = dig(
            JobContext(db, 0, "save.read", ALICE.id),
            save,
            [""],
            gateway=FakeWonder([("enough", {"why": "The post says all there is."})]),
            web=Web(None, FakeFetcher()),  # type: ignore[arg-type]
        )
        last = db.scalar(select(AgentEvent.summary).order_by(AgentEvent.id.desc()).limit(1))
    assert found is None
    assert last == "Stopped looking: The post says all there is."
