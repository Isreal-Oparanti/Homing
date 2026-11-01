"""Integration tests run against TEST_DATABASE_URL, inside a throwaway schema per run.

No Docker needed: the schema is created, migrated, used and dropped (docs/11-testing-evals.md).
Tests marked `integration` are skipped when TEST_DATABASE_URL isn't set.
"""

import uuid
from collections.abc import Iterator

import pytest
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
