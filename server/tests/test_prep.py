from typing import Any

from app.agents.prep import Video, build_sheet, read_video
from app.schemas.agents import Cite, PrepSheet, SheetItem, VideoPoint, VideoPoints
from app.verify.timestamps import check_point, keep_known_cites, numbers_supported

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
