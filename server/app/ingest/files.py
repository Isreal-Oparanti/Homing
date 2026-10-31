"""Files people save: images, flyers and PDFs (docs/04-ingestion.md · PDF, Images).

Types are sniffed from the bytes, never trusted from the name (approved storage rules).
PDFs with a text layer are read as text; scanned PDFs and images go to Muse Spark.
"""

import io
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
