"""What is it? Reads every save, keeps a copy of its content, and says what it is.

See docs/03-agents.md#what-is-it. Never calls a model on a private save, never invents content
it couldn't read, and never edits what the user saved.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AgentEvent, Media, Save, Snapshot
from app.db.repo import saves as saves_repo
from app.events.emitter import emit
from app.ingest.fetch import SafeFetcher
from app.ingest.files import image_for_model, pdf_text
from app.ingest.gather import Gathered, SnapshotIn, gather_link
from app.ingest.urls import find_urls
from app.jobs import queue
from app.jobs.errors import DeferredError, PermanentError
from app.jobs.runner import JobContext
from app.llm.gateway import PURPOSES, Attachment, ModelGateway
from app.schemas.agents import FileReading, Reading
from app.storage import get_storage
from app.verify.secrets import screen

SNAPSHOT_CHARS_FOR_MODEL = 40_000  # about 10k tokens

PRIVATE_REASONS = {
    "looks_like_code": "it looks like a code",
    "looks_like_one_time_code": "it looks like a one-time code",
    "looks_like_account_number": "it looks like an account number",
    "looks_like_card_number": "it looks like a card number",
    "looks_like_id_number": "it looks like an ID number",
    "looks_like_api_key": "it looks like a key",
    "looks_like_password": "it looks like a password",
    "looks_like_secret_token": "it looks like a secret",
}

FILE_KINDS = ("image", "pdf")
FILE_TEXT_CHARS = 200_000

KIND_WORDS = {
    "youtube": "a YouTube video",
    "x": "an X post",
    "instagram": "an Instagram post",
    "facebook": "a Facebook post",
    "tiktok": "a TikTok",
    "web": "a page",
}
FILE_WORDS = {"image": "an image", "pdf": "a PDF"}

COPY_LABELS = {
    "ocr_text": "Our copy of the words on it",
    "pdf_text": "Our copy of the PDF's text",
    "page_text": "Our copy of the page",
    "post_text": "Our copy of the post",
    "transcript": "Our copy of the captions",
    "metadata": "Our copy of the title and description",
}

PAUSED = "Paused until tomorrow: today's reading budget is used up."

# Tests swap these for fakes; agents never build clients themselves.
gateway_factory: Any = ModelGateway
fetcher_factory: Any = SafeFetcher
storage_factory: Any = get_storage


def _read_file(ctx: JobContext, save: Save) -> tuple[Gathered, FileReading | None]:
    """A PDF with a text layer is read as text. Images and scanned PDFs go to Muse Spark,
    which returns every word on them as our copy of the content."""
    storage = storage_factory()
    ids = save.media_ids or ([save.media_id] if save.media_id else [])
    files = [(m, storage.get(m.storage_key)) for i in ids if (m := ctx.db.get(Media, i))]
    if not files:
        raise PermanentError("The file for this save is missing.")
    first, data = files[0]
    if first.mime == "application/pdf":
        pdf = pdf_text(data)
        if not pdf.scanned:
            copy = SnapshotIn("pdf_text", pdf.text[:FILE_TEXT_CHARS], None, {"pages": pdf.pages})
            return Gathered(snapshots=[copy]), None
        attachments = [Attachment(data, first.mime, first.original_filename or "file.pdf")]
    else:
        attachments = [
            Attachment(*image_for_model(raw, m.mime), m.original_filename or "image")
            for m, raw in files
        ]
    reading: FileReading = gateway_factory(ctx.db).run(
        "read.file",
        user_id=save.user_id,
        inputs={"save": {"kind": save.kind, "files": len(files), "note": save.text}},
        save_ids=[save.id],
        attachments=attachments,
    )
    copy = SnapshotIn("ocr_text", reading.text[:FILE_TEXT_CHARS], None, {"files": len(files)})
    return Gathered(snapshots=[copy] if reading.text.strip() else []), reading


def _keep_file_private(ctx: JobContext, save: Save, reason: str | None) -> None:
    """The words on the file look like a secret: keep the save private and don't keep the text."""
    save.visibility = "private"
    save.private_reason = reason
    why = PRIVATE_REASONS.get(reason or "", "it looks sensitive")
    saves_repo.upsert_reading(
        ctx.db,
        save.id,
        {
            "title": "Kept private",
            "what": f"Kept private because what it shows {why.removeprefix('it ')}.",
            "key_facts": {},
            "is_checkable": False,
            "is_opportunity": False,
            "model": "none",
            "prompt_version": "none",
        },
    )
    save.status = "ready"
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="what",
        action="kept_private",
        summary=f"Kept a file private: what it shows {why.removeprefix('it ')}.",
        save_id=save.id,
    )


def _gather(save: Save) -> Gathered:
    if save.kind == "link" and save.url:
        return gather_link(save.url, fetcher_factory(), get_settings())
    return Gathered()  # notes and lists: the save's own text is the content


def _model_inputs(save: Save, gathered: Gathered, snapshots: list[Snapshot]) -> dict[str, Any]:
    content = []
    budget = SNAPSHOT_CHARS_FOR_MODEL
    for snap in snapshots:
        text = snap.text[:budget]
        budget -= len(text)
        content.append(
            {
                "kind": snap.kind,
                "source": snap.source_url,
                "meta": _small_meta(snap.meta),
                "text": text,
            }
        )
        if budget <= 0:
            break
    return {
        "save": {
            "kind": save.kind,
            "platform": save.platform,
            "url": save.url,
            "label": save.label,
            "text": save.text if save.kind != "link" or save.label is None else save.label,
            "saved_at": save.saved_at.isoformat() if save.saved_at else None,
        },
        "content": content,
        "notes": gathered.notes,
    }


def _small_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in meta.items() if k not in ("segments",)}


def _note_pause_once(ctx: JobContext, user_id: str) -> None:
    """One "paused" line in The team per user per day, not one per save."""
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    already = ctx.db.scalar(
        select(AgentEvent.id)
        .where(
            AgentEvent.user_id == user_id,
            AgentEvent.action == "paused",
            AgentEvent.created_at >= today,
        )
        .limit(1)
    )
    if already is None:
        emit(
            ctx.db,
            user_id=user_id,
            agent="system",
            action="paused",
            summary="Paused reading: today's model budget is used up. It carries on tomorrow.",
        )


def _hand_over(ctx: JobContext, save: Save, reading: Reading) -> None:
    """Queue the next questions. Only kinds that have a handler yet (slices land one by one)."""
    from app.jobs.handlers import HANDLERS

    # Opportunities are always checked: even a bare link is the page whose rules and date matter.
    # Lists are checked item by item too.
    to_check = reading.is_checkable or reading.is_opportunity or len(reading.items) >= 2
    nxt = ["save.check"] if to_check else ["save.when"]
    nxt += ["save.place", "save.embed"]
    for kind in nxt:
        if kind in HANDLERS:
            prefix = kind.split(".")[1]
            queue.enqueue(
                ctx.db,
                kind,
                {"save_id": save.id},
                user_id=save.user_id,
                priority=queue.PRIORITY_USER,
                dedupe_key=f"{prefix}:{save.id}",
            )


def read_one(ctx: JobContext, payload: dict[str, Any]) -> None:
    if ctx.user_id is None:
        raise PermanentError("save.read needs a user.")
    save = saves_repo.get_save(ctx.db, ctx.user_id, str(payload.get("save_id")))
    if save is None:
        raise PermanentError("That save no longer exists.")

    if save.visibility == "private":
        why = PRIVATE_REASONS.get(save.private_reason or "", "it looks sensitive")
        saves_repo.upsert_reading(
            ctx.db,
            save.id,
            {
                "title": "Kept private",
                "what": f"Kept private because {why}. We never send these to AI.",
                "key_facts": {},
                "is_checkable": False,
                "is_opportunity": False,
                "model": "none",
                "prompt_version": "none",
            },
        )
        save.status = "ready"
        emit(
            ctx.db,
            user_id=save.user_id,
            agent="what",
            action="kept_private",
            summary=f"Kept a save private: {why}.",
            save_id=save.id,
        )
        return

    save.status = "reading"
    ctx.db.commit()

    try:
        file_reading = None
        if save.kind in FILE_KINDS:
            gathered, file_reading = _read_file(ctx, save)
            if file_reading is not None and screen(file_reading.text).private:
                _keep_file_private(ctx, save, screen(file_reading.text).reason)
                return
        else:
            gathered = _gather(save)
        snapshots = [
            Snapshot(
                save_id=save.id, kind=s.kind, source_url=s.source_url, text=s.text, meta=s.meta
            )
            for s in gathered.snapshots
        ]
        ctx.db.add_all(snapshots)
        ctx.db.flush()
        reading: Reading = file_reading or gateway_factory(ctx.db).run(
            "read.text",
            user_id=save.user_id,
            inputs=_model_inputs(save, gathered, snapshots),
            save_ids=[save.id],
        )
    except DeferredError:
        ctx.db.rollback()
        paused = saves_repo.get_save(ctx.db, ctx.user_id, save.id)
        if paused is not None:
            paused.status = "received"
            paused.error = PAUSED
            _note_pause_once(ctx, paused.user_id)
            ctx.db.commit()
        raise
    except Exception as exc:
        # Any error, not only the model's: a save must never sit on "Reading it…" for good.
        if isinstance(exc, PermanentError) or ctx.attempt >= ctx.max_attempts:
            ctx.db.rollback()
            failed = saves_repo.get_save(ctx.db, ctx.user_id, save.id)
            if failed is not None:
                failed.status = "failed"
                failed.error = "Couldn't read this save. Try again later."
                emit(
                    ctx.db,
                    user_id=failed.user_id,
                    agent="what",
                    action="failed",
                    summary="Couldn't read a save.",
                    save_id=failed.id,
                )
                ctx.db.commit()
        raise

    saves_repo.upsert_reading(
        ctx.db,
        save.id,
        {
            "title": reading.title,
            "what": reading.what,
            "key_facts": reading.key_facts.model_dump(),
            "is_checkable": reading.is_checkable,
            "is_opportunity": reading.is_opportunity,
            "items": [i.model_dump() for i in reading.items] or None,
            "model": get_settings().meta_spark_model,
            "prompt_version": PURPOSES[
                "read.file" if file_reading is not None else "read.text"
            ].prompt.removesuffix(".md"),
        },
    )
    save.status = "ready"
    save.error = None
    if save.kind == "note":
        thing = "a post" if find_urls(save.text or "") else "a note"
    elif save.kind in FILE_KINDS:
        many = len(save.media_ids or []) > 1
        thing = f"{len(save.media_ids)} screenshots" if many else FILE_WORDS[save.kind]
    else:
        thing = KIND_WORDS.get(save.platform or "", "a list of links")
    evidence = [
        {"label": COPY_LABELS.get(s.kind, "Our copy of the content"), "snapshot_id": s.id}
        for s in snapshots[:2]
    ]
    if save.url:
        evidence.append({"label": "Original link", "url": save.url})
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="what",
        action="read",
        summary=f"Read {thing}: {reading.title}",
        save_id=save.id,
        evidence=evidence,
    )
    _hand_over(ctx, save, reading)
