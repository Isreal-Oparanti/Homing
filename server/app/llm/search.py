"""Web search for Is it true?: finding an official page when the save has no link to it.

Results are links only (docs/06-models.md · Web search). Is it true? opens and reads the pages
itself, so a search provider's titles and snippets are never trusted as facts.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.verify.sources import NEVER_OFFICIAL

# Profile and data sites describe an organisation; they're never its own page.
NOT_THE_ORGANISATION = (
    "crunchbase.com",
    "pitchbook.com",
    "cbinsights.com",
    "tracxn.com",
    "wikipedia.org",
    "f6s.com",
    "dealroom.co",
    "angel.co",
    "wellfound.com",
    "glassdoor.com",
    "zoominfo.com",
    "bloomberg.com",
    "techcabal.com",
    "techcrunch.com",
    "medium.com",
)
# Words that say little about which organisation a site belongs to.
GENERIC_WORDS = {
    "capital",
    "ventures",
    "venture",
    "partners",
    "fund",
    "funds",
    "group",
    "africa",
    "african",
    "the",
    "and",
    "for",
    "global",
    "holdings",
    "investments",
    "foundation",
    "international",
    "network",
    "management",
    "company",
    "limited",
    "ltd",
    "inc",
}


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str


class SearchProvider(Protocol):
    def search(self, query: str, *, num: int = 8) -> list[SearchResult]: ...


class SerperSearch:
    """Google results through serper.dev."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, *, num: int = 8) -> list[SearchResult]:
        res = httpx.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": num},
            headers={"X-API-KEY": self.api_key},
            timeout=15,
        )
        res.raise_for_status()
        return [
            SearchResult(r.get("link", ""), r.get("title", ""), r.get("snippet", ""))
            for r in res.json().get("organic", [])
            if r.get("link")
        ]


@lru_cache
def get_search() -> SearchProvider | None:
    settings = get_settings()
    if settings.search_provider == "serper" and settings.search_api_key:
        return SerperSearch(settings.search_api_key)
    return None


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _excluded(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in NEVER_OFFICIAL + NOT_THE_ORGANISATION)


def name_words(name: str) -> list[str]:
    """The words of a name that could identify its website ("Microtraction", "Ingressive")."""
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) >= 3]
    return [w for w in words if w not in GENERIC_WORDS] or words


def own_site(results: list[SearchResult], name: str) -> str | None:
    """The organisation's own site among search results: the first whose address carries its
    name. "Future Africa" → future.africa, "Oui Capital" → ouicapital.com. None if unsure."""
    squashed = re.sub(r"[^a-z0-9]", "", name.lower())
    words = name_words(name)
    for r in results:
        host = _host(r.url)
        if not host or _excluded(host):
            continue
        flat = host.replace("-", "").replace(".", "")
        if squashed and squashed in flat:
            return r.url
        if words and all(w in flat for w in words):
            return r.url
    return None


def _title_names(result: SearchResult, name: str) -> bool:
    title = result.title.lower()
    return bool(name_words(name)) and all(w in title for w in name_words(name))


def find_site(search: SearchProvider, name: str, context: str = "") -> str | None:
    """An organisation's own home page: search its name, then its name with the list's topic.
    Its address must carry the name, or failing that, its page title must."""
    for query in dict.fromkeys(q for q in (name, f"{name} {context}".strip()) if q):
        results = search.search(query)
        url = own_site(results, name)
        if url is None:
            url = next(
                (r.url for r in results if not _excluded(_host(r.url)) and _title_names(r, name)),
                None,
            )
        if url is not None:
            parts = urlsplit(url)
            return f"{parts.scheme}://{parts.netloc}/"
    return None
