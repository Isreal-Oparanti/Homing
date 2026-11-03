import json
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import CurrentUser
from app.db.models import AgentEvent, Ask, Reading, Save, Snapshot
from app.db.repo.users import ensure_user
from app.jobs.runner import JobContext
from app.search import ask as ask_module
from app.search import ask_agent

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
GRANT = (
    "The Glow Up Grant gives 20 women-led businesses N2 million each in equity-free funding. "
    "Applications close on 30 November. Founders must be based in Nigeria, run a registered "
    "business, and show at least six months of trading. Winners also get mentoring, a "
    "masterclass on brand building and a feature on the sponsor's channels."
)


def _call(name: str, args: dict[str, Any], n: int) -> Any:
    return SimpleNamespace(
        id=f"c{n}", function=SimpleNamespace(name=name, arguments=json.dumps(args))
    )


def _message(*calls: Any) -> Any:
    def dump(**_: Any) -> dict[str, Any]:
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                for c in calls
            ],
        }

    return SimpleNamespace(tool_calls=list(calls), content=None, model_dump=dump)


class FakeWonder:
    """Searches, opens the grant, quotes it wrong once, then fixes the quote."""

    def __init__(self, db: Session):
        self.turn = 0
        self.seen: list[Any] = []

    def prompt(self, purpose: str) -> str:
        return "instructions"

    def chat_tools(self, purpose: str, *, messages: list[dict[str, Any]], **kw: Any) -> Any:
        assert purpose == "ask.agent"
        self.seen.append(messages[-1])
        self.turn += 1
        if self.turn == 1:
            return _message(_call("search_saves", {"query": "grants for women founders"}, 1))
        if self.turn == 2:
            return _message(_call("open_save", {"save": "S1"}, 2))
        if self.turn == 3:
            wrong = {
                "point": "It gives N2 million.",
                "save": "S1",
                "quote": "gives N5 million each",
            }
            return _message(_call("submit_answer", {"points": [wrong], "not_covered": []}, 3))
        right = {
            "point": "The Glow Up Grant gives N2 million in equity-free funding.",
            "save": "S1",
            "quote": "20 women-led businesses N2 million each in equity-free funding",
        }
        never = {"point": "Apply soon.", "save": "S9", "quote": "anything"}
        if self.turn == 4:  # one good point, one from a save it never opened
            return _message(
                _call("submit_answer", {"points": [right, never], "not_covered": ["Taxes"]}, 4)
            )
        return _message(_call("submit_answer", {"points": [right], "not_covered": ["Taxes"]}, 5))


class Found:
    def __init__(self, save: Save, reading: Reading):
        self.save, self.reading, self.score = save, reading, 1.0


@pytest.mark.integration
def test_wonder_answers_and_code_is_the_gate(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeWonder
    monkeypatch.setattr(ask_agent, "gateway_factory", fake)
    with sessions() as db:
        ensure_user(db, ALICE)
        save = Save(
            user_id=ALICE.id,
            kind="link",
            origin="paste",
            url="https://g.example",
            content_hash="g",
            status="ready",
        )
        db.add(save)
        db.flush()
        reading = Reading(
            save_id=save.id,
            title="Glow Up Grant",
            what="A grant.",
            key_facts={},
            model="spark",
            prompt_version="v",
        )
        db.add_all([reading, Snapshot(save_id=save.id, kind="page_text", text=GRANT)])
        ask = Ask(user_id=ALICE.id, question="Grants for women founders?")
        db.add(ask)
        db.commit()
        monkeypatch.setattr(ask_agent, "search", lambda db, uid, q, limit: [Found(save, reading)])

        ask_module.answer(JobContext(db, 0, "ask.answer", ALICE.id), {"ask_id": ask.id})
        db.commit()
        answer = ask.answer
        assert ask.status == "done"
        assert [p["quote"] for p in answer["points"]] == [
            "20 women-led businesses N2 million each in equity-free funding"
        ]
        assert answer["dropped"] == 0 and answer["not_covered"] == ["Taxes"]
        # Refused twice: a quote not in the save, then a point from a save never opened.
        assert answer["agent"]["refusals"] == 2 and answer["agent"]["model"] == "muse-wonder-1.0"
        assert answer["agent"]["searches"] == ["grants for women founders"]
        steps = db.scalars(
            select(AgentEvent).where(AgentEvent.user_id == ALICE.id).order_by(AgentEvent.id)
        ).all()
        actions = [e.action for e in steps]
        assert actions[:3] == ["ask_searched", "ask_opened", "ask_refused"]
        refused = next(e for e in steps if e.action == "ask_refused")
        assert refused.models == []  # code refused it, not a model
        assert "isn't in S1's text word for word" in refused.summary
        assert answer["agent"]["turns"] == 5


@pytest.mark.integration
def test_when_wonder_fails_the_spark_pipeline_answers(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken:
        def __init__(self, db: Session):
            pass

        def prompt(self, purpose: str) -> str:
            return ""

        def chat_tools(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError("preview model down")

    monkeypatch.setattr(ask_agent, "gateway_factory", Broken)
    monkeypatch.setattr(
        ask_module, "_answer", lambda ctx, ask: {"points": [], "not_covered": ["x"]}
    )
    with sessions() as db:
        ensure_user(db, ALICE)
        ask = Ask(user_id=ALICE.id, question="Anything?")
        db.add(ask)
        db.commit()
        ask_module.answer(JobContext(db, 0, "ask.answer", ALICE.id), {"ask_id": ask.id})
        db.commit()
        assert ask.status == "done" and ask.answer["not_covered"] == ["x"]
        assert "agent" not in ask.answer
