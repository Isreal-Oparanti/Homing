"""Application sites whose pages are built by JavaScript, read through their public data instead.

A plain fetch of a Workable job page returns only its one-line description. Workable's public
job JSON has the location, requirements and benefits, and its robots.txt allows AI input
(`Content-Signal: ai-input=yes`). See docs/04-ingestion.md.
"""

import html
import json
import re
from urllib.parse import urlsplit

from app.ingest.fetch import FetchError, SafeFetcher
from app.ingest.gather import SnapshotIn

_WORKABLE_HOST = re.compile(r"(?:^|\.)workable\.com$")
_STOPWORDS = {"the", "and", "for", "of", "a", "an", "to", "in", "programme", "program", "call"}


def is_workable(url: str) -> bool:
    return bool(_WORKABLE_HOST.search(urlsplit(url).hostname or ""))


def workable_parts(url: str) -> tuple[str | None, str | None]:
    """(account, shortcode) from apply.workable.com/{account}/j/{code}, /j/{code} or /{account}."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    segments = [s for s in parts.path.split("/") if s]
    if host.startswith("apply."):
        if segments[:1] == ["j"] and len(segments) > 1:
            return None, segments[1].upper()
        account = segments[0] if segments else None
        if len(segments) > 2 and segments[1] == "j":
            return account, segments[2].upper()
        return account, None
    # Older style: {account}.workable.com/j/{code}
    account = host.split(".")[0] if host.count(".") >= 2 else None
    if len(segments) > 1 and segments[0] == "j":
        return account, segments[1].upper()
    return account, None


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOPWORDS}


def _pick_job(jobs: list[dict], hint: str | None) -> dict | None:
    """The job the save is about: the only one, or the best title match with the hint."""
    if len(jobs) == 1:
        return jobs[0]
    if not hint:
        return None
    want = _words(hint)
    scored = sorted(
        ((len(want & _words(j.get("title", ""))), j) for j in jobs), key=lambda x: -x[0]
    )
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


def _text(markup: str | None) -> str:
    if not markup:
        return ""
    markup = re.sub(r"(?i)<li[^>]*>", "\n• ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</h\d>|</li>|</ul>|</ol>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _json(fetcher: SafeFetcher, url: str) -> dict:
    got = fetcher.get(url, accept="application/json")
    if got.status != 200:
        raise FetchError("unreachable", f"Workable answered {got.status}.")
    return json.loads(got.body)


def read_workable(url: str, fetcher: SafeFetcher, hint: str | None = None) -> SnapshotIn | None:
    """Our copy of a Workable job, or None when we can't tell which job is meant."""
    account, code = workable_parts(url)
    if code and not account:  # /j/{code} redirects to the account's own path
        account, code = workable_parts(fetcher.get(url).url)
    if not account:
        return None
    if not code:
        listing = _json(fetcher, f"https://apply.workable.com/api/v1/widget/accounts/{account}")
        job = _pick_job(listing.get("jobs", []), hint)
        if job is None:
            return None
        code = str(job.get("shortcode", "")).upper()
    job = _json(fetcher, f"https://apply.workable.com/api/v2/accounts/{account}/jobs/{code}")
    loc = job.get("location") or {}
    place = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
    workplace = str(job.get("workplace") or ("remote" if job.get("remote") else "")).replace(
        "_", "-"
    )
    lines = [
        job.get("title", ""),
        f"Location: {place}" if place else "",
        f"Workplace: {workplace}" if workplace else "",
        f"Type: {str(job.get('type', '')).replace('_', '-')}" if job.get("type") else "",
        "",
        _text(job.get("description")),
        "Requirements" if job.get("requirements") else "",
        _text(job.get("requirements")),
        "Benefits" if job.get("benefits") else "",
        _text(job.get("benefits")),
    ]
    text = "\n".join(line for line in lines if line is not None).strip()
    page = f"https://apply.workable.com/{account}/j/{code}/"
    meta = {"title": job.get("title"), "account": account, "shortcode": code, "via": "workable"}
    return SnapshotIn("page_text", re.sub(r"\n{3,}", "\n\n", text), page, meta)
