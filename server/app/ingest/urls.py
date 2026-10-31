"""Finding and normalising links. Pure code. See docs/04-ingestion.md#canonical-urls."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|igsh|igshid|si|s|ref_src|ref_url|mibextid|feature)$")
_YT_ID = re.compile(r"(?:youtu\.be/|/shorts/|/live/|/embed/|[?&]v=)([A-Za-z0-9_-]{11})")
_X_STATUS = re.compile(r"/status(?:es)?/(\d+)")


def find_urls(text: str) -> list[str]:
    return [u.rstrip(".,;:!?") for u in _URL.findall(text or "")]


def _host(url: str) -> str:
    host = urlsplit(url).hostname or ""
    for prefix in ("www.", "m.", "mobile.", "web."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host.lower()


def platform_of(url: str) -> str:
    host = _host(url)
    if host in ("youtube.com", "youtu.be", "music.youtube.com"):
        return "youtube"
    if host in ("x.com", "twitter.com"):
        return "x"
    if host in ("instagram.com", "instagr.am"):
        return "instagram"
    if host in ("facebook.com", "fb.watch", "fb.com"):
        return "facebook"
    if host.endswith("tiktok.com"):
        return "tiktok"
    return "web"


def youtube_id(url: str) -> str | None:
    m = _YT_ID.search(url)
    return m.group(1) if m else None


def x_status_id(url: str) -> str | None:
    m = _X_STATUS.search(url)
    return m.group(1) if m else None


def canonical_url(url: str) -> str:
    """One spelling per resource, so the same thing saved twice has the same hash."""
    platform = platform_of(url)
    if platform == "youtube" and (vid := youtube_id(url)):
        return f"https://www.youtube.com/watch?v={vid}"
    if platform == "x" and (sid := x_status_id(url)):
        return f"https://x.com/i/status/{sid}"
    parts = urlsplit(url.strip())
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            "https" if parts.scheme in ("http", "https") else parts.scheme,
            _host(url),
            path,
            urlencode(query),
            "",
        )
    )


def is_youtube_short(url: str) -> bool:
    return "/shorts/" in url
