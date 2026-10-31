"""Where files live: the local disk in development, a private Supabase bucket in production.

Keys look like `u/{user_id}/{sha256}.{ext}` (docs/02-data-model.md · media). Only the server
reads and writes them; models get the bytes inline, never a public link.
"""

from functools import lru_cache
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings


class Storage(Protocol):
    def put(self, key: str, data: bytes, mime: str) -> None: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Storage key escapes the storage folder.")
        return path

    def put(self, key: str, data: bytes, mime: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class SupabaseStorage:
    """Supabase Storage over its REST API, with the service key (server only)."""

    def __init__(self, url: str, key: str, bucket: str):
        self.base = f"{url.rstrip('/')}/storage/v1/object/{bucket}"
        self.headers = {"Authorization": f"Bearer {key}", "apikey": key}

    def put(self, key: str, data: bytes, mime: str) -> None:
        res = httpx.post(
            f"{self.base}/{key}",
            content=data,
            headers={**self.headers, "Content-Type": mime, "x-upsert": "true"},
            timeout=60,
        )
        res.raise_for_status()

    def get(self, key: str) -> bytes:
        res = httpx.get(f"{self.base}/{key}", headers=self.headers, timeout=60)
        res.raise_for_status()
        return res.content


def build(settings: Settings) -> Storage:
    if settings.storage_backend == "supabase":
        return SupabaseStorage(
            settings.supabase_url, settings.supabase_service_key, settings.storage_bucket
        )
    return LocalStorage(Path(settings.storage_dir))


@lru_cache
def get_storage() -> Storage:
    return build(get_settings())
