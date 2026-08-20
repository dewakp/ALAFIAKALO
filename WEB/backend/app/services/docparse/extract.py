"""Layer 0 — get words and their geometry out of a document.

Nothing here knows what a lab report is. It answers one question: where is each
word on the page? Everything downstream is built on those coordinates rather
than on ``extract_text()``'s reflowed string, because reflow is what destroyed
the reference ranges in the DaVita corpus — a range printed to the left of a row
lands on the line *above* it in reading order.

A document with no text layer is a scan. That is reported as ``needs_ocr``, not
as zero results: canon "an error is not an empty state".
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# A page with fewer than this many words almost certainly has no text layer.
# Cover pages legitimately carry a handful of words, so this is deliberately low;
# the decision is made across the whole document, not per page.
_MIN_WORDS_PER_PAGE = 5


@dataclass
class Word:
    """One token with its bounding box, in PDF points from the top-left."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def x_mid(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Page:
    number: int          # 1-based
    width: float
    height: float
    words: list[Word] = field(default_factory=list)
    text: str = ""


@dataclass
class Document:
    pages: list[Page] = field(default_factory=list)
    #: "pdf_text" | "plain_text" | "needs_ocr" | "unreadable"
    extraction_method: str = "pdf_text"
    error_detail: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    @property
    def word_count(self) -> int:
        return sum(len(p.words) for p in self.pages)

    @property
    def usable(self) -> bool:
        return self.extraction_method in ("pdf_text", "plain_text") and self.word_count > 0


def extract(content: bytes, filename: str | None = None, content_type: str | None = None) -> Document:
    """Pull words + geometry out of `content`.

    Never raises for a malformed document — an unreadable file comes back as a
    Document carrying `error_detail`, so the caller can tell the user *why*
    nothing was found instead of showing an empty table.
    """
    name = (filename or "").lower()
    looks_pdf = (
        content[:5] == b"%PDF-"
        or content_type == "application/pdf"
        or name.endswith(".pdf")
    )

    if looks_pdf:
        return _extract_pdf(content)
    return _extract_plain(content)


def _extract_plain(content: bytes) -> Document:
    """Plain text: synthesise one page, no geometry.

    Layout analysis needs coordinates, so a text file always falls through to
    the freeform parser downstream. That is expected, not a failure.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")

    if not text.strip():
        return Document(extraction_method="unreadable", error_detail="The file is empty.")

    lines = text.splitlines()
    page = Page(number=1, width=0.0, height=0.0, text=text)
    # Give each token a synthetic box so downstream code can treat plain text
    # uniformly. Columns are meaningless here; only line grouping survives.
    for row, line in enumerate(lines):
        col = 0.0
        for token in line.split():
            page.words.append(
                Word(text=token, x0=col, x1=col + len(token), top=float(row), bottom=float(row) + 1)
            )
            col += len(token) + 1

    return Document(pages=[page], extraction_method="plain_text")


def _extract_pdf(content: bytes) -> Document:
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - dependency is pinned in requirements
        return Document(
            extraction_method="unreadable",
            error_detail=(
                "PDF support is not installed on the server (pdfplumber missing). "
                "The document could not be read."
            ),
        )

    doc = Document()
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                # use_text_flow=False keeps words in geometric order, which is
                # what column assignment depends on.
                raw_words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
                doc.pages.append(
                    Page(
                        number=index,
                        width=float(page.width),
                        height=float(page.height),
                        words=[
                            Word(
                                text=w["text"],
                                x0=float(w["x0"]),
                                x1=float(w["x1"]),
                                top=float(w["top"]),
                                bottom=float(w["bottom"]),
                            )
                            for w in raw_words
                        ],
                        text=page.extract_text() or "",
                    )
                )
    except Exception as exc:  # noqa: BLE001 - a corrupt upload must not 500
        logger.warning("PDF extraction failed: %s", exc)
        return Document(
            extraction_method="unreadable",
            error_detail=f"The PDF could not be opened ({type(exc).__name__}).",
        )

    if not doc.pages:
        return Document(extraction_method="unreadable", error_detail="The PDF has no pages.")

    if doc.word_count < _MIN_WORDS_PER_PAGE * len(doc.pages):
        doc.extraction_method = "needs_ocr"
        doc.error_detail = (
            f"This PDF has no selectable text ({doc.word_count} words across "
            f"{len(doc.pages)} page(s)) — it is most likely a scan or photo. "
            "Text recognition (OCR) is required to read it."
        )

    return doc
