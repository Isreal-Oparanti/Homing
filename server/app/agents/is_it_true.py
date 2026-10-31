"""Is it true? Compares a save with its official source. Code decides everything shown.

See docs/03-agents.md#is-it-true and docs/05-verification.md. Eligibility comes in S6, so the
verdict here is `closed` or `couldnt_confirm`, decided by code; the verified findings are
what the person reads.
"""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.db.models import Check, Reading, Save, Snapshot, User
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
from app.verify.quotes import match_quote
from app.verify.sources import official_candidates
from app.verify.status import is_closed

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


def _find_official(save: Save, reading: Reading) -> tuple[str, SnapshotIn] | None:
    facts = reading.key_facts or {}
    urls = find_urls(save.text or "") + ([save.url] if save.url else []) + facts.get("links", [])
    fetcher = fetcher_factory()
    for url in official_candidates(urls, facts.get("organisations", []))[:TRIES]:
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
        **values,
        "checked_at": datetime.now(UTC),
    }.items():
        setattr(check, key, value)
    ctx.db.add(check)
    return check


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
            _save_check(
                ctx,
                save,
                verdict="couldnt_confirm",
                note="We couldn't find the official page, so what the post says is unconfirmed.",
            )
            emit(
                ctx.db,
                user_id=save.user_id,
                agent="true",
                action="couldnt_confirm",
                summary=f"Couldn't find the official page for: {reading.title}",
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
    is_past = deadline is not None and deadline.at < now
    _save_check(
        ctx,
        save,
        verdict="closed" if closed or is_past else "couldnt_confirm",
        official_url=official,
        official_found_by="post_link",
        deadline_at=deadline.at if deadline else None,
        deadline_source_text=deadline.source_text if deadline else None,
        deadline_tz_stated=deadline.tz_stated if deadline else False,
        findings=findings,
    )

    gaps = [f for f in findings if f["kind"] in ("left_out", "differs")]
    if closed or is_past:
        summary = f"Checked against {host}: it's closed."
    elif gaps:
        things = "thing" if len(gaps) == 1 else "things"
        summary = f"Checked against {host}: {len(gaps)} {things} the post left out or got wrong."
    else:
        summary = f"Checked against {host}: it matches the post."
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
