"""Connectors: get readable content for a save, one function per platform (docs/04-ingestion.md).

Each returns `Gathered`: snapshots to store (our copy of the content) and plain-language notes
for anything we couldn't read. Official endpoints (oEmbed, YouTube Data API) are APIs meant for
programs, so they skip robots.txt; ordinary pages respect it.
"""

import html as html_lib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import trafilatura

from app.core.config import Settings
from app.ingest.fetch import FetchError, SafeFetcher
from app.ingest.urls import is_youtube_short, platform_of, x_status_id, youtube_id

MAX_SNAPSHOT_CHARS = 200_000
MAX_TRANSCRIPT_CHARS = 60_000


@dataclass
class SnapshotIn:
    kind: str  # page_text · post_text · transcript · metadata
    text: str
    source_url: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Gathered:
    snapshots: list[SnapshotIn] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _json(fetcher: SafeFetcher, url: str) -> dict[str, Any]:
    got = fetcher.get(url, respect_robots=False, accept="application/json")
    if got.status != 200:
        raise FetchError("unreachable", f"The service answered with an error ({got.status}).")
    return json.loads(got.body)


def _strip_tags(markup: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()


THIN_PAGE_CHARS = 500
# Pages built in the browser (Next.js and the like) send their words inside script data.
_NEXT_PUSH = re.compile(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\]\)', re.S)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_TEXT_FIELD = re.compile(r'"(?:text|description)":"((?:[^"\\]|\\.)*)"')
_NOT_WORDS = re.compile(r"\$[\w@:]*|https?://\S+")  # React references ("$L1") and bare links


def _app_text(page: str) -> str:
    """The words in a page's script data: rich-text and description fields, in order, once."""
    data = [json.loads(m.group(1)) for m in _NEXT_PUSH.finditer(page)]
    data += _NEXT_DATA.findall(page)
    seen: dict[str, None] = {}
    for chunk in data:
        for m in _TEXT_FIELD.finditer(chunk):
            try:
                value = " ".join(json.loads(f'"{m.group(1)}"').split())
            except ValueError:
                continue
            if re.search(r"[^\W\d_]{2}", value) and not _NOT_WORDS.fullmatch(value):
                seen.setdefault(value, None)
    # A field that repeats part of a longer one (a paragraph of the full description) goes.
    kept: list[str] = []
    for value in sorted(seen, key=len, reverse=True)[:2000]:
        if not any(value in longer for longer in kept):
            kept.append(value)
    return "\n".join(v for v in seen if v in set(kept))


def gather_web(url: str, fetcher: SafeFetcher) -> Gathered:
    got = fetcher.get(url, accept="text/html,application/xhtml+xml,*/*;q=0.8")
    if got.status >= 400:
        return Gathered(notes=[f"Couldn't open this link (the site answered {got.status})."])
    if "pdf" in got.content_type:
        return Gathered(notes=["This link is a PDF. PDFs are read in a later step."])
    page = got.text()
    text = trafilatura.extract(page, url=got.url, include_tables=True, include_comments=False) or ""
    meta = trafilatura.extract_metadata(page)
    title = (meta.title if meta else None) or _title_tag(page)
    info = {
        "title": title,
        "site": meta.sitename if meta else None,
        "description": meta.description if meta else None,
        "date": meta.date if meta else None,
    }
    if len(text) < THIN_PAGE_CHARS:
        inside = _app_text(page)
        if len(inside) > len(text):
            text = inside
    if not text and info["description"]:
        text = info["description"]
    return Gathered(snapshots=[SnapshotIn("page_text", text[:MAX_SNAPSHOT_CHARS], got.url, info)])


def _title_tag(page: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    return _strip_tags(m.group(1))[:200] if m else None


_CHAPTER = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+[-–—]?\s*(.+)$")
_ISO_DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_chapters(description: str) -> list[dict[str, Any]]:
    chapters = []
    for line in description.splitlines():
        m = _CHAPTER.match(line)
        if m:
            h, mnt, s, title = m.groups()
            chapters.append(
                {"t": int(h or 0) * 3600 + int(mnt) * 60 + int(s), "title": title.strip()}
            )
    return chapters if len(chapters) >= 2 and chapters[0]["t"] == 0 else []


def parse_iso_duration(value: str) -> int | None:
    m = _ISO_DURATION.fullmatch(value or "")
    if not m:
        return None
    h, mnt, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mnt * 60 + s


CAPTION_TRIES = 3


class CaptionsUnavailable(Exception):
    """`blocked` is True when YouTube refused the request, rather than having no captions."""

    def __init__(self, blocked: bool):
        super().__init__("blocked" if blocked else "none")
        self.blocked = blocked


def _captions(video_id: str, *, proxy_url: str = "", pause_s: float = 1.5) -> list[dict[str, Any]]:
    """YouTube caption text with timestamps (Isreal's decision, 31 Oct: captions only, no
    downloading; behind FEATURE_YT_CAPTIONS). YouTube refuses some requests at random, so
    blocked requests are retried a few times with short pauses. YouTube blocks cloud
    servers outright, so production sends these requests through `proxy_url`; a new client
    per try means a rotating proxy gives each try a new address."""
    from requests.exceptions import ProxyError
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import IpBlocked, RequestBlocked
    from youtube_transcript_api.proxies import GenericProxyConfig

    proxy = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url) if proxy_url else None
    for attempt in range(CAPTION_TRIES):
        try:
            fetched = YouTubeTranscriptApi(proxy_config=proxy).fetch(
                video_id, languages=["en", "en-US", "en-GB"]
            )
            return [{"t": round(s.start, 1), "text": s.text} for s in fetched]
        # A proxy that fails is as good as blocked: the video may well have captions.
        except (RequestBlocked, IpBlocked, ProxyError) as exc:
            if attempt == CAPTION_TRIES - 1:
                raise CaptionsUnavailable(blocked=True) from exc
            time.sleep(pause_s * (attempt + 1))
        except Exception as exc:  # no captions, disabled, private or age-restricted
            raise CaptionsUnavailable(blocked=False) from exc
    raise CaptionsUnavailable(blocked=True)


def gather_youtube(url: str, fetcher: SafeFetcher, settings: Settings) -> Gathered:
    vid = youtube_id(url)
    if not vid:
        return gather_web(url, fetcher)
    out = Gathered()
    watch = f"https://www.youtube.com/watch?v={vid}"
    meta: dict[str, Any] = {"video_id": vid, "short": is_youtube_short(url)}
    try:
        o = _json(fetcher, f"https://www.youtube.com/oembed?format=json&url={watch}")
        meta.update(title=o.get("title"), channel=o.get("author_name"))
    except (FetchError, ValueError):
        out.notes.append("Couldn't get this video's title.")
    if settings.youtube_api_key:
        try:
            data = _json(
                fetcher,
                "https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails"
                f"&id={vid}&key={settings.youtube_api_key}",
            )
            if items := data.get("items"):
                snippet, details = items[0]["snippet"], items[0]["contentDetails"]
                meta.update(
                    title=snippet.get("title") or meta.get("title"),
                    channel=snippet.get("channelTitle") or meta.get("channel"),
                    description=snippet.get("description", ""),
                    published_at=snippet.get("publishedAt"),
                    duration_s=parse_iso_duration(details.get("duration", "")),
                    chapters=parse_chapters(snippet.get("description", "")),
                )
        except (FetchError, ValueError, KeyError):
            out.notes.append("Couldn't get this video's description.")
    summary = "\n".join(
        str(x) for x in (meta.get("title"), meta.get("channel"), meta.get("description")) if x
    )
    out.snapshots.append(SnapshotIn("metadata", summary, watch, meta))
    if settings.feature_yt_captions:
        try:
            segments = _captions(vid, proxy_url=settings.captions_proxy_url)
            lines, size = [], 0
            for seg in segments:
                line = f"[{int(seg['t']) // 60}:{int(seg['t']) % 60:02d}] {seg['text']}"
                size += len(line) + 1
                if size > MAX_TRANSCRIPT_CHARS:
                    break
                lines.append(line)
            out.snapshots.append(
                SnapshotIn(
                    "transcript",
                    "\n".join(lines),
                    watch,
                    {"segments": segments, "source": "captions"},
                )
            )
        except CaptionsUnavailable as exc:
            out.notes.append(
                "YouTube didn't share this video's captions this time."
                if exc.blocked
                else "This video has no captions we can read."
            )
    return out


def gather_x(url: str, fetcher: SafeFetcher) -> Gathered:
    sid = x_status_id(url)
    if not sid:
        return Gathered(notes=["This X link isn't a single post."])
    try:
        o = _json(
            fetcher,
            f"https://publish.twitter.com/oembed?omit_script=1&url=https://twitter.com/i/status/{sid}",
        )
    except (FetchError, ValueError):
        return Gathered(notes=["Couldn't read this post. It may be deleted or private."])
    text = _strip_tags(o.get("html", ""))
    meta = {
        "author": o.get("author_name"),
        "author_url": o.get("author_url"),
        "first_post_only": True,
    }
    return Gathered(
        snapshots=[SnapshotIn("post_text", text, f"https://x.com/i/status/{sid}", meta)],
        notes=["If this post starts a thread, only this first post can be read."],
    )


def gather_tiktok(url: str, fetcher: SafeFetcher) -> Gathered:
    try:
        o = _json(fetcher, f"https://www.tiktok.com/oembed?url={url}")
    except (FetchError, ValueError):
        return Gathered(notes=["Couldn't read this TikTok."])
    caption = o.get("title") or ""
    return Gathered(
        snapshots=[SnapshotIn("post_text", caption, url, {"author": o.get("author_name")})]
    )


def gather_meta_embed(platform: str) -> Gathered:
    name = "Instagram" if platform == "instagram" else "Facebook"
    return Gathered(
        notes=[f"{name} post. We can't see inside it. Add the video or a screenshot if it matters."]
    )


def gather_link(url: str, fetcher: SafeFetcher, settings: Settings) -> Gathered:
    platform = platform_of(url)
    try:
        if platform == "youtube":
            return gather_youtube(url, fetcher, settings)
        if platform == "x":
            return gather_x(url, fetcher)
        if platform == "tiktok":
            return gather_tiktok(url, fetcher)
        if platform in ("instagram", "facebook"):
            return gather_meta_embed(platform)
        from app.ingest.ats import is_workable, read_workable  # ats builds on this module

        if is_workable(url):
            try:
                job = read_workable(url, fetcher)
            except (FetchError, ValueError, KeyError):
                job = None  # fall back to the plain page
            if job is not None:
                return Gathered(snapshots=[job])
        return gather_web(url, fetcher)
    except FetchError as exc:
        return Gathered(notes=[str(exc)])
