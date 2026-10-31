"""Is it true? Compares a save with its official source. Code decides everything shown.

See docs/03-agents.md#is-it-true and docs/05-verification.md. Eligibility comes in S6, so the
verdict here is `closed` or `couldnt_confirm`, decided by code; the verified findings are
what the person reads.
"""

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Check, Profile, Reading, Save, Snapshot, User
from app.db.repo import saves as saves_repo
from app.events.emitter import emit
from app.ingest.ats import is_workable, read_workable
from app.ingest.fetch import FetchError, SafeFetcher
from app.ingest.gather import SnapshotIn, gather_web
from app.ingest.urls import find_urls
from app.jobs import queue
from app.jobs.errors import DeferredError, PermanentError
from app.jobs.runner import JobContext
from app.llm.gateway import PURPOSES, ModelGateway
from app.schemas.agents import ProposedCheck
from app.verify.dates import parse_deadline
from app.verify.eligibility import Facts, accept_rule, assess
from app.verify.quotes import match_quote
from app.verify.sources import official_candidates
from app.verify.status import is_closed
from app.verify.verdict import decide

SOURCE_CHARS_FOR_MODEL = 40_000
MIN_SOURCE_CHARS = 200  # less than this is a shell page, not the posting
TRIES = 2  # official candidates to try

# Tests swap these for fakes; agents never build clients themselves.
gateway_factory: Any = ModelGateway
fetcher_factory: Any = SafeFetcher


def _fetch_source(url: str, hint: str, fetcher: SafeFetcher) -> SnapshotIn | None:
    if is_workable(url):
        try:
            if (job := read_workable(url, fetcher, hint)) is not None:
                return job
        except (FetchError, ValueError, KeyError):
            pass
    try:
        gathered = gather_web(url, fetcher)
    except FetchError:
        return None
    page = next((s for s in gathered.snapshots if s.kind == "page_text"), None)
    return page if page is not None and len(page.text) >= MIN_SOURCE_CHARS else None


def _candidates(save: Save, reading: Reading) -> list[str]:
    facts = reading.key_facts or {}
    urls = find_urls(save.text or "") + ([save.url] if save.url else []) + facts.get("links", [])
    return official_candidates(urls, facts.get("organisations", []))[:TRIES]


def _find_official(save: Save, reading: Reading) -> tuple[str, SnapshotIn] | None:
    fetcher = fetcher_factory()
    for url in _candidates(save, reading):
        if (page := _fetch_source(url, reading.title, fetcher)) is not None:
            return url, page
    return None


def _host(url: str) -> str:
    return (urlsplit(url).hostname or url).removeprefix("www.")


def _verify(proposed: ProposedCheck, page: Snapshot) -> list[dict[str, Any]]:
    """Keep only findings whose quote code finds in our copy of the page."""
    out = []
    for f in proposed.findings:
        m = match_quote(f.quote, page.text)
        if m is None:
            continue
        out.append(
            {
                "point": f.point,
                "quote": page.text[m.start : m.end],
                "kind": f.kind,
                "verified": True,
                "match": {"score": m.score, "start": m.start, "end": m.end},
                "source_snapshot_id": page.id,
            }
        )
    return out


def _save_check(ctx: JobContext, save: Save, **values: Any) -> Check:
    check = ctx.db.get(Check, save.id) or Check(save_id=save.id)
    for key, value in {
        "official_url": None,
        "official_found_by": None,
        "deadline_at": None,
        "deadline_source_text": None,
        "deadline_tz_stated": False,
        "findings": [],
        "eligibility": [],
        "note": None,
        "model": get_settings().meta_spark_model,
        "prompt_version": PURPOSES["check.compare"].prompt.removesuffix(".md"),
        "answers": {},
        **values,
        "checked_at": datetime.now(UTC),
    }.items():
        setattr(check, key, value)
    ctx.db.add(check)
    return check


def facts_for(db: Any, user_id: str, check: Check | None) -> Facts:
    """What the person has told Homing, plus their answers for this one opportunity."""
    profile = db.get(Profile, user_id)
    answers = dict(check.answers) if check is not None and check.answers else {}
    if profile is None:
        return Facts(answers=answers)
    return Facts(
        birth_year=profile.birth_year,
        nationality=list(profile.nationality or []),
        residence_country=profile.residence_country,
        student_status=profile.student_status,
        education_level=profile.education_level,
        languages=dict(profile.languages or {}),
        company_registered=profile.company_registered,
        answers=answers,
    )


def judge_check(db: Any, check: Check, user_id: str) -> list[dict[str, Any]]:
    """Re-judge a check's rules and verdict by code. Returns the questions still open."""
    now = datetime.now(UTC)
    ref_year = (check.deadline_at or now).year
    found = assess(check.eligibility or [], facts_for(db, user_id, check), ref_year=ref_year)
    check.eligibility = found.rules
    reading = db.get(Reading, check.save_id)
    check.verdict = decide(
        closed=any(f.get("kind") == "closed" for f in check.findings or []),
        past_deadline=check.deadline_at is not None and check.deadline_at < now,
        source_opened=bool(check.official_url) and not check.note,
        rules=found.rules,
        is_opportunity=reading.is_opportunity if reading else True,
    )
    check.question_for_user = found.questions[0]["text"] if found.questions else None
    return found.questions


VERDICT_WORDS = {
    "fits_you": "it fits you",
    "not_for_you": "it's not for you",
    "closed": "it's closed",
    "couldnt_confirm": "couldn't confirm it",
}


COUNT_WORDS = {
    "fits_you": ("fits you", "fit you"),
    "not_for_you": ("isn't for you", "aren't for you"),
    "needs_your_answer": ("still needs an answer", "still need answers"),
    "closed": ("is closed", "are closed"),
    "couldnt_confirm": ("couldn't be confirmed", "couldn't be confirmed"),
}


def _then_when(ctx: JobContext, save: Save) -> None:
    queue.enqueue(
        ctx.db,
        "save.when",
        {"save_id": save.id},
        user_id=save.user_id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"when:{save.id}",
    )


def check(ctx: JobContext, payload: dict[str, Any]) -> None:
    if ctx.user_id is None:
        raise PermanentError("save.check needs a user.")
    save = saves_repo.get_save(ctx.db, ctx.user_id, str(payload.get("save_id")))
    if save is None:
        raise PermanentError("That save no longer exists.")
    reading = saves_repo.get_reading(ctx.db, save.id)
    if save.visibility == "private" or reading is None:
        return
    user = ctx.db.get(User, save.user_id)
    user_tz = user.tz if user else "Africa/Lagos"

    try:
        found = _find_official(save, reading)
        if found is None:
            tried = _candidates(save, reading)
            if tried:
                host = _host(tried[0])
                note = f"We couldn't open the official page ({host}), so it's unconfirmed."
                summary = f"Couldn't open {_host(tried[0])} to check: {reading.title}"
            else:
                note = "We couldn't find the official page, so what the post says is unconfirmed."
                summary = f"Couldn't find the official page for: {reading.title}"
            _save_check(ctx, save, verdict="couldnt_confirm", note=note)
            emit(
                ctx.db,
                user_id=save.user_id,
                agent="true",
                action="couldnt_confirm",
                summary=summary,
                save_id=save.id,
            )
            _then_when(ctx, save)
            return

        url, source = found
        page = Snapshot(
            save_id=save.id,
            kind="official_text",
            source_url=source.source_url or url,
            text=source.text,
            meta={**source.meta, "for": "check"},
        )
        ctx.db.add(page)
        ctx.db.flush()
        proposed: ProposedCheck = gateway_factory(ctx.db).run(
            "check.compare",
            user_id=save.user_id,
            inputs={
                "save": {"text": save.text, "what": reading.what, "key_facts": reading.key_facts},
                "source": {"url": page.source_url, "text": page.text[:SOURCE_CHARS_FOR_MODEL]},
            },
            save_ids=[save.id],
        )
    except DeferredError:
        raise  # the runner tries again tomorrow; the card keeps waiting
    except Exception as exc:
        if isinstance(exc, PermanentError) or ctx.attempt >= ctx.max_attempts:
            ctx.db.rollback()
            _save_check(
                ctx, save, verdict="couldnt_confirm", note="We couldn't check this one this time."
            )
            _then_when(ctx, save)
            ctx.db.commit()
        raise

    official = page.source_url or url
    host = _host(official)
    if not proposed.is_same_opportunity:
        _save_check(
            ctx,
            save,
            verdict="couldnt_confirm",
            official_url=official,
            official_found_by="post_link",
            note=f"The post's link goes to a different page on {host}, so it's unconfirmed.",
        )
        emit(
            ctx.db,
            user_id=save.user_id,
            agent="true",
            action="couldnt_confirm",
            summary=f"The post's link on {host} isn't this opportunity's page.",
            save_id=save.id,
            evidence=[{"label": "Our copy of the page", "snapshot_id": page.id}],
        )
        _then_when(ctx, save)
        return

    findings = _verify(proposed, page)
    now = datetime.now(UTC)
    deadline = None
    if proposed.deadline_quote and (m := match_quote(proposed.deadline_quote, page.text)):
        deadline = parse_deadline(page.text[m.start : m.end], base=now, user_tz=user_tz)
    closed = is_closed(page.text)
    if closed:
        findings.insert(
            0,
            {
                "point": "The official page says it's closed.",
                "quote": closed.quote,
                "kind": "closed",
                "verified": True,
                "source_snapshot_id": page.id,
            },
        )
    rules = [r for p in proposed.rules if (r := accept_rule(p.model_dump(), page.text))]
    check = _save_check(
        ctx,
        save,
        verdict="couldnt_confirm",
        official_url=official,
        official_found_by="post_link",
        deadline_at=deadline.at if deadline else None,
        deadline_source_text=deadline.source_text if deadline else None,
        deadline_tz_stated=deadline.tz_stated if deadline else False,
        findings=findings,
        eligibility=rules,
    )
    questions = judge_check(ctx.db, check, save.user_id)

    gaps = [f for f in findings if f["kind"] in ("left_out", "differs")]
    things = "thing" if len(gaps) == 1 else "things"
    summary = f"Checked against {host}: " + (
        f"{len(gaps)} {things} the post left out or got wrong" if gaps else "it matches the post"
    )
    if check.verdict == "needs_your_answer":
        asks = "question" if len(questions) == 1 else "questions"
        summary += f". {len(questions)} {asks} to see if it fits you."
    else:
        summary += f". {VERDICT_WORDS.get(check.verdict, '').capitalize()}."
    evidence: list[dict[str, Any]] = [
        {"label": "Our copy of the official page", "snapshot_id": page.id},
        {"label": host, "url": official},
    ]
    evidence += [
        {"label": f["point"], "url": official, "quote": f["quote"]} for f in (gaps or findings)[:3]
    ]
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="true",
        action="checked",
        summary=summary,
        save_id=save.id,
        evidence=evidence,
    )
    _then_when(ctx, save)


# Answers ------------------------------------------------------------------------------------


class BadAnswer(ValueError):
    """The answer doesn't fit the question; the message is shown to the person."""


def _set_profile(profile: Profile, qid: str, value: Any) -> None:
    from app.verify.eligibility import EDUCATION, LEVELS, STUDENT

    if qid == "birth_year":
        year = int(value)
        if not 1900 <= year <= datetime.now(UTC).year:
            raise BadAnswer("That year doesn't look right.")
        profile.birth_year = year
    elif qid in ("nationality", "residence_country"):
        code = str(value).strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise BadAnswer("Pick a country from the list.")
        if qid == "nationality":
            profile.nationality = [code]
        else:
            profile.residence_country = code
    elif qid == "student_status":
        if value not in STUDENT:
            raise BadAnswer("Pick one of the options.")
        profile.student_status = value
    elif qid == "education_level":
        if value not in EDUCATION:
            raise BadAnswer("Pick one of the options.")
        profile.education_level = value
    elif qid.startswith("language:"):
        if value not in LEVELS:
            raise BadAnswer("Pick one of the options.")
        profile.languages = {**(profile.languages or {}), qid.split(":", 1)[1]: value}
    elif qid == "company_registered":
        profile.company_registered = bool(value)
    else:
        raise BadAnswer("We don't know that question.")


def rejudge_all(db: Any, user_id: str) -> list[tuple[Check, str, str]]:
    """Re-judge every opportunity by code. Returns (check, old verdict, new verdict) changes."""
    checks = db.scalars(
        select(Check).join(Save, Save.id == Check.save_id).where(Save.user_id == user_id)
    ).all()
    changed = []
    for check in checks:
        if not check.eligibility:
            continue
        before = check.verdict
        judge_check(db, check, user_id)
        if check.verdict != before:
            changed.append((check, before, check.verdict))
    return changed


def _title(db: Any, save_id: str) -> str:
    reading = db.get(Reading, save_id)
    return reading.title if reading else "A saved opportunity"


def answer(db: Any, user_id: str, save_id: str, qid: str, value: Any) -> str:
    """Store one answer, re-judge everything it touches, and say what changed."""
    if qid.startswith("rule:"):
        check = db.get(Check, save_id)
        if check is None:
            raise BadAnswer("This save hasn't been checked.")
        check.answers = {**(check.answers or {}), qid: bool(value)}
    else:
        profile = db.get(Profile, user_id)
        if profile is None:
            profile = Profile(user_id=user_id, nationality=[], languages={})
            db.add(profile)
        _set_profile(profile, qid, value)
    db.flush()
    changed = rejudge_all(db, user_id)
    counts = Counter(new for _, _, new in changed)
    if not changed:
        return "Saved your answer."
    parts = [f"{n} {COUNT_WORDS[v][0 if n == 1 else 1]}" for v, n in counts.items()]
    things = "opportunity" if len(changed) == 1 else "opportunities"
    summary = f"Used your answer on {len(changed)} saved {things}: " + ", ".join(parts) + "."
    emit(
        db,
        user_id=user_id,
        agent="true",
        action="rechecked",
        summary=summary,
        save_id=save_id,
        evidence=[
            {"label": _title(db, check.save_id), "url": f"/saves/{check.save_id}"}
            for check, _, _ in changed[:3]
        ],
    )
    return summary


FORGET = {
    "birth_year": ("birth_year", None),
    "nationality": ("nationality", []),
    "residence_country": ("residence_country", None),
    "student_status": ("student_status", None),
    "education_level": ("education_level", None),
    "company_registered": ("company_registered", None),
}


def update_profile(db: Any, user_id: str, qid: str, value: Any) -> None:
    """Change one remembered answer, or forget it (value None), then re-judge everything."""
    profile = db.get(Profile, user_id)
    if profile is None:
        profile = Profile(user_id=user_id, nationality=[], languages={})
        db.add(profile)
    if value is None:
        if qid.startswith("language:"):
            languages = dict(profile.languages or {})
            languages.pop(qid.split(":", 1)[1], None)
            profile.languages = languages
        elif qid in FORGET:
            setattr(profile, *FORGET[qid])
        else:
            raise BadAnswer("We don't know that question.")
    else:
        _set_profile(profile, qid, value)
    db.flush()
    changed = rejudge_all(db, user_id)
    if changed:
        things = "opportunity" if len(changed) == 1 else "opportunities"
        emit(
            db,
            user_id=user_id,
            agent="true",
            action="rechecked",
            summary=f"Re-judged {len(changed)} saved {things} after you changed your details.",
        )
