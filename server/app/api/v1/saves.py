"""Saves: add one, list them, and read a save card (docs/07-api.md#saves)."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import is_it_true
from app.core.auth import CurrentUser, require_user
from app.core.errors import AppError
from app.db.models import Check, Media, Save, Snapshot, User, When
from app.db.repo import answers as answers_repo
from app.db.repo import saves as saves_repo
from app.db.repo.users import ensure_user
from app.db.session import get_db
from app.ingest.files import EXTENSIONS, MAX_FILE_BYTES, UnsupportedFile, sniff
from app.ingest.urls import canonical_url
from app.jobs import queue
from app.storage import Storage, get_storage
from app.verify.dates import display
from app.verify.eligibility import assess
from app.verify.secrets import screen

router = APIRouter(prefix="/saves", tags=["saves"])

MAX_TEXT = 20_000
COPY_EXCERPT_CHARS = 1_500


class SaveIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)


class SaveOut(BaseModel):
    id: str
    kind: str
    platform: str | None
    url: str | None
    label: str | None
    text: str | None
    saved_at: datetime
    status: str
    visibility: str
    error: str | None
    files: int = 0  # images or a PDF, fetched with GET /saves/{id}/files/{n}

    @classmethod
    def of(cls, save: Save) -> "SaveOut":
        out = cls.model_validate(save, from_attributes=True)
        out.files = len(save.media_ids or [])
        if save.visibility == "private":
            # Never echoed back; the owner taps Show (GET /saves/{id}/reveal). The link and
            # label go too, since a key inside a URL is one reason a save is private.
            out.text = out.url = out.label = None
        return out


class SaveListItem(SaveOut):
    title: str | None = None
    what: str | None = None


class CopyOut(BaseModel):
    """Our copy of the content, kept at save time: the proof behind "What is it?"."""

    id: str
    kind: str
    source_url: str | None
    chars: int
    excerpt: str

    @classmethod
    def of(cls, snap: Snapshot) -> "CopyOut":
        return cls(
            id=snap.id,
            kind=snap.kind,
            source_url=snap.source_url,
            chars=len(snap.text),
            excerpt=snap.text[:COPY_EXCERPT_CHARS],
        )


class PrivateText(BaseModel):
    text: str


class WhatOut(BaseModel):
    title: str
    what: str
    key_facts: dict[str, Any]
    is_checkable: bool
    is_opportunity: bool


class SaveCard(BaseModel):
    save: SaveOut
    what: WhatOut | None
    true: dict[str, Any] | None = None
    for_: dict[str, Any] | None = Field(default=None, serialization_alias="for")
    when: dict[str, Any] | None = None
    copies: list[CopyOut] = Field(default_factory=list)
    pending: list[str]


class SavePage(BaseModel):
    items: list[SaveListItem]
    next_cursor: str | None


def _item_out(item: dict[str, Any], user_tz: str) -> dict[str, Any]:
    """One item of a list save, as checked. Only verified findings and rules leave the server."""
    deadline = None
    if item.get("deadline_at"):
        at = datetime.fromisoformat(item["deadline_at"])
        deadline = {"at": at, "display": display(at, user_tz)}
    return {
        "name": item.get("name"),
        "url": item.get("url"),
        "status": item.get("status", "queued"),
        "verdict": item.get("verdict"),
        "note": item.get("note"),  # what the post said about it
        "problem": item.get("problem"),  # e.g. "We couldn't open triple-funds.com."
        "official_url": item.get("official_url"),
        "found_by": item.get("found_by"),  # "search" when the save had no link for it
        "findings": [
            {"point": f["point"], "quote": f["quote"], "kind": f["kind"]}
            for f in item.get("findings") or []
            if f.get("verified")
        ],
        "rules": [
            {
                "rule": r.get("rule"),
                "plain": r.get("plain"),
                "quote": r.get("quote"),
                "strength": r.get("strength"),
                "result": r.get("result", "unknown"),
            }
            for r in item.get("rules") or []
            if r.get("verified")
        ],
        "questions": item.get("questions") or [],
        "deadline": deadline,
        "closed": item.get("closed"),
    }


def true_out(
    check: Check | None,
    user_tz: str,
    questions: list[dict[str, Any]] | None = None,
    save_url: str | None = None,
) -> dict[str, Any] | None:
    """Is it true?: only verified findings ever leave the server (docs/05)."""
    if check is None:
        return None
    deadline = None
    if check.deadline_at is not None:
        deadline = {
            "at": check.deadline_at,
            "display": display(check.deadline_at, user_tz),
            "tz_stated": check.deadline_tz_stated,
            "source_text": check.deadline_source_text,
        }
    return {
        "verdict": check.verdict,
        "official_url": check.official_url,
        # The save is just a link to the official page, so nothing was "left out of the post".
        "same_page": bool(save_url and check.official_url)
        and canonical_url(save_url or "") == canonical_url(check.official_url or ""),
        "note": check.note,
        # No official page: the rules below quote the post itself, unconfirmed.
        "from_post": check.official_found_by == "post_only",
        "deadline": deadline,
        "findings": [
            {"point": f["point"], "quote": f["quote"], "kind": f["kind"]}
            for f in check.findings
            if f.get("verified")
        ],
        "rules": [
            {
                "rule": r.get("rule"),
                "plain": r.get("plain"),
                "quote": r.get("quote"),
                "strength": r.get("strength"),
                "result": r.get("result", "unknown"),
            }
            for r in check.eligibility or []
            if r.get("verified")
        ],
        "questions": questions or [],
        "items": [_item_out(i, user_tz) for i in check.items or []],
        "question": check.question_for_user,
        "checked_at": check.checked_at,
    }


def when_out(when: When | None, user_tz: str) -> dict[str, Any] | None:
    if when is None:
        return None
    return {
        "kind": when.kind,
        "source": when.source,
        "due_at": when.due_at,
        "display": display(when.due_at, user_tz) if when.due_at else None,
        "bring_back_at": when.bring_back_at,
        "explanation": when.explanation,
        "source_text": when.source_text,
        "tz_stated": when.tz_stated,
        "time_stated": when.time_stated,
    }


MAX_FILES = 6  # screenshots of one thread, say


def _store_file(db: Session, storage: Storage, user_id: str, upload: UploadFile) -> Media:
    data = upload.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise AppError("too_big", "Files must be 10 MB or smaller.", status=413)
    try:
        mime = sniff(data)
    except UnsupportedFile as exc:
        raise AppError("unsupported_file", str(exc), status=415) from exc
    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Media).where(Media.user_id == user_id, Media.sha256 == sha).limit(1)
    )
    if existing is not None:
        return existing  # the same file saved again: kept once
    key = f"u/{user_id}/{sha}.{EXTENSIONS[mime]}"
    storage.put(key, data, mime)
    media = Media(
        user_id=user_id,
        storage_key=key,
        mime=mime,
        bytes=len(data),
        sha256=sha,
        original_filename=(upload.filename or "")[:200] or None,
    )
    db.add(media)
    db.flush()
    return media


@router.post("/file", status_code=202, response_model=SaveOut)
def create_file_save(
    files: list[UploadFile] = File(...),
    note: str | None = Form(default=None, max_length=MAX_TEXT),
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> SaveOut:
    """A screenshot, flyer or PDF (several images become one save, read in order)."""
    if not files or len(files) > MAX_FILES:
        raise AppError("bad_files", f"Add 1 to {MAX_FILES} files at a time.", status=422)
    ensure_user(db, user)
    media = [_store_file(db, storage, user.id, f) for f in files]
    if any(m.mime == "application/pdf" for m in media) and len(media) > 1:
        raise AppError("bad_files", "Add a PDF on its own.", status=422)
    text = (note or "").strip() or None
    result = screen(text)
    save = Save(
        user_id=user.id,
        origin="upload",
        kind="pdf" if media[0].mime == "application/pdf" else "image",
        text=text,
        label=text if text and len(text) <= 60 else None,
        media_id=media[0].id,
        media_ids=[m.id for m in media],
        content_hash=hashlib.sha256("".join(m.sha256 for m in media).encode()).hexdigest(),
        visibility="private" if result.private else "normal",
        private_reason=result.reason,
    )
    db.add(save)
    db.flush()
    queue.enqueue(
        db,
        "save.read",
        {"save_id": save.id},
        user_id=user.id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"read:{save.id}",
    )
    db.commit()
    return SaveOut.of(save)


@router.post("", status_code=202, response_model=SaveOut)
def create_save(
    body: SaveIn,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> SaveOut:
    """Store the save and queue "What is it?" in the same transaction."""
    ensure_user(db, user)
    save = saves_repo.new_save_from_text(user.id, body.text)
    db.add(save)
    db.flush()
    queue.enqueue(
        db,
        "save.read",
        {"save_id": save.id},
        user_id=user.id,
        priority=queue.PRIORITY_USER,
        dedupe_key=f"read:{save.id}",
    )
    db.commit()
    return SaveOut.of(save)


@router.get("", response_model=SavePage)
def list_saves(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> SavePage:
    rows = saves_repo.list_saves(db, user.id, limit=limit, before_id=cursor)
    readings = saves_repo.readings_for(db, [s.id for s in rows])
    items = []
    for s in rows:
        reading = readings.get(s.id)
        items.append(
            SaveListItem(
                **SaveOut.of(s).model_dump(),
                title=reading.title if reading else None,
                what=reading.what if reading else None,
            )
        )
    return SavePage(
        items=items,
        next_cursor=rows[-1].id if len(rows) == limit else None,
    )


@router.get("/{save_id}", response_model=SaveCard, response_model_by_alias=True)
def save_card(
    save_id: str,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> SaveCard:
    save = saves_repo.get_save(db, user.id, save_id)
    if save is None:
        raise AppError("save_not_found", "That save doesn't exist.", status=404)
    reading = saves_repo.get_reading(db, save.id)
    is_private = save.visibility == "private"
    owner = db.get(User, user.id)
    user_tz = owner.tz if owner else "Africa/Lagos"

    pending: list[str] = []
    if reading is None and save.status in ("received", "reading"):
        pending = ["what"] if is_private else ["what", "true", "for", "when"]
    elif not is_private:
        live = answers_repo.working_on(db, save.id)
        pending = [a for a in ("true", "for", "when") if a in live]
        if "true" in live:
            pending.append("when")  # the "when" waits for the check's deadline

    check = None if is_private else answers_repo.get_check(db, save.id)
    questions = []
    if check is not None and check.verdict == "needs_your_answer":
        facts = is_it_true.facts_for(db, user.id, check)
        ref_year = (check.deadline_at or datetime.now(UTC)).year
        questions = assess(check.eligibility or [], facts, ref_year=ref_year).questions
    if check is not None and check.items:
        # A list: the profile questions its items need, asked once for all of them.
        seen: dict[str, dict[str, Any]] = {}
        for item in check.items:
            for q in item.get("questions") or []:
                seen.setdefault(q["id"], q)
        questions = list(seen.values())
    true = true_out(check, user_tz, questions, save.url)
    if true is None and reading is not None and not reading.is_checkable and not is_private:
        true = {"verdict": "nothing_to_check"}

    for_ = None
    if not is_private and reading is not None and "for" not in pending:
        threads = answers_repo.threads_of(db, save)
        for_ = {
            "threads": [
                {"id": t.id, "title": t.title, "position": pos, "count": total}
                for t, pos, total in threads
            ],
            "duplicate_of": save.duplicate_of,
        }

    return SaveCard(
        save=SaveOut.of(save),
        what=WhatOut.model_validate(reading, from_attributes=True) if reading else None,
        true=true,
        for_=for_,
        when=None if is_private else when_out(answers_repo.get_when(db, save.id), user_tz),
        copies=[CopyOut.of(snap) for snap in saves_repo.snapshots_for(db, save.id)],
        pending=sorted(set(pending), key=["what", "true", "for", "when"].index),
    )


class AnswerIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=40)
    value: str | int | bool


class AnswerOut(BaseModel):
    summary: str


@router.post("/{save_id}/answer", response_model=AnswerOut)
def answer(
    save_id: str,
    body: AnswerIn,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> AnswerOut:
    """One answer, remembered, and every saved opportunity re-judged by code (no model call)."""
    if saves_repo.get_save(db, user.id, save_id) is None:
        raise AppError("save_not_found", "That save doesn't exist.", status=404)
    try:
        summary = is_it_true.answer(db, user.id, save_id, body.question_id, body.value)
    except (is_it_true.BadAnswer, ValueError) as exc:
        raise AppError("bad_answer", str(exc) or "That answer doesn't fit.", status=422) from exc
    db.commit()
    return AnswerOut(summary=summary)


@router.get("/{save_id}/files/{index}")
def file(
    save_id: str,
    index: int,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> Response:
    """One of the owner's files on a save, e.g. the flyer, to show on its card."""
    save = saves_repo.get_save(db, user.id, save_id)
    ids = save.media_ids if save else []
    media = db.get(Media, ids[index]) if 0 <= index < len(ids) else None
    if save is None or media is None or media.user_id != user.id:
        raise AppError("file_not_found", "That file doesn't exist.", status=404)
    return Response(
        content=storage.get(media.storage_key),
        media_type=media.mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{save_id}/reveal", response_model=PrivateText)
def reveal(
    save_id: str,
    response: Response,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> PrivateText:
    """The owner's own text, shown on tap. Private saves leave out their text everywhere else."""
    save = saves_repo.get_save(db, user.id, save_id)
    if save is None or save.text is None:
        raise AppError("save_not_found", "That save doesn't exist.", status=404)
    response.headers["Cache-Control"] = "no-store"
    return PrivateText(text=save.text)
