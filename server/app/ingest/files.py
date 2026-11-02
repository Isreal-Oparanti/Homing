"""Files people save: images, flyers and PDFs (docs/04-ingestion.md · PDF, Images).

Types are sniffed from the bytes, never trusted from the name (approved storage rules).
PDFs with a text layer are read as text; scanned PDFs and images go to Muse Spark.
"""

import html
import io
import re
import zipfile
from dataclasses import dataclass

from PIL import Image
from pypdf import PdfReader

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 1600  # enough to read a flyer or a phone screenshot
SCANNED_CHARS_PER_PAGE = 200  # below this on average, a PDF is treated as scanned
MAX_PDF_PAGES = 30

EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "application/pdf": "pdf",
    # Only from WhatsApp imports so far (docs/04 · storage rules).
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "audio/ogg": "opus",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}
_OFFICE = {
    "word/document.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xl/workbook.xml": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt/presentation.xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
}


class UnsupportedFile(ValueError):
    """The message is shown to the person."""


def sniff(data: bytes) -> str:
    """The file's real type, from its first bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    raise UnsupportedFile("Homing can read images and PDFs for now.")


def sniff_any(data: bytes) -> str | None:
    """Like `sniff`, for everything a WhatsApp export can hold. None when unknown.
    Zips and contact cards are named so the importer can skip them on purpose."""
    try:
        return sniff(data)
    except UnsupportedFile:
        pass
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand.startswith(b"M4A"):
            return "audio/mp4"
        return "video/quicktime" if brand == b"qt  " else "video/mp4"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if data.startswith(b"PK\x03\x04"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile:
            return None
        return next((mime for part, mime in _OFFICE.items() if part in names), "application/zip")
    if data.lstrip()[:11].upper() == b"BEGIN:VCARD":
        return "text/vcard"
    return None


@dataclass(frozen=True)
class PdfText:
    text: str
    pages: int

    @property
    def scanned(self) -> bool:
        return self.pages == 0 or len(self.text) / self.pages < SCANNED_CHARS_PER_PAGE


def pdf_text(data: bytes) -> PdfText:
    """The PDF's own text layer, page by page. Empty for scanned or damaged PDFs, which then
    go to Muse Spark as they are."""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:MAX_PDF_PAGES]
        parts = [(page.extract_text() or "").strip() for page in pages]
    except Exception:  # pypdf raises many types on odd files; the model can still read them
        return PdfText("", 0)
    return PdfText("\n\n".join(p for p in parts if p), len(pages))


def image_for_model(data: bytes, mime: str) -> tuple[bytes, str]:
    """Shrink big images so the call stays fast; small ones go as they are."""
    img = Image.open(io.BytesIO(data))
    if max(img.size) <= MAX_IMAGE_SIDE and mime in ("image/png", "image/jpeg"):
        return data, mime
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=88)
    return out.getvalue(), "image/jpeg"


_OFFICE_PARTS = re.compile(r"^(word/document|ppt/slides/slide\d+|xl/sharedStrings)\.xml$")
_OFFICE_TEXT = re.compile(r"<(?:w|a):t(?:\s[^>]*)?>([^<]*)</(?:w|a):t>|<t(?:\s[^>]*)?>([^<]*)</t>")
_OFFICE_BREAK = re.compile(r"</(?:w|a):p>|</si>")


def office_text(data: bytes) -> str:
    """The words in a Word, PowerPoint or Excel file, paragraph by paragraph. Empty if none."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return ""
    with archive:
        parts = sorted(
            (n for n in archive.namelist() if _OFFICE_PARTS.match(n)),
            key=lambda n: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", n)],
        )
        out = []
        for name in parts:
            xml = archive.read(name).decode("utf-8", errors="replace")
            for paragraph in _OFFICE_BREAK.split(xml):
                words = "".join(a or b for a, b in _OFFICE_TEXT.findall(paragraph))
                if words.strip():
                    out.append(html.unescape(words.strip()))
    return "\n".join(out)
