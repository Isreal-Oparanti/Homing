import io
import math
import struct
import wave
import zipfile
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import what_is_it
from app.core.auth import CurrentUser
from app.db.models import AgentEvent, Reading, Save, Snapshot
from app.db.models.saves import Media
from app.db.repo.users import ensure_user
from app.ingest.files import office_text
from app.ingest.media import RATE, NoSound, to_wav
from app.jobs.runner import JobContext
from app.llm.gateway import VideoLink
from app.schemas.agents import DateFact, KeyFacts, Transcript
from app.schemas.agents import Reading as ReadingOut

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
TALK = " ".join(
    ["Apply to the founders fellowship before Friday, it pays five thousand dollars."] * 5
)


def _tone(seconds: float = 1.0, rate: int = 44_100) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<hh", s, s)
            for i in range(int(seconds * rate))
            for s in [int(8000 * math.sin(2 * math.pi * 440 * i / rate))]
        )
        w.writeframes(frames)
    return out.getvalue()


# Pure code ----------------------------------------------------------------------------------


def test_sound_becomes_16khz_mono_wav() -> None:
    wav, seconds = to_wav(_tone(1.0))
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, RATE, 2)
        assert abs(w.getnframes() / RATE - 1.0) < 0.05
    assert abs(seconds - 1.0) < 0.05
    short, _ = to_wav(_tone(3.0), max_seconds=1)  # the endpoint's limit is respected
    with wave.open(io.BytesIO(short)) as w:
        assert abs(w.getnframes() / RATE - 1.0) < 0.05
    with pytest.raises(NoSound):
        to_wav(b"\x89PNG\r\n\x1a\n not a sound")


def test_words_come_out_of_word_and_powerpoint_files() -> None:
    doc = io.BytesIO()
    with zipfile.ZipFile(doc, "w") as z:
        z.writestr(
            "word/document.xml",
            "<w:document><w:body><w:p><w:r><w:t>Grant &amp; fellowship</w:t></w:r></w:p>"
            '<w:p><w:r><w:t xml:space="preserve">Closes </w:t></w:r><w:r><w:t>30 November</w:t>'
            "</w:r></w:p></w:body></w:document>",
        )
    assert office_text(doc.getvalue()) == "Grant & fellowship\nCloses 30 November"
    deck = io.BytesIO()
    with zipfile.ZipFile(deck, "w") as z:
        z.writestr("ppt/slides/slide2.xml", "<p:sld><a:p><a:t>Second</a:t></a:p></p:sld>")
        z.writestr("ppt/slides/slide10.xml", "<p:sld><a:p><a:t>Tenth</a:t></a:p></p:sld>")
        z.writestr("ppt/slides/slide1.xml", "<p:sld><a:p><a:t>First</a:t></a:p></p:sld>")
    assert office_text(deck.getvalue()) == "First\nSecond\nTenth"  # slides in order
    assert office_text(b"not a zip") == ""


# What is it? on imported files, with fake models and storage -------------------------------


class FakeStorage:
    def __init__(self, url: str | None = "https://signed.example/v.mp4"):
        self.url = url

    def get(self, key: str) -> bytes:
        return b"file bytes"

    def signed_url(self, key: str, seconds: int) -> str | None:
        return self.url


class FakeGateway:
    heard = TALK
    calls: list[dict[str, Any]] = []

    def __init__(self, db: Session):
        pass

    def transcribe(self, wav: bytes, **kwargs: Any) -> Transcript:
        FakeGateway.calls.append({"purpose": "transcribe", **kwargs})
        return Transcript(text=FakeGateway.heard, duration_ms=12_000)

    def run(self, purpose: str, **kwargs: Any) -> ReadingOut:
        FakeGateway.calls.append({"purpose": purpose, **kwargs})
        facts = KeyFacts(
            dates=[
                DateFact(text="before Friday", role="deadline"),
                DateFact(text="Closes 9 December", role="deadline"),  # only on screen
            ]
        )
        return ReadingOut(
            title="Founders fellowship",
            what="A fellowship call.",
            key_facts=facts,
            is_checkable=False,
            is_opportunity=False,
        )


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> FakeStorage:
    FakeGateway.calls, FakeGateway.heard = [], TALK
    storage = FakeStorage()
    monkeypatch.setattr(what_is_it, "gateway_factory", FakeGateway)
    monkeypatch.setattr(what_is_it, "storage_factory", lambda: storage)
    monkeypatch.setattr(what_is_it, "to_wav", lambda data: (b"wav", 12.0))
    return storage


def _media_save(db: Session, kind: str, mime: str, caption: str | None = None) -> str:
    ensure_user(db, ALICE)
    media = Media(
        user_id=ALICE.id,
        storage_key=f"u/a/{kind}",
        mime=mime,
        bytes=10,
        sha256=f"sha-{kind}",
        original_filename=f"{kind}.bin",
    )
    db.add(media)
    db.flush()
    save = Save(
        user_id=ALICE.id,
        kind=kind,
        origin="whatsapp",
        text=caption,
        media_id=media.id,
        media_ids=[media.id],
        content_hash=f"h-{kind}-{caption}",
        status="received",
    )
    db.add(save)
    db.commit()
    return save.id


def _read(db: Session, save_id: str) -> Reading:
    what_is_it.read_one(JobContext(db, 0, "save.read", ALICE.id), {"save_id": save_id})
    db.commit()
    reading = db.get(Reading, save_id)
    assert reading is not None
    return reading


def _purposes() -> list[str]:
    return [c["purpose"] for c in FakeGateway.calls]


@pytest.mark.integration
def test_a_voice_note_is_transcribed_then_read_from_its_words(
    sessions: sessionmaker[Session], fakes: FakeStorage
) -> None:
    with sessions() as db:
        save_id = _media_save(db, "voice", "audio/ogg")
        reading = _read(db, save_id)
        assert _purposes() == ["transcribe", "read.text"]
        assert reading.prompt_version == "read_text.v3"
        speech = db.scalars(select(Snapshot).where(Snapshot.save_id == save_id)).one()
        assert (speech.kind, speech.text, speech.meta) == ("speech", TALK, {"seconds": 12})
        event = db.scalars(select(AgentEvent).where(AgentEvent.save_id == save_id)).one()
        assert event.summary == "Read a voice note: Founders fellowship"
        assert event.evidence[0]["label"] == "Our copy of what's said"


@pytest.mark.integration
def test_a_voice_note_with_no_words_is_kept_and_says_so(
    sessions: sessionmaker[Session], fakes: FakeStorage
) -> None:
    FakeGateway.heard = ""
    with sessions() as db:
        reading = _read(db, _media_save(db, "voice", "audio/ogg", caption="Grandma's advice"))
        assert (reading.model, reading.title) == ("none", "Grandma's advice")
        assert (
            reading.what
            == "A voice note, kept with your words. Homing couldn't hear any words in it."
        )
        assert _purposes() == ["transcribe"]


@pytest.mark.integration
def test_a_video_that_talks_is_read_from_its_words_not_watched(
    sessions: sessionmaker[Session], fakes: FakeStorage
) -> None:
    with sessions() as db:
        _read(db, _media_save(db, "video", "video/mp4"))
        assert _purposes() == ["transcribe", "read.text"]  # no read.video: cheaper, checkable


@pytest.mark.integration
def test_a_quiet_video_is_watched_and_keeps_only_facts_said_or_written(
    sessions: sessionmaker[Session], fakes: FakeStorage
) -> None:
    FakeGateway.heard = "Apply before Friday."
    with sessions() as db:
        save_id = _media_save(db, "video", "video/mp4", caption="Fellowship reel")
        reading = _read(db, save_id)
        watch = FakeGateway.calls[1]
        assert watch["purpose"] == "read.video"
        assert watch["attachments"] == [VideoLink("https://signed.example/v.mp4", "sha-video")]
        assert watch["inputs"]["transcript"] == "Apply before Friday."
        assert reading.prompt_version == "read_video.v1"
        # "before Friday" was said; "Closes 9 December" was only on screen, so it's dropped.
        assert [d["text"] for d in reading.key_facts["dates"]] == ["before Friday"]


@pytest.mark.integration
def test_a_quiet_video_on_this_machine_is_kept_not_guessed(
    sessions: sessionmaker[Session], fakes: FakeStorage
) -> None:
    fakes.url = None  # the local disk: nothing outside can fetch it
    FakeGateway.heard = ""
    with sessions() as db:
        reading = _read(db, _media_save(db, "video", "video/mp4"))
        assert reading.model == "none" and reading.title == "A video you saved"
        assert "read.video" not in _purposes()


@pytest.mark.integration
def test_a_word_document_is_read_from_its_text(
    sessions: sessionmaker[Session], fakes: FakeStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(what_is_it, "office_text", lambda data: "Grant guide. Closes 30 November.")
    with sessions() as db:
        save_id = _media_save(db, "file", "application/vnd.openxmlformats-officedocument")
        _read(db, save_id)
        assert _purposes() == ["read.text"]
        copy = db.scalars(select(Snapshot).where(Snapshot.save_id == save_id)).one()
        assert (copy.kind, copy.text) == ("doc_text", "Grant guide. Closes 30 November.")


@pytest.mark.integration
def test_a_secret_heard_in_a_voice_note_makes_it_private(
    sessions: sessionmaker[Session], fakes: FakeStorage
) -> None:
    FakeGateway.heard = "my password is hunter2 for the bank app"
    with sessions() as db:
        save_id = _media_save(db, "voice", "audio/ogg")
        reading = _read(db, save_id)
        assert reading.title == "Kept private"
        assert db.get(Save, save_id).visibility == "private"  # type: ignore[union-attr]
        assert db.scalars(select(Snapshot).where(Snapshot.save_id == save_id)).first() is None
        assert _purposes() == ["transcribe"]  # never read by a model
