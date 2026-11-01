import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import is_it_true, what_is_it, whats_it_for
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.models import AgentEvent, Snapshot
from app.db.session import get_db
from app.ingest.files import UnsupportedFile, pdf_text, sniff
from app.ingest.gather import Gathered, SnapshotIn
from app.jobs.handlers import HANDLERS
from app.jobs.runner import Runner
from app.llm.search import SearchResult, find_site, own_site
from app.main import create_app
from app.schemas.agents import (
    FileReading,
    KeyFacts,
    ListItem,
    Placement,
    ProposedCheck,
    ProposedFinding,
    ProposedRule,
    Reading,
)
from app.storage import LocalStorage, get_storage

ALICE = CurrentUser(id="u-alice", email="alice@example.com")
HEADERS = {
    "X-Homing-Proxy-Secret": "s",
    "X-Homing-User-Id": ALICE.id,
    "X-Homing-User-Email": ALICE.email,
}
THREAD_TEXT = "1. TripleFunds https://triple-funds.com/\n2. New Africa Fund (no link)"


def _png(colour: str = "white") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), colour).save(out, format="PNG")
    return out.getvalue()


def _pdf_with_text(words: str) -> bytes:
    """A one-page PDF with a real text layer."""
    stream = f"BT /F1 10 Tf 40 760 Td ({words}) Tj ET".encode()
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj".encode() + body + b"endobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n".encode()
    return out + b"%%EOF"


class FakeModels:
    calls: list[str] = []
    file_text = THREAD_TEXT

    def __init__(self, db: Session):
        pass

    def run(self, purpose: str, **kwargs: Any) -> Any:
        FakeModels.calls.append(purpose)
        if purpose == "read.file":
            return FileReading(
                title="Funding thread screenshots",
                what="Screenshots listing funding opportunities.",
                key_facts=KeyFacts(),
                is_checkable=True,
                is_opportunity=True,
                items=[
                    ListItem(name="TripleFunds", url="https://triple-funds.com/"),
                    ListItem(name="New Africa Fund"),
                ],
                text=FakeModels.file_text,
            )
        if purpose == "read.text":
            return Reading(
                title="A PDF",
                what="A PDF.",
                key_facts=KeyFacts(),
                is_checkable=False,
                is_opportunity=False,
            )
        if purpose == "check.compare":
            return ProposedCheck(
                is_same_opportunity=True,
                findings=[
                    ProposedFinding(
                        point="It's for African founders.",
                        quote="Grants for African founders",
                        kind="left_out",
                    )
                ],
                # A who-can-apply rule makes the item an opportunity; only the person can judge
                # it, so it's listed to check rather than blocking the verdict.
                rules=[
                    ProposedRule(
                        rule="other",
                        strength="required",
                        quote="Grants for African founders",
                        plain="For African founders",
                        question="Are you an African founder?",
                    )
                ],
            )
        if purpose == "place.assign":
            return Placement(new_thread_title="Funding and opportunities", reason="Funding.")
        raise AssertionError(purpose)


@pytest.fixture
def client(sessions: sessionmaker[Session], tmp_path: Path) -> TestClient:
    def override_db():  # type: ignore[no-untyped-def]
        with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(proxy_secret="s")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    return TestClient(app)


@pytest.fixture(autouse=True)
def fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    FakeModels.calls = []
    FakeModels.file_text = THREAD_TEXT
    for agent in (what_is_it, is_it_true, whats_it_for):
        monkeypatch.setattr(agent, "gateway_factory", FakeModels)
    monkeypatch.setattr(what_is_it, "storage_factory", lambda: LocalStorage(tmp_path))
    monkeypatch.setattr(what_is_it, "_gather", lambda save: Gathered())
    page = "TripleFunds. Grants for African founders building for Africa."
    monkeypatch.setattr(
        is_it_true, "_fetch_source", lambda url, hint, fetcher: SnapshotIn("page_text", page, url)
    )


def _upload(client: TestClient, files: list[tuple[str, bytes]], note: str | None = None) -> Any:
    return client.post(
        "/api/v1/saves/file",
        files=[("files", (name, data)) for name, data in files],
        data={"note": note} if note else {},
        headers=HEADERS,
    )


def _run(sessions: sessionmaker[Session]) -> None:
    runner = Runner(sessions, HANDLERS, threads=1, worker_id="t")
    while runner.run_once():
        pass


# Pure code ---------------------------------------------------------------------------------


def test_types_are_sniffed_from_the_bytes_not_the_name() -> None:
    assert sniff(_png()) == "image/png"
    assert sniff(_pdf_with_text("hello")) == "application/pdf"
    with pytest.raises(UnsupportedFile):
        sniff(b"PK\x03\x04 a zip pretending to be a png")


def test_a_pdf_with_little_text_counts_as_scanned() -> None:
    assert pdf_text(_pdf_with_text("Hello")).scanned
    long = pdf_text(_pdf_with_text("Grant applications are open to founders. " * 8))
    assert not long.scanned and "Grant applications" in long.text


# Through the API -----------------------------------------------------------------------------


@pytest.mark.integration
def test_screenshots_of_a_list_are_checked_item_by_item(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    res = _upload(client, [("one.png", _png()), ("two.png", _png("black"))])
    assert res.status_code == 202 and res.json()["kind"] == "image"
    save_id = res.json()["id"]
    _run(sessions)

    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
    assert card["what"]["title"] == "Funding thread screenshots"
    assert [c["kind"] for c in card["copies"]] == ["ocr_text"] or "ocr_text" in [
        c["kind"] for c in card["copies"]
    ]
    items = card["true"]["items"]
    assert [i["name"] for i in items] == ["TripleFunds", "New Africa Fund"]
    assert items[0]["status"] == "done" and items[0]["verdict"] == "fits_you"
    assert items[0]["rules"][0]["result"] == "unknown"  # shown under "Check yourself"
    assert items[0]["findings"][0]["quote"] == "Grants for African founders"
    assert items[1]["problem"] == "We couldn't find its website."  # no link, search off in tests
    assert FakeModels.calls.count("read.file") == 1  # both screenshots in one reading
    assert card["save"]["files"] == 2
    shown = client.get(f"/api/v1/saves/{save_id}/files/1", headers=HEADERS)
    assert shown.status_code == 200 and shown.headers["content-type"] == "image/png"
    bob = {**HEADERS, "X-Homing-User-Id": "u-bob", "X-Homing-User-Email": "bob@example.com"}
    assert client.get(f"/api/v1/saves/{save_id}/files/1", headers=bob).status_code == 404

    with sessions() as db:
        actions = db.scalars(select(AgentEvent.action).where(AgentEvent.save_id == save_id)).all()
    assert actions.count("checked_item") == 2 and "checking_list" in actions


@pytest.mark.integration
def test_a_screenshot_that_shows_a_secret_is_kept_private(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    FakeModels.file_text = "Your OTP code is 482913. Do not share it."
    save_id = _upload(client, [("otp.png", _png())]).json()["id"]
    _run(sessions)
    card = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()
    assert card["save"]["visibility"] == "private"
    assert card["copies"] == []  # the words aren't kept
    assert "check.compare" not in FakeModels.calls


@pytest.mark.integration
def test_a_pdf_with_text_is_read_as_text_not_as_an_image(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    pdf = _pdf_with_text("Grant applications are open to founders. " * 8)
    save_id = _upload(client, [("call.pdf", pdf)]).json()["id"]
    _run(sessions)
    with sessions() as db:
        kinds = db.scalars(select(Snapshot.kind).where(Snapshot.save_id == save_id)).all()
    assert "pdf_text" in kinds
    assert "read.text" in FakeModels.calls and "read.file" not in FakeModels.calls


@pytest.mark.integration
def test_the_same_file_twice_is_stored_once(client: TestClient, tmp_path: Path) -> None:
    png = _png()
    _upload(client, [("a.png", png)])
    _upload(client, [("b.png", png)])
    assert len(list(tmp_path.rglob("*.png"))) == 1


@pytest.mark.integration
def test_files_we_cant_read_are_refused(client: TestClient) -> None:
    assert _upload(client, [("x.png", b"not really an image")]).status_code == 415
    pdf = _pdf_with_text("hello")
    assert _upload(client, [("a.pdf", pdf), ("b.png", _png())]).status_code == 422


class FakeSearch:
    def __init__(self, results: list[SearchResult]):
        self.results = results
        self.queries: list[str] = []

    def search(self, query: str, *, num: int = 8) -> list[SearchResult]:
        self.queries.append(query)
        return self.results


def test_an_organisations_own_site_is_found_from_search_results() -> None:
    results = [
        SearchResult(
            "https://ng.linkedin.com/company/microtraction", "Microtraction | LinkedIn", ""
        ),
        SearchResult("https://www.crunchbase.com/organization/microtraction", "Microtraction", ""),
        SearchResult("https://www.microtraction.com/press", "Press - Microtraction", ""),
    ]
    assert own_site(results, "Microtraction") == "https://www.microtraction.com/press"
    assert find_site(FakeSearch(results), "Microtraction") == "https://www.microtraction.com/"


def test_a_renamed_organisation_is_found_by_its_page_title() -> None:
    results = [SearchResult("https://vkav.vc/", "Verod-Kepple Africa Ventures", "")]
    assert find_site(FakeSearch(results), "Kepple Africa Ventures") == "https://vkav.vc/"


def test_no_match_means_no_site() -> None:
    results = [SearchResult("https://example.com/", "Something else", "")]
    assert find_site(FakeSearch(results), "TLCOM") is None


@pytest.mark.integration
def test_a_list_item_without_a_link_is_found_by_search(
    client: TestClient, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    search = FakeSearch(
        [SearchResult("https://www.newafricafund.org/aifgrants", "New Africa Fund", "")]
    )
    monkeypatch.setattr(is_it_true, "search_factory", lambda: search)
    save_id = _upload(client, [("thread.png", _png())]).json()["id"]
    _run(sessions)
    items = client.get(f"/api/v1/saves/{save_id}", headers=HEADERS).json()["true"]["items"]
    assert items[1]["found_by"] == "search"
    assert items[1]["official_url"] == "https://www.newafricafund.org/"
    assert items[1]["status"] == "done" and items[1]["verdict"] == "fits_you"
    assert search.queries == ["New Africa Fund"]
