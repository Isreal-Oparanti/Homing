from typing import Any

import httpx
import pytest

from app.ingest import gather
from app.ingest.fetch import FetchError, SafeFetcher, is_public_ip
from app.ingest.gather import CaptionsUnavailable, parse_chapters, parse_iso_duration
from app.ingest.urls import canonical_url, find_urls, platform_of, youtube_id
from app.llm.gateway import inline_schema, render_blocks
from app.schemas.agents import Reading


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtu.be/TbB7hSBVKDM?si=abc", "https://www.youtube.com/watch?v=TbB7hSBVKDM"),
        (
            "https://youtube.com/shorts/5azEvwamu2Y?feature=share",
            "https://www.youtube.com/watch?v=5azEvwamu2Y",
        ),
        (
            "https://m.youtube.com/watch?v=TbB7hSBVKDM&t=30",
            "https://www.youtube.com/watch?v=TbB7hSBVKDM",
        ),
        (
            "https://twitter.com/richtosho/status/2114671452637052976?s=46",
            "https://x.com/i/status/2114671452637052976",
        ),
        ("https://www.Example.com/apply/?utm_source=x&id=7#top", "https://example.com/apply?id=7"),
    ],
)
def test_canonical_urls(url: str, expected: str) -> None:
    assert canonical_url(url) == expected


def test_platforms_and_ids() -> None:
    assert platform_of("https://www.instagram.com/reel/De9yxpuIG6X") == "instagram"
    assert platform_of("https://fb.watch/abc") == "facebook"
    assert platform_of("https://apply.workable.com/afreximbank/") == "web"
    assert youtube_id("https://youtube.com/shorts/5azEvwamu2Y") == "5azEvwamu2Y"
    assert find_urls("see https://a.com/x, and https://b.org.") == [
        "https://a.com/x",
        "https://b.org",
    ]


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "::ffff:10.0.0.1",
    ],
)
def test_private_addresses_are_not_public(ip: str) -> None:
    assert not is_public_ip(ip)


def _fetcher(routes: dict[str, httpx.Response], dns: dict[str, str]) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return SafeFetcher(resolver=lambda host: [dns[host]], transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://internal.example/",
        "ftp://example.com/file",
        "https://example.com:8443/",
    ],
)
def test_fetcher_refuses_private_or_odd_urls(url: str) -> None:
    fetcher = _fetcher({}, {"internal.example": "10.1.2.3", "example.com": "93.184.216.34"})
    with pytest.raises(FetchError) as err:
        fetcher.get(url, respect_robots=False)
    assert err.value.code == "not_allowed"


def test_fetcher_rechecks_every_redirect() -> None:
    routes = {
        "https://public.example/": httpx.Response(
            302, headers={"location": "http://internal.example/"}
        )
    }
    fetcher = _fetcher(routes, {"public.example": "93.184.216.34", "internal.example": "10.1.2.3"})
    with pytest.raises(FetchError) as err:
        fetcher.get("https://public.example/", respect_robots=False)
    assert err.value.code == "not_allowed"


def test_fetcher_caps_body_size() -> None:
    routes = {"https://big.example/": httpx.Response(200, content=b"x" * 2000)}
    fetcher = SafeFetcher(
        resolver=lambda host: ["93.184.216.34"],
        transport=httpx.MockTransport(lambda r: routes[str(r.url)]),
        max_bytes=1000,
    )
    got = fetcher.get("https://big.example/", respect_robots=False)
    assert len(got.body) == 1000 and got.truncated


def test_robots_txt_is_respected() -> None:
    routes = {
        "https://site.example/robots.txt": httpx.Response(
            200, text="User-agent: *\nDisallow: /private"
        ),
        "https://site.example/public": httpx.Response(200, text="ok"),
    }
    fetcher = _fetcher(routes, {"site.example": "93.184.216.34"})
    assert fetcher.get("https://site.example/public").status == 200
    with pytest.raises(FetchError) as err:
        fetcher.get("https://site.example/private/page")
    assert err.value.code == "blocked"


def test_youtube_chapters_and_durations() -> None:
    description = "Intro text\n0:00 Intro\n2:15 Eye contact\n1:02:03 Questions\nThanks"
    assert parse_chapters(description) == [
        {"t": 0, "title": "Intro"},
        {"t": 135, "title": "Eye contact"},
        {"t": 3723, "title": "Questions"},
    ]
    assert parse_chapters("1:00 not from zero\n2:00 x") == []
    assert parse_iso_duration("PT20M7S") == 1207
    assert parse_iso_duration("PT1H") == 3600


def test_schema_is_inlined_and_closed() -> None:
    schema = inline_schema(Reading)
    assert "$ref" not in str(schema) and "$defs" not in schema
    # A field called "title" must survive, even though "title" annotations are stripped.
    assert "title" in schema["properties"] and "title" in schema["required"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["key_facts"]["additionalProperties"] is False


def test_model_input_masks_phones() -> None:
    rendered = render_blocks({"save": {"text": "Call 08123456789"}})
    assert "08123456789" not in rendered and "<<SAVE>>" in rendered


class _Segment:
    def __init__(self, start: float, text: str):
        self.start, self.text = start, text


def _fake_transcripts(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[Exception | None]
) -> list[str]:
    """Each fetch takes the next outcome: an exception to raise, or None for captions."""
    from youtube_transcript_api import YouTubeTranscriptApi

    calls: list[str] = []

    def fetch(self: object, video_id: str, languages: list[str]) -> list[_Segment]:
        calls.append(video_id)
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return [_Segment(0.04, "hello"), _Segment(2.5, "world")]

    monkeypatch.setattr(YouTubeTranscriptApi, "fetch", fetch)
    return calls


def test_captions_retry_when_youtube_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    from youtube_transcript_api._errors import RequestBlocked

    calls = _fake_transcripts(monkeypatch, [RequestBlocked("vid"), None])
    assert gather._captions("vid", pause_s=0) == [
        {"t": 0.0, "text": "hello"},
        {"t": 2.5, "text": "world"},
    ]
    assert len(calls) == 2


def test_captions_go_through_the_proxy_only_when_one_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from youtube_transcript_api import YouTubeTranscriptApi

    proxies: list[Any] = []
    real_init = YouTubeTranscriptApi.__init__

    def init(self: YouTubeTranscriptApi, proxy_config: Any = None, **kwargs: Any) -> None:
        proxies.append(proxy_config)
        real_init(self, proxy_config=proxy_config, **kwargs)

    monkeypatch.setattr(YouTubeTranscriptApi, "__init__", init)
    _fake_transcripts(monkeypatch, [None, None])
    gather._captions("vid", pause_s=0)
    gather._captions("vid", proxy_url="http://u:p@proxy.example:80/", pause_s=0)
    assert proxies[0] is None
    assert proxies[1].to_requests_dict() == {
        "http": "http://u:p@proxy.example:80/",
        "https": "http://u:p@proxy.example:80/",
    }


def test_captions_say_whether_they_were_blocked_or_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from youtube_transcript_api._errors import RequestBlocked, TranscriptsDisabled

    _fake_transcripts(monkeypatch, [RequestBlocked("vid")] * gather.CAPTION_TRIES)
    with pytest.raises(CaptionsUnavailable) as blocked:
        gather._captions("vid", pause_s=0)
    assert blocked.value.blocked

    # A failing proxy is reported as blocked too, not as a video without captions.
    from requests.exceptions import ProxyError

    _fake_transcripts(monkeypatch, [ProxyError("proxy refused")] * gather.CAPTION_TRIES)
    with pytest.raises(CaptionsUnavailable) as proxy_failed:
        gather._captions("vid", proxy_url="http://u:p@proxy.example:80/", pause_s=0)
    assert proxy_failed.value.blocked

    calls = _fake_transcripts(monkeypatch, [TranscriptsDisabled("vid")])
    with pytest.raises(CaptionsUnavailable) as missing:
        gather._captions("vid", pause_s=0)
    assert (
        not missing.value.blocked and len(calls) == 1
    )  # no point retrying a video with no captions
