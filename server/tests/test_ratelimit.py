from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.ratelimit import LIMITS, Limiter, bucket_of, limit_requests, limiter


def _app() -> TestClient:
    app = FastAPI()
    app.middleware("http")(limit_requests)

    @app.post("/api/v1/saves")
    def save() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    limiter.reset()
    return TestClient(app)


def _as(user: str, ip: str = "") -> dict[str, str]:
    headers = {
        "X-Homing-Proxy-Secret": get_settings().proxy_secret or "",
        "X-Homing-User-Id": user,
    }
    return headers | ({"X-Homing-Client-IP": ip} if ip else {})


def test_buckets() -> None:
    assert bucket_of("POST", "/api/v1/saves") == "heavy"
    assert bucket_of("POST", "/api/v1/saves/abc/check") == "heavy"
    assert bucket_of("POST", "/api/v1/asks") == "heavy"
    assert bucket_of("POST", "/api/v1/imports/whatsapp") == "import"
    assert bucket_of("PUT", "/api/v1/me/profile") == "write"
    assert bucket_of("GET", "/api/v1/saves") == "read"


def test_every_window_must_have_room() -> None:
    limits = Limiter()
    allowed = LIMITS["heavy"][0][0]
    waits = [limits.wait("user:a", "heavy", now=100.0 + i * 0.1) for i in range(allowed + 1)]
    assert waits[:allowed] == [0] * allowed and waits[-1] > 0  # the minute is full
    assert limits.wait("user:a", "heavy", now=200.0) == 0  # a minute later, room again
    assert limits.wait("user:b", "heavy", now=100.0) == 0  # someone else is counted apart


def test_a_flood_gets_429_but_not_other_people(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "proxy_secret", "s3cret")
    client = _app()
    allowed = LIMITS["heavy"][0][0]
    codes = [client.post("/api/v1/saves", headers=_as("alice")).status_code for _ in range(25)]
    assert codes[:allowed] == [200] * allowed and codes[-1] == 429
    flooded = client.post("/api/v1/saves", headers=_as("alice"))
    assert flooded.json()["error"]["code"] == "slow_down" and "Retry-After" in flooded.headers
    assert client.post("/api/v1/saves", headers=_as("bob")).status_code == 200
    assert client.get("/api/v1/health").status_code == 200  # never limited


def test_demo_visitors_are_counted_apart(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "proxy_secret", "s3cret")
    client = _app()
    for _ in range(25):
        client.post("/api/v1/saves", headers=_as("demo", ip="1.1.1.1"))
    assert client.post("/api/v1/saves", headers=_as("demo", ip="1.1.1.1")).status_code == 429
    assert client.post("/api/v1/saves", headers=_as("demo", ip="2.2.2.2")).status_code == 200


def test_without_the_proxy_secret_it_is_counted_by_address() -> None:
    client = _app()
    codes = [
        client.post("/api/v1/saves", headers={"X-Homing-User-Id": "victim"}).status_code
        for _ in range(LIMITS["anonymous"][0][0] + 1)
    ]
    assert codes[-1] == 429
    # The spoofed requests didn't use up the real person's room.
    assert limiter.wait("user:victim", "heavy") == 0
