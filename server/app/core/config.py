"""Settings from the environment. The full list is in docs/10-deployment-ops.md."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://homing:homing@127.0.0.1:5432/homing"
    proxy_secret: str = ""
    admin_token: str = ""
    run_worker_in_api: bool = True

    meta_api_base: str = "https://api.meta.ai/v1"
    meta_api_key: str = ""
    meta_spark_model: str = ""
    meta_transcribe_model: str = ""

    @property
    def is_local(self) -> bool:
        return self.env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
