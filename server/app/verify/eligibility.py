"""Eligibility, judged by code against what the person has told Homing (docs/05 · Eligibility).

The model proposes rules with quotes. Code keeps a rule only if its quote is on the page and
its details match the quote, then judges it: `meets`, `fails` or `unknown`. Every unknown
becomes one plain question; one answer re-judges every opportunity that depends on it.
"""

from dataclasses import dataclass, field
from typing import Any

from app.verify.quotes import match_quote
from app.verify.timestamps import numbers_supported

LEVELS = {"none": 0, "basic": 1, "working": 2, "fluent": 3}
LEVEL_WORDS = {"fluent": "fluent", "working": "a working knowledge", "basic": "basic"}
LANGUAGE_NAMES = {
    "en": ("english", "anglais"),
    "fr": ("french", "français", "francais"),
    "ar": ("arabic", "arabe"),
    "pt": ("portuguese", "portugais"),
    "es": ("spanish", "espagnol"),
    "sw": ("swahili",),
    "de": ("german", "allemand"),
    "zh": ("chinese", "mandarin"),
    "ha": ("hausa",),
    "yo": ("yoruba",),
    "ig": ("igbo",),
    "am": ("amharic",),
}
STUDENT = ["full_time", "part_time", "not_student"]
EDUCATION = ["secondary", "undergraduate", "postgraduate", "graduate"]


@dataclass
class Facts:
    """What the person has told Homing (the profile), plus answers for this opportunity."""

    birth_year: int | None = None
    nationality: list[str] = field(default_factory=list)
    residence_country: str | None = None
    student_status: str | None = None
    education_level: str | None = None
    languages: dict[str, str] = field(default_factory=dict)
    company_registered: bool | None = None
    answers: dict[str, Any] = field(default_factory=dict)  # "rule:3" → True/False


# Checking proposed rules ----------------------------------------------------------------------


def _names(code: str) -> tuple[str, ...]:
    return LANGUAGE_NAMES.get(code.lower(), (code.lower(),))


def accept_rule(rule: dict[str, Any], page: str) -> dict[str, Any] | None:
    """The rule with its quote as it appears on the page, or None if it doesn't hold up."""
    found = match_quote(rule.get("quote", ""), page)
    if found is None:
        return None
    quote = page[found.start : found.end]
    kind = rule.get("rule")
    if kind == "age":
        ages = " ".join(str(a) for a in (rule.get("min_age"), rule.get("max_age")) if a is not None)
        if not ages or not numbers_supported(ages, quote):
            return None
    if kind == "language":
        needs = rule.get("languages_any", []) + rule.get("languages_all", [])
        said = quote.lower()
        if not needs or not all(any(n in said for n in _names(x["code"])) for x in needs):
            return None
    if kind in ("nationality", "residence") and not rule.get("countries"):
        return None
    if kind == "other" and not rule.get("question"):
        return None
    return {**rule, "quote": quote, "verified": True}


# Judging ------------------------------------------------------------------------------------


def _languages(rule: dict[str, Any], facts: Facts) -> str:
    def level(code: str) -> int | None:
        have = facts.languages.get(code.lower())
        return LEVELS.get(have) if have else None

    def need(x: dict[str, Any]) -> bool | None:
        have = level(x["code"])
        return None if have is None else have >= LEVELS[x["level"]]

    any_of = [need(x) for x in rule.get("languages_any", [])]
    all_of = [need(x) for x in rule.get("languages_all", [])]
    if any_of and all(r is False for r in any_of) or False in all_of:
        return "fails"
    any_ok = not any_of or any(r is True for r in any_of)
    all_ok = all(r is True for r in all_of)
    return "meets" if any_ok and all_ok else "unknown"


def judge(rule: dict[str, Any], facts: Facts, *, index: int, ref_year: int) -> str:
    """`meets`, `fails` or `unknown` for one rule."""
    kind = rule.get("rule")
    if kind == "age":
        if facts.birth_year is None:
            return "unknown"
        age = ref_year - facts.birth_year
        low, high = rule.get("min_age"), rule.get("max_age")
        ok = (low is None or age >= low) and (high is None or age <= high)
        return "meets" if ok else "fails"
    if kind in ("nationality", "residence"):
        countries = [c.upper() for c in rule.get("countries", [])]
        if "ANY" in countries:
            return "meets"
        mine = facts.nationality if kind == "nationality" else [facts.residence_country or ""]
        mine = [c.upper() for c in mine if c]
        if not mine:
            return "unknown"
        return "meets" if set(mine) & set(countries) else "fails"
    if kind == "student":
        if facts.student_status is None:
            return "unknown"
        if rule.get("student_status") == "full_time":
            return "meets" if facts.student_status == "full_time" else "fails"
        return "meets" if facts.student_status in ("full_time", "part_time") else "fails"
    if kind == "education":
        if facts.education_level is None:
            return "unknown"
        return "meets" if facts.education_level in rule.get("education_levels", []) else "fails"
    if kind == "language":
        return _languages(rule, facts)
    if kind == "company":
        if facts.company_registered is None or rule.get("company_registered") is None:
            return "unknown"
        return "meets" if facts.company_registered == rule["company_registered"] else "fails"
    answer = facts.answers.get(f"rule:{index}")
    if answer is None:
        return "unknown"
    return "meets" if bool(answer) == bool(rule.get("yes_meets", True)) else "fails"


# Questions ----------------------------------------------------------------------------------


def _ask(qid: str, text: str, kind: str) -> dict[str, Any]:
    return {"id": qid, "text": text, "kind": kind}


def _language_label(code: str) -> str:
    return _names(code)[0].capitalize()


def questions_for(rule: dict[str, Any], facts: Facts, *, index: int) -> list[dict[str, Any]]:
    """What to ask so this rule can be judged. Profile questions are shared across saves."""
    kind = rule.get("rule")
    if kind == "age":
        return [_ask("birth_year", "What year were you born?", "year")]
    if kind == "nationality":
        return [_ask("nationality", "Which country are you a citizen of?", "country")]
    if kind == "residence":
        return [_ask("residence_country", "Which country do you live in?", "country")]
    if kind == "student":
        return [
            {
                "id": "student_status",
                "text": "Are you a student right now?",
                "kind": "choice",
                "options": [
                    {"value": "full_time", "label": "Full-time student"},
                    {"value": "part_time", "label": "Part-time student"},
                    {"value": "not_student", "label": "Not a student"},
                ],
            }
        ]
    if kind == "education":
        return [
            {
                "id": "education_level",
                "text": "What level are you studying at, or have finished?",
                "kind": "choice",
                "options": [
                    {"value": "secondary", "label": "Secondary school"},
                    {"value": "undergraduate", "label": "Undergraduate"},
                    {"value": "postgraduate", "label": "Postgraduate"},
                    {"value": "graduate", "label": "Graduated"},
                ],
            }
        ]
    if kind == "language":
        codes = dict.fromkeys(
            x["code"].lower() for x in rule.get("languages_any", []) + rule.get("languages_all", [])
        )
        return [
            {
                "id": f"language:{code}",
                "text": f"How well do you speak {_language_label(code)}?",
                "kind": "choice",
                "options": [
                    {"value": "fluent", "label": "Fluent"},
                    {"value": "working", "label": "Working knowledge"},
                    {"value": "basic", "label": "Basic"},
                    {"value": "none", "label": "Not at all"},
                ],
            }
            for code in codes
            if code not in facts.languages
        ]
    if kind == "company":
        return [_ask("company_registered", "Is your company registered?", "yesno")]
    return [_ask(f"rule:{index}", rule["question"], "yesno")]


@dataclass
class Assessment:
    rules: list[dict[str, Any]]  # each with "result"
    questions: list[dict[str, Any]]  # for required rules still unknown, without repeats


def assess(rules: list[dict[str, Any]], facts: Facts, *, ref_year: int) -> Assessment:
    judged, questions, seen = [], [], set()
    for i, rule in enumerate(rules):
        result = judge(rule, facts, index=i, ref_year=ref_year)
        judged.append({**rule, "result": result})
        if result == "unknown" and rule.get("strength") == "required":
            for q in questions_for(rule, facts, index=i):
                if q["id"] not in seen:
                    seen.add(q["id"])
                    questions.append(q)
    return Assessment(judged, questions)
