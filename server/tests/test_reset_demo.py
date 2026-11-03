from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import CurrentUser
from app.db.models import Moment, Save, Thread, ThreadSave
from app.db.repo.users import ensure_user
from app.scripts import reset_demo

DEMO = CurrentUser(id="demo", email="demo@homing.local")
ALICE = CurrentUser(id="u-alice", email="alice@example.com")


def _save(db: Session, user: CurrentUser, text: str) -> Save:
    save = Save(user_id=user.id, kind="note", origin="paste", text=text, content_hash=text)
    db.add(save)
    db.flush()
    return save


@pytest.mark.integration
def test_reset_puts_the_demo_back_and_touches_no_one_else(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(reset_demo, "BASELINE", tmp_path / "baseline.pkl")
    monkeypatch.setattr(reset_demo, "session_factory", lambda: sessions)
    with sessions() as db:
        for u in (DEMO, ALICE):
            ensure_user(db, u)
        db.flush()
        seeded = _save(db, DEMO, "seeded grant")
        goal = Thread(user_id=DEMO.id, title="Finding funding")
        db.add(goal)
        db.flush()
        db.add(ThreadSave(thread_id=goal.id, save_id=seeded.id, added_by="agent"))
        _save(db, ALICE, "alice's own")
        db.commit()
        goal_id = goal.id

    reset_demo.snapshot()

    with sessions() as db:  # a visitor plays with the demo
        _save(db, DEMO, "a judge's test save")
        renamed = db.get(Thread, goal_id)
        renamed.title, renamed.locked_by_user = "My renamed goal", True
        db.execute(ThreadSave.__table__.delete())
        db.add(Moment(user_id=DEMO.id, text="pitch tomorrow", at=func.now()))
        _save(db, ALICE, "alice saves more")
        db.commit()

    reset_demo.reset()

    with sessions() as db:
        demo_saves = db.scalars(select(Save.text).where(Save.user_id == DEMO.id)).all()
        assert demo_saves == ["seeded grant"]
        thread = db.get(Thread, goal_id)
        assert (thread.title, thread.locked_by_user) == ("Finding funding", False)
        assert db.scalar(select(func.count()).select_from(ThreadSave)) == 1
        assert db.scalar(select(func.count()).select_from(Moment)) == 0
        alice = db.scalars(select(Save.text).where(Save.user_id == ALICE.id)).all()
        assert sorted(alice) == ["alice saves more", "alice's own"]  # never touched
