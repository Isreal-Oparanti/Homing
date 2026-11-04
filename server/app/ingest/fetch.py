"""SafeFetcher: the only way the server fetches a URL.

See docs/09-security-privacy.md#ssrf-and-fetching.

- http/https on ports 80/443 only;
- every hostname resolves only to public addresses, re-checked on every redirect (max 5);
- the address actually connected to is checked too, against DNS rebinding;
- bodies are capped (5 MB) and robots.txt is respected.
"""

import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "HomingBot/0.1 (+https://github.com/Isreal-Oparanti/Homing)"
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
ROBOTS_TTL_S = 3600

Resolver = Callable[[str], list[str]]


class FetchError(Exception):
    """`code` is stable for the UI; the message is plain language."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Fetched:
    url: str
    status: int
    content_type: str
    body: bytes
    truncated: bool

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _system_resolver(host: str) -> list[str]:
    try:
        return list({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror as exc:
        raise FetchError("unreachable", "Couldn't find that website.") from exc


def is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class SafeFetcher:
    def __init__(
        self,
        *,
        resolver: Resolver = _system_resolver,
        transport: httpx.BaseTransport | None = None,
        max_bytes: int = MAX_BYTES,
    ):
        self._resolve = resolver
        self._max_bytes = max_bytes
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
        self._robots: dict[str, tuple[float, RobotFileParser | None]] = {}

    def check_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise FetchError("not_allowed", "Only web links can be opened.")
        if parts.port not in (None, 80, 443):
            raise FetchError("not_allowed", "That link uses a port we don't open.")
        host = parts.hostname
        if not host:
            raise FetchError("not_allowed", "That link has no website in it.")
        try:
            addresses = [str(ipaddress.ip_address(host))]
        except ValueError:
            addresses = self._resolve(host)
        if not addresses or not all(is_public_ip(a) for a in addresses):
            raise FetchError("not_allowed", "That link points somewhere private.")

    def _check_peer(self, response: httpx.Response) -> None:
        stream = response.extensions.get("network_stream")
        peer = stream.get_extra_info("server_addr") if stream is not None else None
        if peer and not is_public_ip(str(peer[0])):
            raise FetchError("not_allowed", "That link points somewhere private.")

    def robots_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None or time.monotonic() - cached[0] > ROBOTS_TTL_S:
            parser: RobotFileParser | None = None
            try:
                got = self.get(f"{origin}/robots.txt", respect_robots=False)
                if got.status == 200:
                    parser = RobotFileParser()
                    parser.parse(got.text().splitlines())
            except FetchError:
                parser = None  # no robots.txt we can read: allowed
            cached = (time.monotonic(), parser)
            self._robots[origin] = cached
        parser = cached[1]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    def get(self, url: str, *, respect_robots: bool = True, accept: str = "*/*") -> Fetched:
        if respect_robots and not self.robots_allowed(url):
            raise FetchError(
                "blocked",
                "This site asks programs like Homing not to read it, and Homing respects that.",
            )
        for _ in range(MAX_REDIRECTS + 1):
            self.check_url(url)
            try:
                with self._client.stream("GET", url, headers={"Accept": accept}) as res:
                    self._check_peer(res)
                    if res.is_redirect and "location" in res.headers:
                        url = urljoin(url, res.headers["location"])
                        continue
                    body = bytearray()
                    truncated = False
                    for chunk in res.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            del body[self._max_bytes :]
                            truncated = True
                            break
                    return Fetched(
                        url=str(res.url),
                        status=res.status_code,
                        content_type=res.headers.get("content-type", "").split(";")[0].strip(),
                        body=bytes(body),
                        truncated=truncated,
                    )
            except httpx.TimeoutException as exc:
                raise FetchError("unreachable", "The website took too long to answer.") from exc
            except httpx.HTTPError as exc:
                raise FetchError("unreachable", "Couldn't open this link.") from exc
        raise FetchError("unreachable", "That link redirects too many times.")
