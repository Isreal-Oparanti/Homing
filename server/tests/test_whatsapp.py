import io
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.what_is_it import read_one
from app.core.auth import TICKET_SECONDS, sign_ticket
from app.core.config import Settings, get_settings
from app.db.models import Import, Job, Reading, Save
from app.db.session import get_db
from app.ingest.files import sniff_any
from app.ingest.whatsapp import importer
from app.ingest.whatsapp.parser import parse, plan
from app.jobs.handlers import HANDLERS
from app.jobs.runner import JobContext, Runner
from app.main import create_app
from app.storage import LocalStorage

FIXTURES = Path(__file__).parent / "fixtures" / "whatsapp"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# The parser: pure code ------------------------------------------------------------------


def test_android_export_day_first_24h() -> None:
    chat = parse(_fixture("android_24h.txt"))
    assert chat.day_first and not chat.order_ambiguous
    assert chat.system_lines == 2  # the encryption notice and a deleted message
    first = chat.messages[0]
    assert (first.at, first.sender, first.text) == (
        datetime(2026, 10, 28, 9, 1),
        "Ada",
        "https://example.com/fellowship-2026",
    )
    texts = [m.text for m in chat.messages]
    assert "Remember to ask Tolu about the visa\nand the letter from school" in texts
    assert "Deadline moved to Friday" in texts  # the edit note is gone
    photo = next(m for m in chat.messages if m.attachment)
    assert (photo.attachment, photo.text) == ("IMG-20261028-WA0001.jpg", "Flyer from the hub")
    assert sum(m.media_omitted for m in chat.messages) == 1


def test_android_export_month_first_12h() -> None:
    chat = parse(_fixture("android_12h_month_first.txt"))
    assert not chat.day_first and not chat.order_ambiguous
    assert [m.at for m in chat.messages] == [
        datetime(2026, 10, 28, 21, 5),
        datetime(2026, 10, 28, 21, 6),
        datetime(2026, 11, 2, 11, 59),
        datetime(2026, 11, 2, 0, 30),  # 12:30 am
    ]


def test_ios_export() -> None:
    chat = parse(_fixture("ios.txt"))
    photo, omitted, note = chat.messages
    assert photo.at == datetime(2026, 10, 28, 14, 5, 33)
    assert photo.attachment == "00000012-PHOTO-2026-10-28-14-05-33.jpg"
    assert omitted.media_omitted
    assert note.text == "Line one\nline two"


def test_dates_that_dont_show_the_order_use_the_guess_and_say_so() -> None:
    chat = parse("03/04/2026, 10:00 - Ada: hello")
    assert chat.order_ambiguous and chat.messages[0].at == datetime(2026, 4, 3, 10, 0)
    assert parse("03/04/2026, 10:00 - Ada: hello", day_first_guess=False).messages[0].at.month == 3


def test_messages_become_saves_by_the_rules() -> None:
    planned, skipped = plan(parse(_fixture("android_24h.txt")).messages)
    assert skipped == 2  # ".." and the media the export left out
    link = planned[0]
    assert link.label == "Fellowship for builders"  # sent 60s after the link
    assert [p.text for p in planned].count("Fellowship for builders") == 0
    assert planned[-2].text == "https://example.com/late-label" and planned[-2].label is None
    assert planned[-1].text == "too late to be a label"  # ten minutes later: a note
    assert [p.attachment for p in planned if p.attachment] == [
        "IMG-20261028-WA0001.jpg",
        "STK-20261028-WA0002.webp",
    ]


def test_media_types_come_from_the_bytes() -> None:
    assert sniff_any(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 20) == "video/mp4"
    assert sniff_any(b"OggS\x00\x02" + b"\x00" * 20) == "audio/ogg"
    assert sniff_any(b"BEGIN:VCARD\nVERSION:3.0") == "text/vcard"
    docx = io.BytesIO()
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    assert sniff_any(docx.getvalue()).endswith("wordprocessingml.document")  # type: ignore[union-attr]
    plain = io.BytesIO()
    with zipfile.ZipFile(plain, "w") as z:
        z.writestr("notes.txt", "hi")
    assert sniff_any(plain.getvalue()) == "application/zip"
    assert sniff_any(b"something else") is None


# The importer, through the API and the job runner ----------------------------------------


CHAT = (
    "28/10/2026, 09:01 - Ada: https://example.com/fellowship-2026\n"
    "28/10/2026, 09:02 - Ada: Fellowship for builders\n"
    "28/10/2026, 09:20 - Ada: IMG-20261028-WA0001.jpg (file attached)\n"
    "Flyer from the hub\n"
    "28/10/2026, 09:21 - Ada: STK-20261028-WA0002.webp (file attached)\n"
    "28/10/2026, 09:25 - Ada: VID-20261028-WA0003.mp4 (file attached)\n"
    "28/10/2026, 09:26 - Ada: Tolu.vcf (file attached)\n"
    "28/10/2026, 09:27 - Ada: old.zip (file attached)\n"
    "28/10/2026, 09:40 - Ada: my password is hunter2 for the portal\n"
)


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(out, format="PNG")
    return out.getvalue()


def _export(extra: dict[str, bytes] | None = None) -> bytes:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("a.txt", "inside")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("WhatsApp Chat with Ada.txt", CHAT)
        z.writestr("IMG-20261028-WA0001.jpg", _png())
        z.writestr("STK-20261028-WA0002.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        z.writestr("VID-20261028-WA0003.mp4", b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)
        z.writestr("Tolu.vcf", "BEGIN:VCARD\nVERSION:3.0\nFN:Tolu\nEND:VCARD")
        z.writestr("old.zip", inner.getvalue())
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return out.getvalue()


@pytest.fixture
def client(
    sessions: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    folder = tmp_path / "imports"
    monkeypatch.setattr(importer, "folder_factory", lambda: folder)
    monkeypatch.setattr(importer, "storage_factory", lambda: LocalStorage(tmp_path / "files"))
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        proxy_secret="s", import_dir=str(folder)
    )
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _upload(client: TestClient, data: bytes, name: str = "export.zip") -> dict:
    ticket = sign_ticket(
        {"uid": "u-ada", "email": "ada@example.com", "exp": int(time.time()) + TICKET_SECONDS},
        "s",
    )
    res = client.post(
        "/api/v1/imports/whatsapp",
        files={"file": (name, data)},
        headers={"Authorization": f"Bearer {ticket}"},
    )
    assert res.status_code == 202, res.text
    return res.json()


def _run_import(sessions: sessionmaker[Session]) -> None:
    # The import outranks the reads it queues, so one job is exactly the import.
    Runner(sessions, HANDLERS, threads=1, worker_id="t").run_once()


@pytest.mark.integration
def test_an_export_with_media_imports_and_a_second_run_adds_nothing(
    client: TestClient, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    first = _upload(client, _export())
    _run_import(sessions)
    with sessions() as db:
        imp = db.get(Import, first["id"])
        assert imp is not None and imp.status == "done", imp and imp.error
        counts = imp.counts
        assert (counts["messages"], counts["saves"], counts["media"]) == (8, 4, 2)
        assert (counts["private"], counts["skipped"], counts["already"]) == (1, 3, 0)
        saves = {s.kind: s for s in db.scalars(select(Save).where(Save.import_id == imp.id))}
        assert set(saves) == {"link", "image", "video", "note"}
        link = saves["link"]
        assert link.label == "Fellowship for builders"
        assert link.saved_at == datetime(2026, 10, 28, 8, 1, tzinfo=UTC)  # 09:01 in Lagos
        assert saves["image"].text == "Flyer from the hub"
        assert saves["note"].visibility == "private"
        reads = db.scalars(select(Job).where(Job.kind == "save.read")).all()
        assert len(reads) == 4 and {j.priority for j in reads} == {90}
    assert not list((tmp_path / "imports").iterdir())  # the upload is deleted

    shown = client.get(f"/api/v1/imports/{first['id']}", headers=_headers()).json()
    assert shown["status"] == "done" and shown["counts"]["saves"] == 4

    second = _upload(client, _export())
    _run_import(sessions)
    with sessions() as db:
        again = db.get(Import, second["id"])
        assert again is not None and again.status == "done"
        assert (again.counts["saves"], again.counts["already"]) == (0, 4)


def _headers() -> dict[str, str]:
    return {
        "X-Homing-Proxy-Secret": "s",
        "X-Homing-User-Id": "u-ada",
        "X-Homing-User-Email": "ada@example.com",
    }


@pytest.mark.integration
def test_a_zip_with_unsafe_paths_is_refused(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    sent = _upload(client, _export({"../../escape.txt": b"zip slip"}))
    _run_import(sessions)
    with sessions() as db:
        imp = db.get(Import, sent["id"])
        assert imp is not None and imp.status == "failed"
        assert imp.error == "This zip has unsafe file paths, so Homing didn't open it."
        assert db.scalars(select(Save).where(Save.import_id == imp.id)).first() is None


@pytest.mark.integration
def test_a_file_that_isnt_a_chat_is_refused(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    sent = _upload(client, b"just some words", name="notes.txt")
    _run_import(sessions)
    with sessions() as db:
        imp = db.get(Import, sent["id"])
        assert imp is not None and imp.status == "failed"
        assert imp.error == "This doesn't look like a WhatsApp chat export."


@pytest.mark.integration
def test_a_video_is_kept_with_its_words_but_not_sent_anywhere(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    _upload(client, _export())
    _run_import(sessions)
    with sessions() as db:
        video = db.scalars(select(Save).where(Save.kind == "video")).one()
        read_one(JobContext(db, 0, "save.read", video.user_id), {"save_id": video.id})
        db.commit()
        reading = db.get(Reading, video.id)
        assert reading is not None and reading.model == "none"
        assert reading.title == "A video you saved"
        assert db.get(Save, video.id).status == "ready"  # type: ignore[union-attr]
