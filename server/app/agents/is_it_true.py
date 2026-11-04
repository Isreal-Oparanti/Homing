"""Is it true? Compares a save with its official source. Code decides everything shown.

See docs/03-agents.md#is-it-true and docs/05-verification.md. Eligibility comes in S6, so the
verdict here is `closed` or `couldnt_confirm`, decided by code; the verified findings are
what the person reads.
"""

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import object_session

from app.agents.source_agent import find_source
from app.agents.web_tools import Web
from app.core.config import get_settings
from app.db.models import Check, Find, Profile, Reading, Save, Snapshot, User
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
from app.llm.search import find_site as search_site
from app.llm.search import get_search
from app.schemas.agents import ProposedCheck
from app.verify.dates import parse_deadline
from app.verify.eligibility import Facts, accept_rule, assess
from app.verify.quotes import match_quote
from app.verify.sources import official_candidates
from app.verify.status import is_closed
from app.verify.verdict import decide

log = logging.getLogger(__name__)

SOURCE_CHARS_FOR_MODEL = 40_000
MIN_SOURCE_CHARS = 200  # less than this is a shell page, not the posting
TRIES = 2  # official candidates to try

# Tests swap these for fakes; agents never build clients themselves.
gateway_factory: Any = ModelGateway
fetcher_factory: Any = SafeFetcher
search_factory: Any = get_search


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
    urls = find_urls(words_of(save)) + ([save.url] if save.url else []) + facts.get("links", [])
    return official_candidates(urls, facts.get("organisations", []))[:TRIES]


def _searched_candidates(reading: Reading) -> list[str]:
    """Official-page candidates from a web search, when the save itself has no usable link."""
    search = search_factory()
    if search is None:
        return []
    facts = reading.key_facts or {}
    orgs = facts.get("organisations", [])
    words = [orgs[0]] if orgs and orgs[0].lower() not in reading.title.lower() else []
    query = " ".join([*words, reading.title, "apply" if reading.is_opportunity else ""]).strip()
    try:
        results = search.search(query)
    except Exception:  # a search outage just means we say we couldn't find the page
        return []
    return official_candidates([r.url for r in results], orgs)[:TRIES]


def _agent_source(ctx: JobContext, save: Save, reading: Reading) -> tuple[str, SnapshotIn] | None:
    """Muse Wonder looks for the source of a save the person added, when the save's own links
    don't lead to it: a blog, a post, a forwarded message, no link at all. A direct official
    link takes the fast fixed path; imports always do (hundreds at a time). Any failure falls
    back to the fixed path, never to an error."""
    if save.import_id or not get_settings().check_agent:
        return None
    try:
        return find_source(
            ctx,
            save,
            reading,
            words_of(save),
            gateway=gateway_factory(ctx.db),
            web=Web(search_factory(), fetcher_factory()),
        )
    except DeferredError:
        raise
    except Exception:
        log.exception("source agent failed; the fixed path takes over")
        ctx.db.rollback()
        return None


def _find_official(save: Save, reading: Reading) -> tuple[str, SnapshotIn] | None:
    fetcher = fetcher_factory()
    linked = _candidates(save, reading)
    for url in linked or _searched_candidates(reading):
        if (page := _fetch_source(url, reading.title, fetcher)) is not None:
            return url, page
    return None


MIN_POST_CHARS = 80  # shorter than this, a post has no rules worth reading


def words_of(save: Save) -> str:
    """What the save says: the person's own text, or the words read off their file."""
    if save.kind in ("image", "pdf"):
        db = object_session(save)
        copy = None
        if db is not None:
            copy = db.scalar(
                select(Snapshot.text)
                .where(Snapshot.save_id == save.id, Snapshot.kind.in_(("ocr_text", "pdf_text")))
                .limit(1)
            )
        return "\n\n".join(t for t in (save.text, copy) if t)
    return save.text or ""


def _rules_from_post(ctx: JobContext, save: Save, reading: Reading) -> list[dict[str, Any]]:
    """Who-can-apply rules quoted from the post itself, when there's no official page."""
    text = words_of(save)
    proposed: ProposedCheck = gateway_factory(ctx.db).run(
        "check.compare",
        user_id=save.user_id,
        inputs={
            "save": {"text": text, "what": reading.what, "key_facts": reading.key_facts},
            "source": {"url": None, "text": text},
        },
        save_ids=[save.id],
    )
    return [r for p in proposed.rules if (r := accept_rule(p.model_dump(), text))]


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
        "items": [],
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


def _post_deadline(save: Save | None, reading: Reading, user_tz: str) -> datetime | None:
    """The latest closing date the post itself states, parsed by code. Event dates don't count."""
    if save is None:
        return None
    found = [
        d.at
        for fact in (reading.key_facts or {}).get("dates", [])
        if fact.get("role") == "deadline"
        and (d := parse_deadline(fact.get("text", ""), base=save.saved_at, user_tz=user_tz))
    ]
    return max(found) if found else None


def judge_check(db: Any, check: Check, user_id: str) -> list[dict[str, Any]]:
    """Re-judge a check's rules and verdict by code. Returns the questions still open."""
    now = datetime.now(UTC)
    ref_year = (check.deadline_at or now).year
    found = assess(check.eligibility or [], facts_for(db, user_id, check), ref_year=ref_year)
    check.eligibility = found.rules
    reading = db.get(Reading, check.save_id)
    source_opened = bool(check.official_url) and not check.note
    past = check.deadline_at is not None and check.deadline_at < now
    if check.deadline_at is None and not source_opened and reading is not None:
        # No official page to go by: a closing date the post itself gives that has passed
        # still means it's over. An opened official page always wins over the post.
        save = db.get(Save, check.save_id)
        user = db.get(User, user_id)
        closes = _post_deadline(save, reading, user.tz if user else "Africa/Lagos")
        past = closes is not None and closes < now
    check.verdict = decide(
        closed=any(f.get("kind") == "closed" for f in check.findings or []),
        past_deadline=past,
        source_opened=source_opened,
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
    "needs_your_answer": "it needs your answer",
    "checked": "here's what the page says",
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
    if len(reading.items or []) >= 2:
        _start_items(ctx, save, reading)
        return
    user = ctx.db.get(User, save.user_id)
    user_tz = user.tz if user else "Africa/Lagos"

    try:
        by_agent = False
        prior = ctx.db.scalar(select(Check).where(Check.save_id == save.id))
        # Keep watching: what the check said before, to tell the person exactly what changed.
        before = (
            (prior.deadline_at, prior.verdict, len(prior.eligibility or []))
            if payload.get("recheck") and prior is not None
            else None
        )
        if payload.get("recheck") and prior is not None and prior.official_url:
            # Keep watching saw the official page change: read the same page again.
            again = _fetch_source(prior.official_url, reading.title, fetcher_factory())
            found = (prior.official_url, again) if again is not None else None
        else:
            # The cheapest thing that works first: a direct official link needs no agent.
            found = _find_official(save, reading) if _candidates(save, reading) else None
            if found is None:
                found = _agent_source(ctx, save, reading)
                by_agent = found is not None
                found = found or (
                    None if _candidates(save, reading) else _find_official(save, reading)
                )
        if found is None:
            tried = _candidates(save, reading)
            if tried:
                host = _host(tried[0])
                note = f"We couldn't open the official page ({host}), so it's unconfirmed."
                summary = f"Couldn't open {_host(tried[0])} to check: {reading.title}"
            else:
                note = "We couldn't find the official page, so what the post says is unconfirmed."
                summary = f"Couldn't find the official page for: {reading.title}"
            rules = []
            if reading.is_opportunity and len(words_of(save)) >= MIN_POST_CHARS:
                # No official page: still say who it's for, going by the post's own words.
                rules = _rules_from_post(ctx, save, reading)
                if rules:
                    note += " Who can apply below is going by the post's own words."
                    summary += f". Judged from the post's own words ({len(rules)} rules)"
            check = _save_check(
                ctx,
                save,
                verdict="couldnt_confirm",
                note=note,
                official_found_by="post_only" if rules else None,
                eligibility=rules,
            )
            if rules:
                judge_check(ctx.db, check, save.user_id)
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
                "save": {
                    "text": words_of(save),
                    "what": reading.what,
                    "key_facts": reading.key_facts,
                },
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
        note = (
            f"The page Homing found on {host} is about something else, so it's unconfirmed."
            if by_agent
            else f"The post's link goes to a different page on {host}, so it's unconfirmed."
        )
        rules = []
        if reading.is_opportunity and len(words_of(save)) >= MIN_POST_CHARS:
            # Still say who it's for, going by the post's (or flyer's) own words.
            rules = _rules_from_post(ctx, save, reading)
            if rules:
                note += " Who can apply below is going by the post's own words."
        check = _save_check(
            ctx,
            save,
            verdict="couldnt_confirm",
            official_url=None if rules else official,
            official_found_by="post_only" if rules else "post_link",
            note=note,
            eligibility=rules,
        )
        if rules:
            judge_check(ctx.db, check, save.user_id)
        emit(
            ctx.db,
            user_id=save.user_id,
            agent="true",
            action="couldnt_confirm",
            summary=(
                f"The page found on {host} isn't this opportunity's page."
                if by_agent
                else f"The post's link on {host} isn't this opportunity's page."
            ),
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
        official_found_by="agent"
        if by_agent
        else ("post_link" if url in _candidates(save, reading) else "search"),
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
    action = "checked"
    if before is not None:
        changes = what_changed(before, check, user_tz)
        if changes:
            action = "changed"
            summary = f"The official page for {reading.title} changed: " + "; ".join(changes) + "."
        else:
            action = "rechecked"
            summary = f"Re-read {host}: its words changed, but nothing that matters to you did."
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="true",
        action=action,
        summary=summary,
        save_id=save.id,
        evidence=evidence,
    )
    _then_when(ctx, save)


def what_changed(before: tuple[datetime | None, str, int], check: Check, user_tz: str) -> list[str]:
    """What a re-read changed that matters to the person, in plain words."""
    deadline, verdict, rules = before
    tz = ZoneInfo(user_tz)

    def day(at: datetime) -> str:
        local = at.astimezone(tz)
        return f"{local.day} {local:%b}"

    out = []
    if check.deadline_at != deadline:
        if deadline and check.deadline_at:
            out.append(f"the deadline moved from {day(deadline)} to {day(check.deadline_at)}")
        elif check.deadline_at:
            out.append(f"it now gives a deadline: {day(check.deadline_at)}")
        else:
            out.append("it no longer gives a deadline")
    if check.verdict != verdict and check.verdict == "closed":
        out.append("it's now closed")
    elif check.verdict != verdict:
        out.append(f"now {VERDICT_WORDS.get(check.verdict, check.verdict)}")
    if len(check.eligibility or []) != rules:
        out.append("who can apply changed")
    return out


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


def rejudge_finds(db: Any, user_id: str) -> None:
    """What What's it for? found on the web, judged again by code against what the person
    just told Homing: one that turns out not to be for them leaves the list."""
    facts = facts_for(db, user_id, None)
    now = datetime.now(UTC)
    for find in db.scalars(select(Find).where(Find.user_id == user_id, Find.state == "new")):
        if not find.rules:
            continue  # the page doesn't say who can apply: nothing to judge
        judged = assess(find.rules, facts, ref_year=(find.deadline_at or now).year).rules
        find.rules = judged
        find.verdict = decide(closed=False, past_deadline=False, source_opened=True, rules=judged)


def rejudge_all(db: Any, user_id: str) -> list[tuple[Check, str, str]]:
    """Re-judge every opportunity by code. Returns (check, old verdict, new verdict) changes."""
    checks = db.scalars(
        select(Check).join(Save, Save.id == Check.save_id).where(Save.user_id == user_id)
    ).all()
    changed = []
    for check in checks:
        if check.items:
            items = [dict(i) for i in check.items]
            for item in items:
                before = item.get("verdict")
                judge_item(db, user_id, item)
                if before and item.get("verdict") != before:
                    changed.append((check, before, item["verdict"]))
            check.items = items
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
    rejudge_finds(db, user_id)
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
    rejudge_finds(db, user_id)
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


# Lists: one save, many opportunities ----------------------------------------------------------

MAX_ITEMS = 20


def _start_items(ctx: JobContext, save: Save, reading: Reading) -> None:
    """Fan out: one job per item, so the items are checked side by side."""
    items = [
        {"name": i.get("name"), "url": i.get("url"), "note": i.get("note"), "status": "queued"}
        for i in (reading.items or [])[:MAX_ITEMS]
    ]
    _save_check(ctx, save, verdict="checked", items=items)
    for index in range(len(items)):
        queue.enqueue(
            ctx.db,
            "save.check_item",
            {"save_id": save.id, "index": index},
            user_id=save.user_id,
            priority=queue.PRIORITY_USER,
            dedupe_key=f"checkitem:{save.id}:{index}",
        )
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="true",
        action="checking_list",
        summary=f"Checking the {len(items)} items in this save, one by one.",
        save_id=save.id,
    )
    _then_when(ctx, save)


def judge_item(db: Any, user_id: str, item: dict[str, Any]) -> None:
    """An item's rules and verdict, by code. Items use the profile only (no one-off answers).

    Whether an item is an opportunity is decided by its own page: who-can-apply rules or a
    closing date make it one. A directory or a news page is just checked.
    """
    if item.get("status") != "done" or not item.get("official_url"):
        return
    now = datetime.now(UTC)
    deadline = datetime.fromisoformat(item["deadline_at"]) if item.get("deadline_at") else None
    found = assess(item.get("rules") or [], facts_for(db, user_id, None), ref_year=now.year)
    item["rules"] = found.rules
    item["questions"] = [q for q in found.questions if not q["id"].startswith("rule:")]
    # There's no per-item question, so "Are you building in Africa?"-style rules don't block the
    # verdict; the card lists them under "Check yourself".
    blocking = [
        r for r in found.rules if not (r.get("rule") == "other" and r.get("result") == "unknown")
    ]
    item["verdict"] = decide(
        closed=bool(item.get("closed")),
        past_deadline=deadline is not None and deadline < now,
        source_opened=True,
        rules=blocking,
        is_opportunity=bool(found.rules or item.get("deadline_at")),
    )


def check_item(ctx: JobContext, payload: dict[str, Any]) -> None:
    if ctx.user_id is None:
        raise PermanentError("save.check_item needs a user.")
    save = saves_repo.get_save(ctx.db, ctx.user_id, str(payload.get("save_id")))
    reading = saves_repo.get_reading(ctx.db, save.id) if save else None
    check = ctx.db.get(Check, save.id) if save else None
    index = int(payload.get("index", -1))
    if save is None or reading is None or check is None or not 0 <= index < len(check.items):
        return
    item = dict(check.items[index])
    name = item.get("name") or "This item"
    url = item.get("url")
    user = ctx.db.get(User, save.user_id)
    user_tz = user.tz if user else "Africa/Lagos"
    result: dict[str, Any] = {"status": "done"}

    if not url and (search := search_factory()) is not None:
        try:
            url = search_site(search, name, reading.title)
        except Exception:  # a search outage just means we say we couldn't find it
            url = None
        result["found_by"] = "search" if url else None
    source = _fetch_source(url, name, fetcher_factory()) if url else None
    if not url:
        result.update(verdict="couldnt_confirm", problem="We couldn't find its website.")
    elif source is None:
        result.update(verdict="couldnt_confirm", problem=f"We couldn't open {_host(url)}.")
    else:
        page = Snapshot(
            save_id=save.id,
            kind="official_text",
            source_url=source.source_url or url,
            text=source.text,
            meta={**source.meta, "for": "item", "index": index},
        )
        ctx.db.add(page)
        ctx.db.flush()
        proposed: ProposedCheck = gateway_factory(ctx.db).run(
            "check.compare",
            user_id=save.user_id,
            inputs={
                "save": {"text": f"{name}: {item.get('note') or ''}".strip(": ")},
                "source": {"url": page.source_url, "text": page.text[:SOURCE_CHARS_FOR_MODEL]},
            },
            save_ids=[save.id],
        )
        now = datetime.now(UTC)
        deadline = None
        if proposed.deadline_quote and (m := match_quote(proposed.deadline_quote, page.text)):
            deadline = parse_deadline(page.text[m.start : m.end], base=now, user_tz=user_tz)
        closed = is_closed(page.text)
        result.update(
            official_url=page.source_url,
            snapshot_id=page.id,
            findings=_verify(proposed, page)[:5],
            rules=[r for p in proposed.rules if (r := accept_rule(p.model_dump(), page.text))],
            deadline_at=deadline.at.isoformat() if deadline else None,
            deadline_source_text=deadline.source_text if deadline else None,
            closed=closed.quote if closed else None,
        )
        result = {**item, **result}
        judge_item(ctx.db, save.user_id, result)

    # Several item jobs write to the same check: take the row lock to merge safely.
    locked = ctx.db.scalar(
        select(Check)
        .where(Check.save_id == save.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    items = list(locked.items)
    items[index] = {**items[index], **result}
    locked.items = items
    done = items[index]
    words = VERDICT_WORDS.get(done.get("verdict", ""), "it needs your answer")
    where = f" on {_host(done['official_url'])}" if done.get("official_url") else ""
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="true",
        action="checked_item",
        summary=f"Checked {name}{where}: {words}.",
        save_id=save.id,
        evidence=[{"label": name, "url": url}] if url else [],
    )
