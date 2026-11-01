"""Files people save: images, flyers and PDFs (docs/04-ingestion.md · PDF, Images).

Types are sniffed from the bytes, never trusted from the name (approved storage rules).
PDFs with a text layer are read as text; scanned PDFs and images go to Muse Spark.
"""

import io
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
