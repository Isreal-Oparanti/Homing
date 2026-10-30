"""Settings from the environment. The full list is in docs/10-deployment-ops.md."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _psycopg_url(url: str) -> str:
    """Accept Postgres URLs exactly as Supabase shows them; SQLAlchemy needs the psycopg driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://homing:homing@127.0.0.1:5432/homing"
    test_database_url: str = ""
    # Supabase's free tier allows few pooled connections: keep each process's pool small.
    db_pool_size: int = 3
    db_max_overflow: int = 2
    proxy_secret: str = ""
    admin_token: str = ""
    run_worker_in_api: bool = True

    meta_api_base: str = "https://api.meta.ai/v1"
    meta_api_key: str = ""
    meta_spark_model: str = "muse-spark-1.3"
    meta_transcribe_model: str = "muse-voice-transcribe-1.0"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _use_psycopg(cls, value: str) -> str:
        return _psycopg_url(value)

    @property
    def is_local(self) -> bool:
        return self.env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
