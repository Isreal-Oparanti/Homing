import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

SECRET = "test-secret"


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret=SECRET)
    return TestClient(app)


def user_headers(secret: str = SECRET) -> dict[str, str]:
    return {
        "X-Homing-Proxy-Secret": secret,
        "X-Homing-User-Id": "u1",
        "X-Homing-User-Email": "u1@example.com",
    }


def test_health_needs_no_auth(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_me_rejects_missing_secret(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_rejects_wrong_secret(client: TestClient) -> None:
    assert client.get("/api/v1/me", headers=user_headers("wrong")).status_code == 401


def test_me_returns_the_proxied_user(client: TestClient) -> None:
    response = client.get("/api/v1/me", headers=user_headers())
    assert response.status_code == 200
    assert response.json() == {"id": "u1", "email": "u1@example.com", "name": None}


def test_supabase_urls_are_accepted_as_pasted() -> None:
    settings = Settings(database_url="postgresql://u:p@host:5432/postgres")
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/postgres"
    assert Settings(database_url="postgres://u:p@h/db").database_url.startswith(
        "postgresql+psycopg://"
    )
