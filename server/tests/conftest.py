"""Integration tests run against TEST_DATABASE_URL, inside a throwaway schema per run.

No Docker needed: the schema is created, migrated, used and dropped (docs/11-testing-evals.md).
Tests marked `integration` are skipped when TEST_DATABASE_URL isn't set.
"""

import os
import uuid
from collections.abc import Iterator

# Tests never hold a real model key (a placeholder lets the client be built; every model call
# in tests is a fake). Set before any Settings is read, so it wins over server/.env.
os.environ["META_API_KEY"] = "test-placeholder-not-a-key"
# Request limits are tested on their own (test_ratelimit.py); other tests send freely.
os.environ["RATE_LIMITS"] = "false"

import pytest  # noqa: E402
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

TABLES = "users, media, imports, jobs, model_calls"  # TRUNCATE … CASCADE clears the rest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: needs TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    url = get_settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    schema = f"test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(url, connect_args={"prepare_threshold": None})
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(
        url, pool_size=4, max_overflow=2, connect_args={"prepare_threshold": None}
    )

    @event.listens_for(engine, "connect")
    def _use_schema(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        with dbapi_conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}", public')
        dbapi_conn.commit()

    cfg = Config("alembic.ini")
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        cfg.attributes["schema"] = schema
        command.upgrade(cfg, "head")
        conn.commit()
        for table in ("users", "jobs", "saves", "alembic_version"):
            found = conn.execute(text(f"SELECT to_regclass('\"{schema}\".{table}')")).scalar()
            assert found, f"migration leaked out of the test schema: no {schema}.{table}"

    yield engine

    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


@pytest.fixture
def sessions(db_engine: Engine) -> sessionmaker[Session]:
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    with factory() as db:
        db.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        db.commit()
    return factory


@pytest.fixture
def db(sessions: sessionmaker[Session]) -> Iterator[Session]:
    with sessions() as session:
        yield session


@pytest.fixture(autouse=True)
def no_web_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never call the real search service; tests that need search pass a fake."""
    from app.agents import is_it_true

    monkeypatch.setattr(is_it_true, "search_factory", lambda: None)


@pytest.fixture(autouse=True)
def no_real_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Tests never touch the real bucket, whatever STORAGE_BACKEND says; tests that need files
    swap in their own LocalStorage."""
    from app.agents import what_is_it
    from app.ingest.whatsapp import importer
    from app.storage import LocalStorage

    local = LocalStorage(tmp_path_factory.mktemp("files"))
    monkeypatch.setattr(what_is_it, "storage_factory", lambda: local)
    monkeypatch.setattr(importer, "storage_factory", lambda: local)


class _QuietEmbedder:
    def embed(self, texts: list[str], kind: str) -> list[list[float]]:
        return [[1.0] + [0.0] * 383 for _ in texts]


@pytest.fixture(autouse=True)
def no_real_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never load the 120 MB model; tests that need search pass their own fake."""
    from app.search import hybrid

    monkeypatch.setattr(hybrid, "embedder_factory", _QuietEmbedder)


class _NoWonder:
    def __init__(self, db: object) -> None:
        raise RuntimeError("tests never call the real Muse Wonder")


@pytest.fixture(autouse=True)
def no_real_wonder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ask's agent never reaches the real model in tests: it fails at once and the Spark
    pipeline (with each test's own fake) answers; tests of the agent pass their own fake."""
    from app.agents import finds_more
    from app.search import ask_agent

    monkeypatch.setattr(ask_agent, "gateway_factory", _NoWonder)
    # Finding more never reaches the real web or Wonder either; its own tests pass fakes.
    monkeypatch.setattr(finds_more, "gateway_factory", _NoWonder)
    monkeypatch.setattr(finds_more, "search_factory", lambda: None)
    # Is it true? takes its fixed path in tests; the source agent's own tests pass fakes.
    from app.agents import is_it_true

    monkeypatch.setattr(is_it_true, "_agent_source", lambda ctx, save, reading: None)
