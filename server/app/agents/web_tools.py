"""The web, as Muse Wonder's tools: search for links, open pages, follow their links.

Shared by the agents that go out on the web (finds_more; is_it_true's source search). The
model only ever names refs: W1, W2… for search results and L1, L2… for links on pages it
opened. It can't type a URL, so words on a page can only lead it to links that page really
has, and every fetch still goes through SafeFetcher (public addresses, robots.txt). Search
titles and snippets are shown as leads, never trusted as facts: facts come from opened pages.
"""

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import lxml.html

from app.ingest.fetch import FetchError, SafeFetcher
from app.ingest.gather import web_page
from app.llm.search import SearchProvider
from app.verify.sources import NEVER_OFFICIAL

PAGE_CHARS_FOR_MODEL = 4_000
MAX_LINKS = 20
# Context engineering for links: what a page links to, ranked before Wonder sees it, so its
# few page opens go to the organisation's own pages rather than menus and footers.
NAV_TEXT = {
    "home",
    "about",
    "about us",
    "contact",
    "contact us",
    "privacy",
    "privacy policy",
    "terms",
    "terms of use",
    "terms and conditions",
    "cookies",
    "cookie policy",
    "login",
    "log in",
    "sign in",
    "sign up",
    "subscribe",
    "newsletter",
    "search",
    "menu",
    "faq",
    "faqs",
    "blog",
    "news",
    "careers",
    "donate",
    "shop",
    "share",
    "tweet",
    "next",
    "previous",
    "older posts",
    "newer posts",
    "skip to content",
    "back to top",
}
NAV_PATHS = (
    "/tag/",
    "/tags/",
    "/category/",
    "/author/",
    "/page/",
    "/feed",
    "/wp-login",
    "/wp-admin",
    "/login",
    "/signin",
    "/sign-in",
    "/privacy",
    "/terms",
    "/cookie",
    "/search",
    "/comments",
    "/share",
    "/cart",
    "/account",
)
GOOD_WORDS = (
    "apply",
    "application",
    "programme",
    "program",
    "fellowship",
    "grant",
    "accelerator",
    "call-for",
    "call for",
    "challenge",
    "prize",
    "fund",
    "cohort",
    "register",
    "competition",
    "scholarship",
    "award",
    "incubator",
    "eligib",
    "opportunit",
)
TWO_PART_ENDINGS = (
    ".co.uk",
    ".org.uk",
    ".ac.uk",
    ".gov.uk",
    ".com.ng",
    ".org.ng",
    ".gov.ng",
    ".edu.ng",
    ".co.za",
    ".org.za",
    ".co.ke",
    ".or.ke",
    ".com.gh",
    ".org.gh",
    ".com.au",
)
MIN_PAGE_CHARS = 200  # less than this is a shell page, not the posting
SKIP = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".ico", ".zip", ".mp4")

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web (Google). Returns leads: refs (W1, W2, …) with a title, "
        "site and snippet. Snippets are not facts; open a page to read it.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}
OPEN_TOOL = {
    "type": "function",
    "function": {
        "name": "open_page",
        "description": "Open a search result (W3) or a link from a page you opened (L12). "
        "Returns the page's id (P1, P2, …), its main text and its links, best first: links to "
        "other sites (`leaves_site`), then ones about applying; menus and footers are left out.",
        "parameters": {
            "type": "object",
            "properties": {"ref": {"type": "string", "description": "e.g. W3 or L12"}},
            "required": ["ref"],
        },
    },
}


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def site_of(host: str) -> str:
    """The registrable part of a host: apply.example.org and example.org are one site."""
    labels = 3 if host.endswith(TWO_PART_ENDINGS) else 2
    return ".".join(host.split(".")[-labels:])


def rank_links(links: list[tuple[str, str]], page_url: str) -> list[tuple[str, str, bool]]:
    """(text, url, leaves the site): menus, footers, social and login links dropped; links to
    other sites first (a blog links out to the official page), then ones about applying."""
    here = site_of(host_of(page_url))
    scored = []
    for i, (text, url) in enumerate(links):
        host, path = host_of(url), urlsplit(url).path.lower()
        words = f"{text} {path}".lower()
        if text.lower().strip(" ›»→|") in NAV_TEXT or any(p in path for p in NAV_PATHS):
            continue
        if any(host == d or host.endswith("." + d) for d in NEVER_OFFICIAL):
            continue  # social posts and opportunity blogs: never the source, rarely a lead
        leaves = site_of(host) != here
        score = (3 if leaves else 0) + (2 if any(w in words for w in GOOD_WORDS) else 0)
        scored.append((-score, i, text, url, leaves))
    return [(text, url, leaves) for _, _, text, url, leaves in sorted(scored)]


def links_of(html: str, base: str) -> list[tuple[str, str]]:
    """(text, absolute url) for each distinct web link on a page, in page order."""
    try:
        doc = lxml.html.fromstring(html)
    except (ValueError, lxml.etree.ParserError):
        return []
    seen, out = set(), []
    for a in doc.iter("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base, href).split("#", 1)[0]
        if urlsplit(url).scheme not in ("http", "https") or url.lower().endswith(SKIP):
            continue
        if url in seen or url.rstrip("/") == base.rstrip("/"):
            continue
        seen.add(url)
        text = " ".join(a.text_content().split())[:80]
        out.append((text or host_of(url), url))
    return out


@dataclass
class Page:
    ref: str
    url: str
    title: str
    text: str
    query: str | None = None  # the search that led here, through any links followed


@dataclass
class Web:
    """What one agent run has seen on the web, by ref. Budgets keep a run small."""

    search: SearchProvider | None
    fetcher: SafeFetcher
    max_searches: int = 5
    max_pages: int = 9
    leads: dict[str, str] = field(default_factory=dict)  # W#/L# -> url
    pages: dict[str, Page] = field(default_factory=dict)  # P# -> page
    queries: list[str] = field(default_factory=list)
    lead_query: dict[str, str] = field(default_factory=dict)  # W#/L# -> the search behind it
    _links: int = 0

    def add_leads(self, urls: list[str]) -> list[dict[str, Any]]:
        """Links the agent starts from (e.g. the ones in a save), as W refs like search results."""
        out = []
        for url in dict.fromkeys(urls):
            ref = f"W{sum(k.startswith('W') for k in self.leads) + 1}"
            self.leads[ref] = url
            out.append({"ref": ref, "site": host_of(url), "url": url})
        return out

    def run_search(self, query: str) -> dict[str, Any]:
        query = " ".join(str(query).split())[:200]
        if self.search is None:
            return {"error": "Web search isn't available. Work with the pages you have."}
        if len(self.queries) >= self.max_searches:
            return {"error": "No searches left. Open the leads you have, or finish."}
        self.queries.append(query)
        try:
            results = self.search.search(query, num=8)
        except Exception:  # an outage is a fact to report, not a crash
            return {"error": "The search didn't answer. Try once more or use what you have."}
        out = []
        for r in results:
            ref = f"W{sum(k.startswith('W') for k in self.leads) + 1}"
            self.leads[ref] = r.url
            self.lead_query[ref] = query
            out.append({"ref": ref, "title": r.title, "site": host_of(r.url), "snippet": r.snippet})
        return {"query": query, "leads": out}

    def open(self, ref: str) -> dict[str, Any]:
        ref = str(ref).strip().upper()
        url = self.leads.get(ref)
        if url is None:
            return {"error": f"{ref} isn't a lead you were given. Use a W or L ref."}
        for page in self.pages.values():
            if page.url == url:
                return {"page": page.ref, "note": "Already open.", "title": page.title}
        if len(self.pages) >= self.max_pages:
            return {"error": "No page opens left. Propose from what you've read, or finish."}
        try:
            got = self.fetcher.get(url, accept="text/html,application/xhtml+xml,*/*;q=0.8")
        except FetchError as exc:
            return {"error": f"Couldn't open {host_of(url)}: {exc}"}
        gathered = web_page(got)
        copy = next((s for s in gathered.snapshots if s.kind == "page_text"), None)
        if copy is None or len(copy.text) < MIN_PAGE_CHARS:
            why = gathered.notes[0] if gathered.notes else "there's almost no text on it"
            return {"error": f"Couldn't read {host_of(url)}: {why}"}
        page = Page(
            f"P{len(self.pages) + 1}",
            copy.source_url or got.url,
            str(copy.meta.get("title") or host_of(url)),
            copy.text,
            self.lead_query.get(ref),
        )
        self.pages[page.ref] = page
        links = []
        if "html" in got.content_type:
            ranked = rank_links(links_of(got.text(), got.url), page.url)
            for text, link, leaves in ranked[:MAX_LINKS]:
                self._links += 1
                self.leads[f"L{self._links}"] = link
                if page.query:
                    self.lead_query[f"L{self._links}"] = page.query
                links.append(
                    {
                        "ref": f"L{self._links}",
                        "text": text,
                        "site": host_of(link),
                        "leaves_site": leaves,
                    }
                )
        return {
            "page": page.ref,
            "site": host_of(page.url),
            "title": page.title,
            "text": page.text[:PAGE_CHARS_FOR_MODEL],
            "links": links,
        }


KEEP_FULL_PAGES = 3  # the latest pages Wonder opened stay whole in its context
TRIMMED_CHARS = 300


def trim_context(messages: list[dict[str, Any]]) -> None:
    """Context engineering: older page texts shrink to their opening lines, so each turn
    re-sends what the agent needs (its leads, links and latest pages), not everything it read.
    Code always checks against the full page, which it keeps."""
    pages = [
        m
        for m in messages
        if m.get("role") == "tool"
        and '"text":' in m.get("content", "")
        and '"page":' in m["content"]
    ]
    for m in pages[:-KEEP_FULL_PAGES]:
        try:
            result = json.loads(m["content"])
        except ValueError:
            continue
        text = result.get("text")
        if isinstance(text, str) and len(text) > TRIMMED_CHARS:
            result["text"] = text[:TRIMMED_CHARS] + " … (read earlier; reopen it to read again)"
            m["content"] = json.dumps(result)
