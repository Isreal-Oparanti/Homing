from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Created on first use, so code that never touches the database doesn't need a URL."""
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set. See server/.env.example.")
    # prepare_threshold=None turns off server-side prepared statements, which Supabase's
    # transaction pooler can't handle. It's harmless on the session pooler, so either URL works.
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={"prepare_threshold": None},
    )


@lru_cache
def session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with session_factory()() as db:
        yield db
