from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import prep
from app.agents.prep import Video, build_sheet, make_reel, prepare, read_video
from app.core.auth import CurrentUser
from app.db.models import AgentEvent, Card, Moment, Reading, Save, Snapshot, Thread, ThreadSave
from app.db.repo.users import ensure_user
from app.jobs.runner import JobContext
from app.schemas.agents import Cite, PrepSheet, SheetItem, VideoPoint, VideoPoints
from app.verify.timestamps import CheckedPoint, check_point, keep_known_cites, numbers_supported

SEGMENTS = [
    {"t": 0.0, "text": "welcome back to the channel"},
    {"t": 12.4, "text": "never ever start off with I'm glad to be here"},
    {"t": 16.0, "text": "lead with something surprising instead"},
    {"t": 95.2, "text": "before you speak have a moment of silence"},
    {"t": 99.0, "text": "then deliver the line"},
]
MOMENT = "Recording my 3-minute demo video."


def test_a_real_second_and_quote_are_kept() -> None:
    p = check_point("Open with a bold line.", 12, 18, "never ever start off with", SEGMENTS, 120)
    assert p is not None and (p.t_start, p.quote) == (12, "never ever start off with")


def test_a_made_up_second_is_dropped() -> None:
    assert check_point("Open bold.", 50, 60, "never ever start off with", SEGMENTS, 120) is None


def test_a_quote_from_elsewhere_in_the_video_is_dropped() -> None:
    assert check_point("Pause first.", 12, 18, "have a moment of silence", SEGMENTS, 120) is None


def test_seconds_outside_the_video_are_dropped() -> None:
    assert check_point("x", 130, 140, "then deliver the line", SEGMENTS, 120) is None


def test_numbers_the_speaker_never_said_are_dropped() -> None:
    quote = "have a moment of silence"
    assert check_point("Pause for 10 seconds.", 95, 100, quote, SEGMENTS, 120) is None
    # Numbers from the moment itself are fine.
    kept = check_point("Pause, then fit 3 minutes.", 95, 100, quote, SEGMENTS, 120, context=MOMENT)
    assert kept is not None


def test_numbers_supported() -> None:
    assert numbers_supported("Cut to 3 minutes", "a 3-minute demo")
    assert not numbers_supported("Practise for 10 minutes", "get 1% better each day")


def test_unknown_citations_are_dropped_then_empty_items() -> None:
    items = [
        {"text": "a", "cites": [{"video": "V1", "t": 12}, {"video": "V9", "t": 1}]},
        {"text": "b", "cites": [{"video": "V2", "t": 5}]},
    ]
    kept, dropped = keep_known_cites(items, {("V1", 12)})
    assert [i["text"] for i in kept] == ["a"] and dropped == 2


class FakeGateway:
    def run(self, purpose: str, **kwargs: Any) -> Any:
        if purpose == "video.points":
            return VideoPoints(
                points=[
                    VideoPoint(
                        point="Open bold.", t_start=12, t_end=18, quote="never ever start off with"
                    ),
                    VideoPoint(point="Invented.", t_start=50, t_end=55, quote="nothing like this"),
                ]
            )
        return PrepSheet(
            agree=[SheetItem(text="Open bold.", cites=[Cite(video="V1", t=12)])],
            checklist=[
                SheetItem(text="Open bold in the first line.", cites=[Cite(video="V1", t=12)]),
                SheetItem(text="Practise 10 times.", cites=[Cite(video="V1", t=12)]),
                SheetItem(text="Use a teleprompter.", cites=[Cite(video="V1", t=50)]),
            ],
        )


def test_the_sheet_keeps_only_what_the_videos_back_up() -> None:
    video = Video(id="V1", title="Talk", url="https://www.youtube.com/watch?v=x", segments=SEGMENTS)
    read_video(FakeGateway(), video, moment=MOMENT, user_id=None)  # type: ignore[arg-type]
    assert [p.t_start for p in video.points] == [12] and video.dropped == 1

    sheet = build_sheet(FakeGateway(), [video], moment=MOMENT, user_id=None)  # type: ignore[arg-type]
    assert [i["text"] for i in sheet["checklist"]] == ["Open bold in the first line."]
    assert sheet["dropped_cites"] == 1


def test_the_reel_pads_merges_and_stops_at_three_minutes() -> None:
    video = Video(id="V1", title="Talk", url="u", segments=SEGMENTS, duration_s=400)
    video.points = [CheckedPoint("Open bold.", 12, 18, "q"), CheckedPoint("Pause.", 20, 30, "q")]
    long = Video(id="V2", title="Long", url="u", segments=SEGMENTS, duration_s=4000)
    long.points = [CheckedPoint("Rehearse.", 1000, 1170, "q")]
    sheet = {
        "checklist": [
            {"text": "a", "cites": [{"video": "V1", "t": 12}]},
            {"text": "b", "cites": [{"video": "V1", "t": 20}]},  # touches the first: merged
            {"text": "c", "cites": [{"video": "V2", "t": 1000}]},  # 185s: over three minutes
        ],
        "agree": [{"text": "d", "cites": [{"video": "V9", "t": 1}]}],  # unknown: skipped
    }
    assert make_reel(sheet, [video, long]) == [{"video": "V1", "start": 9, "end": 42}]


# The card.prep job ---------------------------------------------------------------------------

ALICE = CurrentUser(id="u-alice", email="alice@example.com")


@pytest.mark.integration
def test_a_prep_card_gets_a_sheet_from_the_goals_videos(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prep, "gateway_factory", lambda db: FakeGateway())
    with sessions() as db:
        ensure_user(db, ALICE)
        goal = Thread(user_id=ALICE.id, title="Speaking better")
        db.add(goal)
        db.flush()
        for n, (platform, captions) in enumerate(
            [("youtube", True), ("youtube", False), ("instagram", False)]
        ):
            save = Save(
                user_id=ALICE.id,
                kind="link",
                origin="paste",
                url=f"https://example.com/{n}",
                platform=platform,
                content_hash=f"h{n}",
                status="ready",
            )
            db.add(save)
            db.flush()
            db.add(
                Reading(
                    save_id=save.id,
                    title=f"Video {n}",
                    what="A talk.",
                    key_facts={},
                    model="spark",
                    prompt_version="v",
                )
            )
            db.add(ThreadSave(thread_id=goal.id, save_id=save.id, added_by="agent"))
            if captions:
                db.add(
                    Snapshot(
                        save_id=save.id,
                        kind="transcript",
                        source_url=save.url,
                        text="...",
                        meta={"segments": SEGMENTS},
                    )
                )
        moment = Moment(
            user_id=ALICE.id, text="recording my demo", at=datetime.now(UTC), thread_ids=[goal.id]
        )
        db.add(moment)
        db.flush()
        card = Card(
            user_id=ALICE.id,
            kind="prep",
            moment_id=moment.id,
            thread_ids=[goal.id],
            title="Get ready: recording my demo",
            why_now="soon",
            next_step="Go over them.",
            payload={"saves": 3},
            dedupe_key=f"prep:{moment.id}",
        )
        db.add(card)
        db.commit()

        prepare(JobContext(db, 0, "card.prep", ALICE.id), {"card_id": card.id})
        db.commit()
        sheet = card.payload["sheet"]
        assert card.payload["saves"] == 3  # what the card had stays
        assert sheet["status"] == "ready"
        assert [i["text"] for i in sheet["checklist"]] == ["Open bold in the first line."]
        assert sheet["videos"]["V1"]["points"][0]["t_start"] == 12
        assert sheet["reel"] == [{"video": "V1", "start": 9, "end": 30}]
        assert sheet["skipped"] == {"no_captions": 1, "reels": 1, "others": 0}
        assert sheet["dropped_points"] == 1
        said = db.scalars(select(AgentEvent.summary).where(AgentEvent.card_id == card.id)).all()
        assert said[0].startswith("Went through 'Video 0' for recording my demo: 1 points")
        assert said[-1].startswith("Prep sheet ready for recording my demo: 1 steps")
