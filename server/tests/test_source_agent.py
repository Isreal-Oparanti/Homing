from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.source_agent import find_source
from app.agents.web_tools import Web
from app.core.auth import CurrentUser
from app.db.models import AgentEvent, Reading, Save
from app.db.repo.users import ensure_user
from app.jobs.runner import JobContext
from tests.test_finds_more import YEAR, FakeFetcher, _call, _message

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
SCRIPT = [
    ("open_page", {"ref": "W1"}),  # the blog post the person saved
    ("choose_source", {"page": "P1", "name_quote": "The Lagos Founders Fund"}),  # refused
    ("open_page", {"ref": "L1"}),  # its Apply link
    ("choose_source", {"page": "P2", "name_quote": f"Lagos Founders Fund {YEAR}"}),
]


class FakeWonder:
    def __init__(self) -> None:
        self.turn = 0

    def prompt(self, purpose: str) -> str:
        return "instructions"

    def chat_tools(self, purpose: str, **kw: Any) -> Any:
        assert purpose == "check.agent"
        name, args = SCRIPT[self.turn]
        self.turn += 1
        return _message(_call(name, args, self.turn))


@pytest.mark.integration
def test_wonder_follows_a_blog_to_the_official_page(sessions: sessionmaker[Session]) -> None:
    with sessions() as db:
        ensure_user(db, ALICE)
        save = Save(
            user_id=ALICE.id,
            kind="link",
            origin="paste",
            url="https://www.opportunitydesk.org/nigeria-grants",
            content_hash="b",
            status="ready",
        )
        db.add(save)
        db.flush()
        reading = Reading(
            save_id=save.id,
            title="Lagos Founders Fund",
            what="A grant for startups.",
            key_facts={},
            model="spark",
            prompt_version="v",
        )
        db.add(reading)
        db.commit()
        found = find_source(
            JobContext(db, 0, "save.check", ALICE.id),
            save,
            reading,
            "",
            gateway=FakeWonder(),
            web=Web(None, FakeFetcher()),  # type: ignore[arg-type]
        )
        assert found is not None
        url, page = found
        assert url == "https://fund.example.org/apply" and "Lagos Founders Fund" in page.text
        steps = list(db.scalars(select(AgentEvent.summary).order_by(AgentEvent.id)))
    assert steps[1] == (
        "Homing refused that source: opportunitydesk.org isn't the organisation's own site."
    )
    assert steps[-1] == "Chose fund.example.org as the source to check against."
