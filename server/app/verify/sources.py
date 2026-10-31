"""Which link in a post is the official source (docs/05 · Finding the official source).

Pure code: application hosts first, then the organisation's own site. Social posts, chat
invites and opportunity blogs are never official; they can only lead to the official page.
"""

import re
from urllib.parse import urlsplit

APPLICATION_HOSTS = (
    "workable.com",
    "greenhouse.io",
    "lever.co",
    "typeform.com",
    "forms.gle",
    "docs.google.com",
    "fluxx.io",
    "submittable.com",
    "smapply.io",
    "airtable.com",
)
NEVER_OFFICIAL = (
    "whatsapp.com",
    "wa.me",
    "chat.whatsapp.com",
    "t.me",
    "x.com",
    "twitter.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "linkedin.com",
    "linktr.ee",
    "bit.ly",
    "opportunitiesforafricans.com",
    "opportunitydesk.org",
    "opportunitiescorners.com",
)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _org_words(organisations: list[str]) -> set[str]:
    return {w for org in organisations for w in re.findall(r"[a-z]{4,}", org.lower())}


def official_candidates(urls: list[str], organisations: list[str]) -> list[str]:
    """Links that could be the official source, best first. Empty when none could be."""
    words = _org_words(organisations)
    ranked: list[tuple[int, int, str]] = []
    for i, url in enumerate(dict.fromkeys(urls)):
        host = _host(url)
        # A LinkedIn job page is the posting itself; LinkedIn posts and profiles are not.
        is_job_page = host.endswith("linkedin.com") and "/jobs/" in urlsplit(url).path
        if not host or (_matches(host, NEVER_OFFICIAL) and not is_job_page):
            continue
        names_org = any(w in host or w in urlsplit(url).path.lower() for w in words)
        if _matches(host, APPLICATION_HOSTS):
            rank = 0 if names_org else 1
        else:
            rank = 2 if names_org else 3
        ranked.append((rank, i, url))
    return [url for _, _, url in sorted(ranked)]
