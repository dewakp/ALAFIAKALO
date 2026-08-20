"""The parse pipeline — bytes in, reviewable clinical records out.

Ties the layers together and, importantly, decides *nothing* about the database.
It returns what the document says and how confident that reading is; staging and
import are separate steps so a human can look before anything is written.

Layout is tried in the order that fails loudest:

  1. labelled-column table — the common lab report
  2. trend matrix          — flowsheet / patient-profile grids
  3. freeform text         — neither shape found

A document that yields nothing carries `error_detail` saying why. It never comes
back as an empty success, because an empty table and a failed parse look
identical to a reader and mean opposite things.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date

from . import classify as classify_mod
from . import layout, layout_matrix
from .extract import Document, extract
from .metadata import ReportMetadata, extract_metadata, redact
from .normalize import LabRecord, records_from_matrix, records_from_table

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    content_hash: str
    filename: str | None
    doc_type: str
    doc_type_confidence: float
    classification_method: str
    extraction_method: str
    layout_kind: str                       # "columns" | "matrix" | "none"
    page_count: int
    metadata: ReportMetadata = field(default_factory=ReportMetadata)
    records: list[LabRecord] = field(default_factory=list)
    #: The reconstructed column tables, kept so the medication and condition
    #: mappers can read the same geometry with different column meanings.
    #: In-memory only — never persisted.
    tables: list[layout.Table] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error_detail: str | None = None
    raw_text: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.records)

    @property
    def confidence(self) -> float:
        """Mean record confidence, tempered by how sure we are of the type."""
        if not self.records:
            return 0.0
        mean = sum(r.confidence for r in self.records) / len(self.records)
        return round(mean * (0.6 + 0.4 * self.doc_type_confidence), 2)

    @property
    def date_range(self) -> tuple[date | None, date | None]:
        dates = sorted(r.test_date for r in self.records if r.test_date)
        return (dates[0], dates[-1]) if dates else (None, None)


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


async def parse(
    content: bytes,
    filename: str | None = None,
    content_type: str | None = None,
    *,
    use_model: bool = True,
) -> ParseResult:
    """Parse a clinical document. Never raises for bad input."""
    digest = content_hash(content)
    document = extract(content, filename, content_type)

    result = ParseResult(
        content_hash=digest,
        filename=filename,
        doc_type=classify_mod.UNKNOWN,
        doc_type_confidence=0.0,
        classification_method="none",
        extraction_method=document.extraction_method,
        layout_kind="none",
        page_count=len(document.pages),
        raw_text=document.text[:4000],
    )

    if not document.usable:
        result.error_detail = document.error_detail or "The document could not be read."
        return result

    result.metadata = extract_metadata(document)
    result.tables = layout.parse_document(document)
    records, layout_kind = _read_records(document, result.metadata, result.tables)
    result.records = records
    result.layout_kind = layout_kind

    classification = classify_mod.classify(
        document.text,
        has_lab_table=layout_kind == "columns",
        has_trend_matrix=layout_kind == "matrix",
    )
    if use_model:
        # Redact before the excerpt leaves this process — the model is local,
        # but prompts get logged and a log is a second copy.
        classification = await classify_mod.classify_with_model(
            redact(document.text[:2000], result.metadata), classification
        )

    result.doc_type = classification.doc_type
    result.doc_type_confidence = classification.confidence
    result.classification_method = classification.method
    result.notes.extend(classification.notes)
    result.notes.extend(result.metadata.notes)

    if not records:
        result.error_detail = (
            "No measurements could be read from this document. It may be a "
            "format that is not supported yet, or a scan without selectable text."
        )
    return result


def _read_records(
    document: Document, meta: ReportMetadata, tables: list[layout.Table]
) -> tuple[list[LabRecord], str]:
    """Try each layout shape; return the first that yields anything."""
    if tables:
        records: list[LabRecord] = []
        for table in tables:
            records.extend(records_from_table(table, report_date=meta.report_date))
        if records:
            return records, "columns"

    matrices = [m for m in (layout_matrix.parse_page(p) for p in document.pages) if m]
    if matrices:
        records = []
        for matrix in matrices:
            records.extend(records_from_matrix(matrix))
        if records:
            return records, "matrix"

    return [], "none"
