"""Import a WhatsApp export: a `.zip` with media, or the chat `.txt` alone (docs/04).

The job `import.whatsapp` runs this. Saves keep the time they were sent, run through the
secret screen, and are read at low priority. Running the same export again adds nothing.
"""

import hashlib
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Import, Save, User
from app.db.repo import media as media_repo
from app.db.repo.saves import new_save_from_text
from app.events.emitter import emit
from app.ingest.files import sniff_any
from app.ingest.whatsapp.parser import Planned, parse, plan
from app.jobs import queue
from app.jobs.errors import PermanentError
from app.jobs.runner import JobContext
from app.storage import Storage, get_storage
from app.verify.secrets import screen

# Zip safety (docs/04 · storage rules).
MAX_TOTAL_BYTES = 2 * 1024**3
MAX_ENTRIES = 20_000
MAX_MEDIA_BYTES = 50 * 1024**2  # the storage bucket's limit per file
COMMIT_EVERY = 50
DAMAGED = (
    "Couldn't open this export. It may be damaged or cut short: export the chat again "
    "from WhatsApp and import the new file."
)
STOPPED = "The import stopped before it finished. Try importing the file again."

# What each kind of file becomes. Files not listed here are skipped and counted.
SAVE_KINDS = {
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "image/gif": "image",
    "application/pdf": "pdf",
    "video/mp4": "video",
    "video/quicktime": "video",
    "audio/ogg": "voice",
    "audio/mp4": "voice",
    "audio/mpeg": "voice",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "file",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "file",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "file",
}
# Stickers are reactions, not saves.
_STICKER = re.compile(r"^STK-|-STICKER-", re.I)


def import_folder() -> Path:
    return Path(get_settings().import_dir)


# Tests swap these.
storage_factory: Any = get_storage
folder_factory: Any = import_folder


class ImportRefused(ValueError):
    """The message is shown to the person."""


@dataclass
class Export:
    chat: str
    files: dict[str, zipfile.ZipInfo] = field(default_factory=dict)  # by file name
    archive: zipfile.ZipFile | None = None

    def read(self, name: str) -> bytes | None:
        info = self.files.get(name)
        if info is None or self.archive is None or info.file_size > MAX_MEDIA_BYTES:
            return None
        with self.archive.open(info) as f:
            data = f.read(MAX_MEDIA_BYTES + 1)
        return data if len(data) <= MAX_MEDIA_BYTES else None

    def close(self) -> None:
        if self.archive is not None:
            self.archive.close()  # Windows can't delete the upload while it's open


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and ":" not in path.parts[0]


def open_export(path: Path) -> Export:
    """The chat text and the files beside it. Refuses unsafe zips before reading anything."""
    if not zipfile.is_zipfile(path):
        with path.open("rb") as f:
            if f.read(4) == b"PK\x03\x04":
                raise ImportRefused(DAMAGED)  # a zip whose end is missing
        return Export(chat=path.read_bytes().decode("utf-8-sig", errors="replace"))
    archive = zipfile.ZipFile(path)
    try:
        # A cut-short export can still look like a zip: Python then finds the directory of a
        # zip stored inside it. A real export's first file starts at its very first byte.
        if min((i.header_offset for i in archive.infolist()), default=0) != 0:
            raise ImportRefused(DAMAGED)
        infos = [i for i in archive.infolist() if not i.is_dir()]
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise ImportRefused("This export is too big to import.")
        if not all(_safe_name(i.filename) for i in infos):
            raise ImportRefused("This zip has unsafe file paths, so Homing didn't open it.")
        chats = [i for i in infos if i.filename.lower().endswith(".txt")]
        chat = next((i for i in chats if "whatsapp chat" in i.filename.lower()), None)
        if chat is None and len(chats) == 1:
            chat = chats[0]
        if chat is None:
            raise ImportRefused("There's no WhatsApp chat file in this zip.")
        files = {PurePosixPath(i.filename).name: i for i in infos if i is not chat}
        text = archive.read(chat).decode("utf-8-sig", errors="replace")
    except BaseException:
        archive.close()
        raise
    return Export(chat=text, files=files, archive=archive)


def _local(at: datetime, tz: str) -> datetime:
    return at.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC)


def _media_save(
    db: Session, storage: Storage, user_id: str, item: Planned, export: Export, counts: dict
) -> Save | None:
    name = item.attachment or ""
    data = export.read(name)
    mime = sniff_any(data) if data is not None else None
    kind = SAVE_KINDS.get(mime or "")
    if data is None or mime is None or kind is None or _STICKER.search(name):
        counts["skipped"] += 1  # stickers, contact cards, zips, unknown or missing files
        return None
    media, new = media_repo.store(db, storage, user_id, data, mime, name)
    counts["media"] += int(new)
    caption = item.text.strip() or None
    result = screen(caption or "")
    return Save(
        user_id=user_id,
        origin="whatsapp",
        kind=kind,
        text=caption,
        label=caption if caption and len(caption) <= 60 else None,
        media_id=media.id,
        media_ids=[media.id],
        content_hash=hashlib.sha256(media.sha256.encode()).hexdigest(),
        visibility="private" if result.private else "normal",
        private_reason=result.reason,
    )


def run_import(db: Session, storage: Storage, imp: Import, path: Path, tz: str) -> dict[str, Any]:
    export = open_export(path)
    try:
        return _import(db, storage, imp, export, tz)
    finally:
        export.close()


def _import(db: Session, storage: Storage, imp: Import, export: Export, tz: str) -> dict[str, Any]:
    chat = parse(export.chat)
    if not chat.messages:
        raise ImportRefused("This doesn't look like a WhatsApp chat export.")
    planned, skipped = plan(chat.messages)
    counts: dict[str, Any] = {
        "messages": len(chat.messages),
        "saves": 0,
        "media": 0,
        "private": 0,
        "duplicates": 0,
        "skipped": skipped,
        "already": 0,  # imported before: running the same export again adds nothing
        "total": len(planned),
    }
    imp.format = "zip" if export.archive is not None else "txt"
    imp.counts = {**counts, "order_ambiguous": chat.order_ambiguous}
    imp.status = "importing"
    db.commit()

    imported = {
        (at, h)
        for at, h in db.execute(
            select(Save.saved_at, Save.content_hash).where(
                Save.user_id == imp.user_id, Save.origin == "whatsapp"
            )
        ).all()
    }
    hashes = set(db.scalars(select(Save.content_hash).where(Save.user_id == imp.user_id)).all())
    for n, item in enumerate(planned, 1):
        if item.attachment:
            save = _media_save(db, storage, imp.user_id, item, export, counts)
        else:
            save = new_save_from_text(imp.user_id, item.text, origin="whatsapp")
            if item.label:
                save.label = item.label
        if save is not None:
            save.import_id = imp.id
            save.saved_at = _local(item.at, tz)
            if (save.saved_at, save.content_hash) in imported:
                counts["already"] += 1
            else:
                counts["duplicates"] += int(save.content_hash in hashes)
                counts["private"] += int(save.visibility == "private")
                counts["saves"] += 1
                hashes.add(save.content_hash)
                imported.add((save.saved_at, save.content_hash))
                db.add(save)
                db.flush()
                queue.enqueue(
                    db,
                    "save.read",
                    {"save_id": save.id},
                    user_id=imp.user_id,
                    priority=queue.PRIORITY_BACKLOG,
                    dedupe_key=f"read:{save.id}",
                )
        if n % COMMIT_EVERY == 0:
            imp.counts = {**imp.counts, **counts, "done": n}
            db.commit()
    imp.counts = {**imp.counts, **counts, "done": len(planned)}
    return counts


def import_whatsapp(ctx: JobContext, payload: dict[str, Any]) -> None:
    imp = ctx.db.get(Import, payload["import_id"])
    if imp is None:
        raise PermanentError("Import not found.")
    path = folder_factory() / imp.storage_key
    owner = ctx.db.get(User, imp.user_id)
    try:
        counts = run_import(
            ctx.db, storage_factory(), imp, path, owner.tz if owner else "Africa/Lagos"
        )
    except Exception as exc:
        # A refused or damaged export won't get better by trying again. Anything else gets the
        # usual retries, and the import says it failed on the last one: never "Opening…" for good.
        damaged = isinstance(exc, (zipfile.BadZipFile, OSError, EOFError, zlib.error))
        final = isinstance(exc, ImportRefused) or damaged
        if not final and ctx.attempt < ctx.max_attempts:
            raise
        ctx.db.rollback()
        imp.status = "failed"
        imp.error = str(exc) if isinstance(exc, ImportRefused) else DAMAGED if damaged else STOPPED
        imp.finished_at = datetime.now(UTC)
        ctx.db.commit()
        path.unlink(missing_ok=True)
        raise PermanentError(imp.error) from exc
    imp.status = "done"
    imp.finished_at = datetime.now(UTC)
    files = f", {counts['media']} files" if counts["media"] else ""
    private = f", {counts['private']} kept private" if counts["private"] else ""
    emit(
        ctx.db,
        user_id=imp.user_id,
        agent="system",
        action="imported",
        summary=f"Imported {counts['saves']} saves from WhatsApp{files}{private}.",
    )
    ctx.db.commit()
    path.unlink(missing_ok=True)
