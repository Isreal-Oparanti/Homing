"""What is it? Reads every save, keeps a copy of its content, and says what it is.

See docs/03-agents.md#what-is-it. Never calls a model on a private save, never invents content
it couldn't read, and never edits what the user saved.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AgentEvent, Media, Save, Snapshot, User
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
from app.schemas.agents import BatchItem, FileReading, KeyFacts, ListItem, Reading
from app.storage import get_storage
from app.verify.dates import display, parse_deadline
from app.verify.quotes import appears_in
from app.verify.secrets import screen

SNAPSHOT_CHARS_FOR_MODEL = 40_000  # about 10k tokens
# Imported saves are a backlog: the first reading needs the gist, and Is it true? reads the
# official page itself. About 2k tokens.
BACKLOG_CHARS_FOR_MODEL = 8_000
# An imported opportunity with no date is checked only if it was saved this recently.
STALE_AFTER = timedelta(days=180)
# An import's small saves are read up to BATCH_SIZE at a time in one call (read.batch).
BATCH_SIZE = 20
BATCH_ITEM_CHARS = 2_000  # more to read than this, and a save gets a call of its own
BATCH_KINDS = ("link", "note", "list")

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
# Files from WhatsApp imports that Homing keeps but can't read yet (docs/04, S8).
KEPT_WORDS = {"video": "a video", "voice": "a voice note", "file": "a document"}

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
    budget = BACKLOG_CHARS_FOR_MODEL if save.import_id else SNAPSHOT_CHARS_FOR_MODEL
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
    if to_check and save.import_id and not _still_open(ctx, save, reading):
        to_check = False
    nxt = ["save.check"] if to_check else ["save.when"]
    # An import's saves are placed together, seeing the whole pile (What's it for?, S9), not
    # one at a time: better threads, a quarter of the tokens.
    nxt += ["save.embed"] if save.import_id else ["save.place", "save.embed"]
    # An import's saves wait behind anything the person saves by hand.
    priority = queue.PRIORITY_BACKLOG if save.import_id else queue.PRIORITY_USER
    for kind in nxt:
        if kind in HANDLERS:
            prefix = kind.split(".")[1]
            queue.enqueue(
                ctx.db,
                kind,
                {"save_id": save.id},
                user_id=save.user_id,
                priority=priority,
                dedupe_key=f"{prefix}:{save.id}",
            )


def _still_open(ctx: JobContext, save: Save, reading: Reading) -> bool:
    """For a save brought in by an import: is checking it worth the model's time? Yes if a
    date it names is still ahead, or if it names none and was saved in the last six months.
    Otherwise Is it true? says why it held off, and the card offers to check it anyway."""
    owner = ctx.db.get(User, save.user_id)
    tz = owner.tz if owner else "Africa/Lagos"
    now = datetime.now(UTC)
    dates = [
        d.at
        for fact in reading.key_facts.dates
        if fact.role in ("deadline", "event")
        and (d := parse_deadline(fact.text, base=save.saved_at, user_tz=tz))
    ]
    if dates and max(dates) > now:
        return True
    if not dates and now - save.saved_at < STALE_AFTER:
        return True
    why = (
        f"its date passed on {display(max(dates), tz)}"
        if dates
        else f"it was saved on {display(save.saved_at, tz).split(',')[0]} and names no date"
    )
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="true",
        action="held_off",
        summary=f"Didn't check {reading.title}: {why}. Tap Check it now if you still want it.",
        save_id=save.id,
    )
    return False


def _own_words(save: Save) -> bool:
    """Whether the person wrote anything with the link: a label, or text around it."""
    words = save.text or ""
    for url in find_urls(words):
        words = words.replace(url, "")
    return bool(save.label or words.strip())


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

    if save.kind in KEPT_WORDS:
        thing = KEPT_WORDS[save.kind]
        caption = (save.text or "").strip()
        saves_repo.upsert_reading(
            ctx.db,
            save.id,
            {
                "title": caption[:80] if caption else f"{thing.capitalize()} you saved",
                "what": f"{thing.capitalize()}, kept with your words. Homing can't read it yet.",
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
            action="kept",
            summary=f"Kept {thing}; Homing can't read it yet.",
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
        if file_reading is None and save.kind == "link" and not snapshots and not _own_words(save):
            # Nothing came back and the person wrote nothing: a model could only guess.
            _nothing_to_read(ctx, save, gathered)
            return
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

    _finish(ctx, save, reading, snapshots, "read.file" if file_reading else "read.text")


def _finish(
    ctx: JobContext, save: Save, reading: Reading, snapshots: list[Snapshot], purpose: str
) -> None:
    """Store the reading, tell The team, and hand over to the next questions."""
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
            "prompt_version": PURPOSES[purpose].prompt.removesuffix(".md"),
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


def _nothing_to_read(ctx: JobContext, save: Save, gathered: Gathered) -> None:
    thing = KIND_WORDS.get(save.platform or "", "a link")
    note = gathered.notes[0] if gathered.notes else "Homing couldn't open this link."
    saves_repo.upsert_reading(
        ctx.db,
        save.id,
        {
            "title": f"{thing[0].upper()}{thing[1:]} you saved",
            "what": note,
            "key_facts": {},
            "is_checkable": False,
            "is_opportunity": False,
            "model": "none",
            "prompt_version": "none",
        },
    )
    save.status = "ready"
    save.error = None
    emit(
        ctx.db,
        user_id=save.user_id,
        agent="what",
        action="nothing_to_read",
        summary=f"Kept {thing} without guessing at it: {note}",
        save_id=save.id,
        evidence=[{"label": "Original link", "url": save.url}] if save.url else [],
    )


def _enqueue_read(ctx: JobContext, save: Save) -> None:
    queue.enqueue(
        ctx.db,
        "save.read",
        {"save_id": save.id},
        user_id=save.user_id,
        priority=queue.PRIORITY_BACKLOG if save.import_id else queue.PRIORITY_USER,
        dedupe_key=f"read:{save.id}",
    )


def _own_facts_only(item: BatchItem, save: Save, snapshots: list[Snapshot]) -> Reading:
    """A batch reading keeps only facts found in its own save's words, so saves read together
    can never borrow from each other."""
    own = "\n".join(
        [save.text or "", save.label or "", save.url or ""]
        + [s.text[:BATCH_ITEM_CHARS] for s in snapshots]
    )
    facts = item.key_facts
    kept = KeyFacts(
        dates=[d for d in facts.dates if appears_in(d.text, own)],
        amounts=[a for a in facts.amounts if appears_in(a.text, own)],
        requirements=[r for r in facts.requirements if appears_in(r.text, own)],
        links=[u for u in facts.links if u in own],
        organisations=[o for o in facts.organisations if appears_in(o, own)],
        places=[p for p in facts.places if appears_in(p, own)],
    )
    items = [
        ListItem(name=i.name, url=i.url if i.url and i.url in own else None, note=i.note)
        for i in item.items
        if appears_in(i.name, own)
    ]
    return Reading(
        title=item.title,
        what=item.what,
        key_facts=kept,
        is_checkable=item.is_checkable,
        is_opportunity=item.is_opportunity,
        items=items,
    )


def read_batch(ctx: JobContext, payload: dict[str, Any]) -> None:
    """What is it? for an import's small saves, up to 20 in one model call, so the instructions
    are sent once instead of 20 times. A save with more to read gets a call of its own; a
    private save, or one with nothing to read, never reaches the model."""
    if ctx.user_id is None:
        raise PermanentError("save.read_batch needs a user.")
    ids = [str(i) for i in payload.get("save_ids", [])][:BATCH_SIZE]
    saves = [
        s
        for i in ids
        if (s := saves_repo.get_save(ctx.db, ctx.user_id, i)) is not None and s.status == "received"
    ]
    gateway = gateway_factory(ctx.db)
    try:
        batch: list[tuple[str, Save, Gathered, list[Snapshot]]] = []
        for save in saves:
            if save.visibility == "private" or save.kind not in BATCH_KINDS:
                _enqueue_read(ctx, save)  # private and file saves have their own path
                continue
            gathered = _gather(save)
            snapshots = [
                Snapshot(
                    save_id=save.id, kind=x.kind, source_url=x.source_url, text=x.text, meta=x.meta
                )
                for x in gathered.snapshots
            ]
            ctx.db.add_all(snapshots)
            ctx.db.flush()
            if save.kind == "link" and not snapshots and not _own_words(save):
                _nothing_to_read(ctx, save, gathered)
            elif sum(len(x.text) for x in snapshots) > BATCH_ITEM_CHARS:
                inputs = _model_inputs(save, gathered, snapshots)
                reading = gateway.run(
                    "read.text", user_id=save.user_id, inputs=inputs, save_ids=[save.id]
                )
                _finish(ctx, save, reading, snapshots, "read.text")
            else:
                batch.append((f"S{len(batch) + 1}", save, gathered, snapshots))
        if not batch:
            return
        out = gateway.run(
            "read.batch",
            user_id=ctx.user_id,
            inputs={
                "saves": [
                    {"id": sid, **_model_inputs(save, gathered, snapshots)}
                    for sid, save, gathered, snapshots in batch
                ]
            },
            save_ids=[save.id for _, save, _, _ in batch],
        )
        got = {r.id: r for r in out.readings}
        read = 0
        for sid, save, _gathered, snapshots in batch:
            item = got.get(sid)
            if item is None:
                _enqueue_read(ctx, save)  # skipped by the model: read it on its own
                continue
            _finish(ctx, save, _own_facts_only(item, save, snapshots), snapshots, "read.batch")
            read += 1
        if read > 1:
            emit(
                ctx.db,
                user_id=ctx.user_id,
                agent="what",
                action="read_batch",
                summary=f"Read {read} small saves together in one go, to save effort.",
            )
    except DeferredError:
        ctx.db.rollback()
        for save in saves:
            paused = saves_repo.get_save(ctx.db, ctx.user_id, save.id)
            if paused is not None and paused.status == "received":
                paused.error = PAUSED
        _note_pause_once(ctx, ctx.user_id)
        ctx.db.commit()
        raise
    except Exception as exc:
        if isinstance(exc, PermanentError) or ctx.attempt >= ctx.max_attempts:
            # Reading together keeps failing: read each save on its own instead.
            ctx.db.rollback()
            for save in saves:
                fresh = saves_repo.get_save(ctx.db, ctx.user_id, save.id)
                if fresh is not None and fresh.status == "received":
                    _enqueue_read(ctx, fresh)
            ctx.db.commit()
        raise
