"""Request limits, so one person (or one script) can't flood the API or burn everyone's budget.

Counted per person: the user the web server vouches for (its proxy secret checks out). The demo
account is shared by every visitor, so it's counted per visitor's address, which the web server
passes on; one visitor hammering it can't lock the others out. Anything else (a request
without the proxy secret, a browser upload with a ticket) is counted per address.
The model budgets (llm/gateway.py) still cap what the agents spend; this caps how fast anyone
can ask. The API runs as one process (deploy/ec2/homing-api.service), so counts live in memory.
"""

import hmac
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.auth import DEMO_USER_ID
from app.core.config import get_settings

MINUTE, HOUR = 60, 3600

# Writes that start model or web work: saving, asking, checking, finding, preparing.
HEAVY = (
    ("POST", "/api/v1/saves"),
    ("POST", "/api/v1/asks"),
    ("POST", "/api/v1/moments"),
    ("POST", "/api/v1/threads/rebuild"),
)
HEAVY_ENDINGS = ("/check", "/find", "/transcript", "/text", "/file")

# (bucket, [(requests, seconds), …]): every window must have room.
LIMITS: dict[str, list[tuple[int, int]]] = {
    "import": [(3, HOUR)],
    "heavy": [(20, MINUTE), (150, HOUR)],
    "write": [(60, MINUTE), (600, HOUR)],
    "read": [(300, MINUTE)],
    "anonymous": [(30, MINUTE)],
    "shared": [(100, MINUTE)],
}
MAX_KEYS = 20_000  # forget the oldest counts past this, so memory stays small


class Limiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def wait(self, key: str, bucket: str, now: float | None = None) -> int:
        """0 and counts the request when there's room; else the seconds to wait."""
        now = time.monotonic() if now is None else now
        rules = LIMITS[bucket]
        longest = max(seconds for _, seconds in rules)
        with self._lock:
            hits = self._hits.setdefault(f"{bucket}:{key}", deque())
            while hits and now - hits[0] > longest:
                hits.popleft()
            for allowed, seconds in rules:
                recent = [t for t in hits if now - t <= seconds]
                if len(recent) >= allowed:
                    return max(1, int(seconds - (now - recent[0])) + 1)
            hits.append(now)
            if len(self._hits) > MAX_KEYS:
                for old in list(self._hits)[: MAX_KEYS // 10]:
                    del self._hits[old]
        return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = Limiter()


def bucket_of(method: str, path: str) -> str:
    if method == "POST" and path.startswith("/api/v1/imports"):
        return "import"
    if method in ("GET", "HEAD", "OPTIONS"):
        return "read"
    if (method, path.rstrip("/")) in HEAVY or (method == "POST" and path.endswith(HEAVY_ENDINGS)):
        return "heavy"
    return "write"


def _address(request: Request) -> str:
    # Caddy puts the caller's address first; behind it, request.client is always Caddy.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")


def who(request: Request) -> tuple[str, bool]:
    """(the key to count under, whether the web server vouched for it)."""
    expected = get_settings().proxy_secret
    given = request.headers.get("x-homing-proxy-secret", "")
    user = request.headers.get("x-homing-user-id", "")
    if expected and given and user and hmac.compare_digest(given, expected):
        if user == DEMO_USER_ID:
            visitor = request.headers.get("x-homing-client-ip", "").strip()[:64]
            return f"demo:{visitor or 'shared'}", True
        return f"user:{user}", True
    return f"ip:{_address(request)}", False


async def limit_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    path = request.url.path
    if path.endswith("/health"):
        return await call_next(request)
    key, vouched = who(request)
    bucket = bucket_of(request.method, path) if vouched else "anonymous"
    if key == "demo:shared":
        # The demo without a visitor's address (pages the web server builds itself): every
        # visitor at once, so reads go free and the rest shares a wider limit.
        if bucket == "read":
            return await call_next(request)
        bucket = "shared"
    if request.method == "POST" and request.headers.get("authorization", "").startswith("Bearer "):
        bucket = "heavy"  # a browser upload with a ticket: a file save
    wait = limiter.wait(key, bucket)
    if wait:
        return JSONResponse(
            {
                "error": {
                    "code": "slow_down",
                    "message": f"That's a lot at once. Try again in {wait} seconds.",
                    "details": {"retry_after": wait},
                }
            },
            status_code=429,
            headers={"Retry-After": str(wait)},
        )
    return await call_next(request)
