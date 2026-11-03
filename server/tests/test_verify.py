from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.verify.dates import bring_back_at, display, parse_deadline
from app.verify.quotes import accepts, match_quote

LAGOS = "Africa/Lagos"
SOURCE = (
    "Internship Opportunities\n\nLocation:  Cairo, Cairo Governorate, Egypt.\n"
    "Candidates must be “fluent” in English or French, with a working knowledge of the other.\n"
    "Interns who relocate receive a housing allowance of $500 per month.\n"
    "Full–time study is preferred."
)


# Quotes ---------------------------------------------------------------------------------


def test_exact_quote_maps_back_to_the_original_text() -> None:
    m = match_quote("Cairo, Cairo Governorate, Egypt", SOURCE)
    assert m is not None and m.score == 100
    assert SOURCE[m.start : m.end] == "Cairo, Cairo Governorate, Egypt"


def test_quotes_dashes_and_spacing_are_normalised() -> None:
    m = match_quote('must be "fluent" in English or French', SOURCE)
    assert m is not None and m.score == 100
    assert SOURCE[m.start : m.end] == "must be “fluent” in English or French"
    assert match_quote("Full-time study is preferred", SOURCE) is not None


def test_a_small_typo_is_accepted_but_a_different_claim_is_not() -> None:
    typo = match_quote("Interns who relocate recieve a housing allowance of $500 per month", SOURCE)
    assert typo is not None and 92 <= typo.score < 100
    assert (
        match_quote("Interns who relocate receive a housing allowance of $900 a week", SOURCE)
        is None
    )
    assert match_quote("Candidates must be fluent in Spanish only", SOURCE) is None


def test_the_threshold_is_exactly_92() -> None:
    assert accepts(92, 40)
    assert not accepts(91.9, 40)


def test_short_quotes_must_be_exact() -> None:
    assert not accepts(99, 11)
    assert accepts(100, 11)


def test_quotes_under_three_words_need_a_number() -> None:
    assert match_quote("Cairo", SOURCE) is None
    assert match_quote("$500", SOURCE) is not None
    assert match_quote("$700", SOURCE) is None


def test_pasting_is_not_quoting() -> None:
    assert match_quote(SOURCE * 2, SOURCE * 3) is None


# Dates ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "base", "shown", "tz_stated", "time_stated"),
    [
        # The golden rows in docs/05-verification.md.
        (
            "Deadline: 31 October 2026.",
            datetime(2026, 10, 20, tzinfo=UTC),
            "Sat 31 Oct, 23:59",
            False,
            False,
        ),
        ("Nov 4, 9 PM ET", datetime(2026, 10, 30, tzinfo=UTC), "Thu 5 Nov, 03:00", True, True),
        (
            "closes TOMORROW",
            datetime(2026, 10, 30, 13, 5, tzinfo=UTC),
            "Sat 31 Oct, 23:59",
            False,
            False,
        ),
        (
            "Deadline: November 2, 2026",
            datetime(2026, 10, 20, tzinfo=UTC),
            "Mon 2 Nov, 23:59",
            False,
            False,
        ),
        # Others seen in real posts.
        (
            "Applications CLOSE: 20 July 2025",
            datetime(2025, 6, 1, tzinfo=UTC),
            "Sun 20 Jul, 23:59",
            False,
            False,
        ),
        (
            "closes 5pm WAT on 3 November",
            datetime(2026, 10, 1, tzinfo=UTC),
            "Tue 3 Nov, 17:00",
            True,
            True,
        ),
        (
            "Deadline: 2026-11-20 17:00 +02:00",
            datetime(2026, 10, 1, tzinfo=UTC),
            "Fri 20 Nov, 16:00",
            True,
            True,
        ),
        (
            "Date limite : 15 novembre 2026",
            datetime(2026, 10, 1, tzinfo=UTC),
            "Sun 15 Nov, 23:59",
            False,
            False,
        ),
        # YC's page, 1 Nov: "on-time" made the date search find only "8pm".
        (
            "The deadline to apply on-time is November 2 at 8pm PT",
            datetime(2026, 11, 1, 10, tzinfo=UTC),
            "Tue 3 Nov, 05:00",
            True,
            True,
        ),
        # The Meta hackathon page, 2 Nov: the time comes a few words after the date.
        (
            "Nov 4: Project submissions due by 9:00 PM ET",
            datetime(2026, 11, 2, 10, tzinfo=UTC),
            "Thu 5 Nov, 03:00",
            True,
            True,
        ),
    ],
)
def test_deadlines(
    text: str, base: datetime, shown: str, tz_stated: bool, time_stated: bool
) -> None:
    d = parse_deadline(text, base=base, user_tz=LAGOS)
    assert d is not None
    assert display(d.at, LAGOS) == f"{shown} Lagos time"
    assert (d.tz_stated, d.time_stated) == (tz_stated, time_stated)


@pytest.mark.parametrize(
    ("text", "year"),
    [
        ("Oct 25, 11:59 PM ET: Applications Deadline", 2026),  # just passed: this year's
        ("Closes 30 Aug", 2027),  # passed long ago: the next one
        ("Applications close Jan 15", 2027),
        ("Oct 25 2027 deadline", 2027),  # a stated year is kept
    ],
)
def test_a_date_with_no_year_that_just_passed_means_this_year(text: str, year: int) -> None:
    d = parse_deadline(text, base=datetime(2026, 11, 2, 13, tzinfo=UTC), user_tz=LAGOS)
    assert d is not None and d.at.year == year


def test_a_weekday_deadline_is_the_next_one_after_it_was_written() -> None:
    tuesday = datetime(2026, 11, 3, 9, tzinfo=UTC)
    d = parse_deadline("Apply by Friday", base=tuesday, user_tz=LAGOS)
    assert d is not None and display(d.at, LAGOS) == "Fri 6 Nov, 23:59 Lagos time" and d.relative
    d = parse_deadline("Applications close this Friday at 5pm", base=tuesday, user_tz=LAGOS)
    assert d is not None and display(d.at, LAGOS) == "Fri 6 Nov, 17:00 Lagos time"
    assert parse_deadline("Black Friday sale", base=tuesday, user_tz=LAGOS) is None


@pytest.mark.parametrize("text", ["mid-September to early December", "Aged 20-32", "in 2016", ""])
def test_vague_or_non_dates_give_nothing(text: str) -> None:
    assert parse_deadline(text, base=datetime(2026, 10, 1, tzinfo=UTC), user_tz=LAGOS) is None


def test_relative_dates_use_the_message_time_in_the_users_zone() -> None:
    # 23:30 Lagos on 30 Oct is 22:30 UTC: "tomorrow" is the 31st, not the 1st.
    d = parse_deadline(
        "closes tomorrow", base=datetime(2026, 10, 30, 22, 30, tzinfo=UTC), user_tz=LAGOS
    )
    assert d is not None and d.relative
    assert display(d.at, LAGOS) == "Sat 31 Oct, 23:59 Lagos time"


# Bringing saves back ----------------------------------------------------------------------


NOW = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)


def _lagos(dt: datetime | None) -> str | None:
    return dt.astimezone(ZoneInfo(LAGOS)).strftime("%d %b %H:%M") if dt else None


def test_bring_back_a_week_before_a_far_deadline_at_9am() -> None:
    assert _lagos(bring_back_at(NOW + timedelta(days=10), now=NOW, user_tz=LAGOS)) == "03 Nov 09:00"


def test_bring_back_two_days_before_a_near_deadline() -> None:
    assert _lagos(bring_back_at(NOW + timedelta(days=4), now=NOW, user_tz=LAGOS)) == "02 Nov 09:00"


def test_bring_back_now_when_under_48_hours_and_never_once_past() -> None:
    assert bring_back_at(NOW + timedelta(hours=20), now=NOW, user_tz=LAGOS) == NOW
    assert bring_back_at(NOW - timedelta(hours=1), now=NOW, user_tz=LAGOS) is None
