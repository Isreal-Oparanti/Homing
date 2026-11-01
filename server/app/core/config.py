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
    db_pool_size: int = 5
    db_max_overflow: int = 2
    # Job runner threads per process. Each holds a DB connection while it works, so this
    # stays below db_pool_size.
    worker_threads: int = 3
    proxy_secret: str = ""
    admin_token: str = ""
    run_worker_in_api: bool = True

    meta_api_base: str = "https://api.meta.ai/v1"
    meta_api_key: str = ""
    meta_spark_model: str = "muse-spark-1.3"
    meta_transcribe_model: str = "muse-voice-transcribe-1.0"
    youtube_api_key: str = ""
    # YouTube captions via youtube-transcript-api (Isreal's decision, docs/adr/0008).
    feature_yt_captions: bool = True
    # Spend guards in tokens (in + out), because Meta hasn't published prices.
    # The demo user gets half the per-user budget (docs/06-models.md#gateway-behaviour).
    model_daily_token_budget: int = 5_000_000
    model_user_daily_token_budget: int = 1_500_000
    spark_max_concurrency: int = 6

    # Files: the local disk in development, a private Supabase bucket in production.
    storage_backend: str = "local"  # local · supabase
    storage_dir: str = "data/storage"
    supabase_url: str = ""
    supabase_service_key: str = ""
    storage_bucket: str = "saves"
    # Web search for Is it true? when a save has no link to its official page.
    search_provider: str = "serper"
    search_api_key: str = ""

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
