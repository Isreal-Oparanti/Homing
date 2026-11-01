"""Before the first deploy: create the private bucket, then copy in files saved locally.

Development and production share one database, so a save made locally must find its file
in the bucket too. Keys are the same in both places (u/{user_id}/{sha256}.{ext}).

Run: python -m uv run python -m app.scripts.setup_storage
Needs SUPABASE_URL and SUPABASE_SERVICE_KEY in .env. Safe to run again.
"""

import mimetypes
from pathlib import Path

from app.core.config import get_settings
from app.storage import SupabaseStorage

settings = get_settings()
bucket = SupabaseStorage(
    settings.supabase_url, settings.supabase_service_key, settings.storage_bucket
)
print("Bucket created." if bucket.ensure_bucket() else "Bucket already there.")

local = Path(settings.storage_dir)
files = sorted(p for p in local.rglob("*") if p.is_file()) if local.exists() else []
for path in files:
    key = path.relative_to(local).as_posix()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    bucket.put(key, path.read_bytes(), mime)
    assert bucket.get(key) == path.read_bytes(), key
print(f"Copied {len(files)} local file(s), each read back and compared.")
