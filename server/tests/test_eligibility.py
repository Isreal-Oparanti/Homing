from typing import Any

import pytest

from app.verify.eligibility import Facts, accept_rule, assess, judge
from app.verify.verdict import decide

PAGE = (
    "Candidates must be aged between 20 and 32 in the year in which they apply "
    "for the internship;\n"
    "Fluency in English or French and a working knowledge of the other.\n"
    "Students with proof of enrollment in full-time undergraduate or postgraduate study "
    "programmes are preferred.\n"
    "Children of Afreximbank staff are not eligible to participate in this programme."
)
AGE = {
    "rule": "age",
    "strength": "required",
    "quote": "Candidates must be aged between 20 and 32 in the year in which they apply",
    "plain": "Aged 20-32 in the year you apply",
    "min_age": 20,
    "max_age": 32,
}
LANGUAGE = {
    "rule": "language",
    "strength": "required",
    "quote": "Fluency in English or French and a working knowledge of the other.",
    "plain": "English or French, plus a working knowledge of the other",
    "languages_any": [{"code": "en", "level": "fluent"}, {"code": "fr", "level": "fluent"}],
    "languages_all": [{"code": "en", "level": "working"}, {"code": "fr", "level": "working"}],
}
STUDENT = {
    "rule": "student",
    "strength": "preferred",
    "quote": "proof of enrollment in full-time undergraduate or postgraduate study programmes",
    "plain": "Full-time students preferred",
    "student_status": "full_time",
}
STAFF = {
    "rule": "other",
    "strength": "required",
    "quote": "Children of Afreximbank staff are not eligible",
    "plain": "Not a child of Afreximbank staff",
    "question": "Is a parent of yours on Afreximbank's staff?",
    "yes_meets": False,
}


def _accepted(*rules: dict[str, Any]) -> list[dict[str, Any]]:
    out = [accept_rule(r, PAGE) for r in rules]
    assert all(out)
    return out  # type: ignore[return-value]


# Checking proposed rules ----------------------------------------------------------------------


def test_rules_must_quote_the_page() -> None:
    assert accept_rule({**AGE, "quote": "Applicants must be under 35"}, PAGE) is None


def test_ages_must_be_in_the_quote() -> None:
    assert accept_rule({**AGE, "max_age": 35}, PAGE) is None


def test_languages_must_be_named_in_the_quote() -> None:
    swahili = {**LANGUAGE, "languages_all": [{"code": "sw", "level": "working"}]}
    assert accept_rule(swahili, PAGE) is None


# Judging --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("languages", "result"),
    [
        ({"en": "fluent", "fr": "working"}, "meets"),
        ({"en": "fluent", "fr": "basic"}, "fails"),  # needs a working knowledge of the other
        ({"fr": "fluent", "en": "working"}, "meets"),
        ({"en": "fluent"}, "unknown"),
        ({"en": "basic", "fr": "basic"}, "fails"),
    ],
)
def test_english_or_french_plus_the_other(languages: dict[str, str], result: str) -> None:
    assert judge(LANGUAGE, Facts(languages=languages), index=0, ref_year=2027) == result


def test_age_in_the_year_you_apply() -> None:
    assert judge(AGE, Facts(birth_year=2000), index=0, ref_year=2027) == "meets"
    assert judge(AGE, Facts(birth_year=1990), index=0, ref_year=2027) == "fails"
    assert judge(AGE, Facts(), index=0, ref_year=2027) == "unknown"


def test_yes_can_mean_you_dont_meet_it() -> None:
    assert judge(STAFF, Facts(answers={"rule:3": True}), index=3, ref_year=2027) == "fails"
    assert judge(STAFF, Facts(answers={"rule:3": False}), index=3, ref_year=2027) == "meets"


def test_nationality_open_to_everyone() -> None:
    rule = {"rule": "nationality", "strength": "required", "countries": ["ANY"]}
    assert judge(rule, Facts(), index=0, ref_year=2027) == "meets"
    rule = {**rule, "countries": ["NG", "GH"]}
    assert judge(rule, Facts(nationality=["NG"]), index=0, ref_year=2027) == "meets"
    assert judge(rule, Facts(nationality=["US"]), index=0, ref_year=2027) == "fails"


# Questions ------------------------------------------------------------------------------------


def test_only_whats_missing_is_asked_and_only_for_required_rules() -> None:
    rules = _accepted(AGE, LANGUAGE, STUDENT, STAFF)
    found = assess(rules, Facts(languages={"en": "fluent"}), ref_year=2027)
    asked = [q["id"] for q in found.questions]
    # Age, French (English is known), the staff question; the preferred student rule asks nothing.
    assert asked == ["birth_year", "language:fr", "rule:3"]
    assert found.questions[1]["text"] == "How well do you speak French?"


def test_one_question_is_asked_once_across_rules() -> None:
    rules = _accepted(LANGUAGE, {**LANGUAGE, "strength": "required"})
    assert [q["id"] for q in assess(rules, Facts(), ref_year=2027).questions] == [
        "language:en",
        "language:fr",
    ]


# Verdict --------------------------------------------------------------------------------------


def _verdict(results: list[tuple[str, str]], **kw: Any) -> str:
    rules = [{"strength": s, "result": r} for s, r in results]
    args = {"closed": False, "past_deadline": False, "source_opened": True, **kw}
    return decide(rules=rules, **args)


def test_verdict_order() -> None:
    assert _verdict([("required", "fails")], closed=True) == "closed"
    assert _verdict([("required", "meets")], past_deadline=True) == "closed"
    assert _verdict([("required", "fails"), ("required", "unknown")]) == "not_for_you"
    assert _verdict([("required", "unknown")]) == "needs_your_answer"
    assert _verdict([("required", "meets")], source_opened=False) == "couldnt_confirm"
    assert _verdict([("required", "meets"), ("preferred", "fails")]) == "fits_you"
    # Not an opportunity: "fits you" means nothing, so it's just checked.
    assert _verdict([("required", "unknown")], is_opportunity=False) == "checked"
    assert _verdict([], is_opportunity=False, source_opened=False) == "couldnt_confirm"
