# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

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

from app.services.docparse import ocr

logger = logging.getLogger(__name__)

# A page with fewer than this many words almost certainly has no text layer.
# Cover pages legitimately carry a handful of words, so this is deliberately low;
# the decision is made across the whole document, not per page.
_MIN_WORDS_PER_PAGE = 5


#: Carried on every OCR'd document, and shown to the patient.
#:
#: ⚠️ It is not boilerplate. Measured on the test fixture: at a 300-dpi render
#: the A/G ratio `1.8` came back as `18` — a decimal point lost, AT CONFIDENCE
#: 85. Rendering at 400 dpi fixed that case; nothing promises the next one.
#: Every row from a document carrying this is staged UNTICKED.
_OCR_CAVEAT = (
    "The text in this document was recognised from an image, so the values "
    "may be misread — a decimal point in particular. Check each row against "
    "the original before importing it."
)


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
        return (self.extraction_method in ("pdf_text", "plain_text", "ocr")
                and self.word_count > 0)


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
        doc = _extract_pdf(content)
        # A scan has no text layer. `needs_ocr` has been detected here since
        # this module was written and NOTHING could act on it, so a scanned PDF
        # failed exactly like a photo did (§3ar — a state nothing consumes).
        if doc.extraction_method == "needs_ocr":
            return _extract_scanned_pdf(content, fallback=doc)
        return doc

    # A PHOTO of a report. Operator, 2026-10-16: *"We need to expand acceptable
    # uploads."* Refusing was better than the empty table it replaced and is
    # still the wrong answer — photographing a report is what a patient does.
    image = ocr.open_image(content)
    if image is not None:
        return _extract_image(image)

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


#: A US Letter page in PDF points — the space every threshold downstream was
#: measured in.
_PAGE_WIDTH_PT = 612.0


def _words_to_page(words: list[dict], size, number: int = 1) -> Page:
    """OCR words -> a `Page` the layout parser can read, IN PDF POINTS.

    ⚠️ **The first version left the boxes in pixels**, on the reasoning that
    the parser only compares positions to each other. That is false, and the
    cost was a clinical misidentification rather than a wonky layout.

    §3ab records the parser's real thresholds as absolute distances: the
    name/value column boundary at `x_mid 162.0`, and `_reclaim_name_overflow`
    separating "a gap INSIDE a name (2.0 pt here)" from "the gap to the real
    value (29.0 pt)". At 400 dpi one point is about 5.5 pixels, so a 2 pt word
    space becomes ~11 px and every one of those figures is meaningless.

    Measured on the test fixture, pixels vs points, same photo:

        pixels   raw='PHOS'      -> 'Phosphorus'            637.0 U/L
        points   raw='ALK PHOS'  -> 'Alkaline Phosphatase'  637.0 U/L

    The first is alkaline phosphatase — a liver enzyme, U/L, reference 46-116 —
    recorded as PHOSPHORUS, a mineral a dialysis patient is managed on and for
    whom 637 is impossible. The words were recognised correctly both times;
    only the grouping differed, because "ALK" and "PHOS" fell either side of a
    gap the parser was measuring in the wrong unit.

    Scaling by WIDTH and keeping the aspect ratio: a photo is rarely exactly
    letter-shaped, and stretching height to match would move every row.
    """
    pixel_width = float(size[0]) or 1.0
    scale = _PAGE_WIDTH_PT / pixel_width

    page = Page(number=number,
                width=_PAGE_WIDTH_PT,
                height=float(size[1]) * scale)
    for w in words:
        page.words.append(Word(
            text=w["text"],
            x0=w["x0"] * scale, x1=w["x1"] * scale,
            top=w["top"] * scale, bottom=w["bottom"] * scale,
        ))
    page.text = " ".join(w["text"] for w in words)
    return page


def _ocr_unavailable(why: str) -> Document:
    """Say the capability is missing rather than that the document is empty.

    §3aa: an error is not an empty state. "We could not read this" and "this
    contained nothing" are opposite claims about a patient's report.
    """
    return Document(
        extraction_method="unreadable",
        error_detail=(
            f"This looks like a photo or a scan, and text recognition is not "
            f"available on the server ({why}). Nothing was read."
        ),
    )


def _extract_image(image) -> Document:
    """A photograph of a document."""
    ok, why = ocr.available()
    if not ok:
        return _ocr_unavailable(why or "unknown reason")

    try:
        words, size = ocr.words_from_image(image)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR failed on image: %s", exc, exc_info=True)
        return Document(
            extraction_method="unreadable",
            error_detail=f"The photo could not be read ({type(exc).__name__}).",
        )

    if not words:
        return Document(
            extraction_method="unreadable",
            error_detail=(
                "No text could be recognised in this photo. A flat, sharp, "
                "well-lit shot of the whole page reads best."
            ),
        )

    doc = Document(pages=[_words_to_page(words, size)], extraction_method="ocr")
    doc.error_detail = _OCR_CAVEAT
    return doc


def _extract_scanned_pdf(content: bytes, fallback: Document) -> Document:
    """A PDF whose pages are images. Rendered, then read like a photograph."""
    ok, why = ocr.available()
    if not ok:
        return _ocr_unavailable(why or "unknown reason")

    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(content, dpi=ocr.MIN_DPI)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not render scanned PDF: %s", exc, exc_info=True)
        return fallback          # keep the original "needs OCR" explanation

    pages: list[Page] = []
    for index, image in enumerate(images, start=1):
        try:
            words, size = ocr.words_from_image(image)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR failed on page %s: %s", index, exc)
            continue
        if words:
            pages.append(_words_to_page(words, size, number=index))

    if not pages:
        return fallback

    doc = Document(pages=pages, extraction_method="ocr")
    doc.error_detail = _OCR_CAVEAT
    return doc


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
