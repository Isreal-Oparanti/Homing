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
    # Public addresses, for links that leave the app (the calendar feed). Not secrets.
    public_api_url: str = "https://homing-api.crowscap.xyz"
    web_url: str = "https://homing-rho.vercel.app"
    admin_token: str = ""
    run_worker_in_api: bool = True
    # Development and production share the database, not each other's work: each worker
    # only takes jobs from its own lane. Production is "main"; set JOB_LANE=dev locally.
    job_lane: str = "main"

    meta_api_base: str = "https://api.meta.ai/v1"
    meta_api_key: str = ""
    meta_spark_model: str = "muse-spark-1.3"
    meta_transcribe_model: str = "muse-voice-transcribe-1.0"
    # Ask runs as a Muse Wonder agent; off, the Spark pipeline answers (search/ask.py).
    ask_agent: bool = True
    # Is it true? finds a save's source with a Muse Wonder agent; off, the fixed path does.
    check_agent: bool = True
    youtube_api_key: str = ""
    # YouTube captions via youtube-transcript-api (Isreal's decision, docs/adr/0008).
    feature_yt_captions: bool = True
    # A proxy for caption requests only (ADR 0008), because YouTube blocks cloud servers.
    # For example http://USER-rotate:PASS@p.webshare.io:80/. It holds a password: never log it.
    captions_proxy_url: str = ""
    # Spend guards in tokens (in + out), because Meta hasn't published prices.
    # Per day. The shared demo account has its own cap below (docs/06-models.md#gateway-behaviour).
    model_daily_token_budget: int = 5_000_000
    model_user_daily_token_budget: int = 1_500_000
    # The demo account is shared by every visitor (judges included), so it gets its own cap.
    model_demo_daily_token_budget: int = 3_000_000
    spark_max_concurrency: int = 6

    # Files: the local disk in development, a private Supabase bucket in production.
    storage_backend: str = "local"  # local · supabase
    storage_dir: str = "data/storage"
    supabase_url: str = ""
    supabase_service_key: str = ""
    storage_bucket: str = "saves"
    # WhatsApp exports wait here between upload and import. The API and the worker share it,
    # so they must run on the same machine (they do: docs/10). Deleted after each import.
    import_dir: str = "data/imports"
    import_max_bytes: int = 1024**3
    # The embedding model for search by meaning (app/search/embed.py), downloaded on first use.
    embed_dir: str = "data/models/multilingual-e5-small"
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
