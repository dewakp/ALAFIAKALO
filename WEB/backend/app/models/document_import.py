"""Staging for parsed clinical documents.

A parser is sometimes wrong, and a clinical table is the wrong place to find that
out. Everything read from a document lands here first, is shown to the patient
with its confidence and how it deduplicates against what they already have, and
only reaches `lab_results` / `medications` / `chronic_conditions` once they
accept it.

Modelled on `clinician_ingest_candidates` (candidate → dedup → provenance →
upsert), which solved the same problem for the physician directory.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

#: DocumentImport.status
STATUS_PARSED = "parsed"
STATUS_CONFIRMED = "confirmed"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"

#: DocumentImportItem.dedupe_status
DEDUPE_NEW = "new"
DEDUPE_DUPLICATE = "duplicate"    # same value already recorded — import is a no-op
DEDUPE_CONFLICT = "conflict"      # same test/date, different value — needs a human


class DocumentImport(Base):
    """One uploaded document and the outcome of reading it."""

    __tablename__ = "document_imports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    filename: Mapped[str | None] = mapped_column(String(255))
    #: sha256 of the bytes — re-uploading the same file returns the existing
    #: import instead of creating a second copy of the same readings.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    doc_type: Mapped[str | None] = mapped_column(String(40))
    doc_type_confidence: Mapped[float | None] = mapped_column(Float)
    classification_method: Mapped[str | None] = mapped_column(String(20))

    #: "pdf_text" | "plain_text" | "needs_ocr" | "unreadable"
    extraction_method: Mapped[str | None] = mapped_column(String(20))
    #: "columns" | "matrix" | "none"
    layout_kind: Mapped[str | None] = mapped_column(String(20))
    page_count: Mapped[int | None] = mapped_column(Integer)
    parse_confidence: Mapped[float | None] = mapped_column(Float)

    # Report-level context, as read from the document.
    patient_name: Mapped[str | None] = mapped_column(String(255))
    report_date: Mapped[str | None] = mapped_column(String(20))
    lab_name: Mapped[str | None] = mapped_column(String(255))
    ordering_provider: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_PARSED, index=True)
    #: Why nothing was read. Never left empty on a failure — an empty item list
    #: and a failed parse must not look the same to the reader.
    error_detail: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[list | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items = relationship(
        "DocumentImportItem",
        back_populates="document_import",
        cascade="all, delete-orphan",
        order_by="DocumentImportItem.row_index",
    )


class DocumentImportItem(Base):
    """One staged row, addressed at the clinical table it would be written to."""

    __tablename__ = "document_import_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    import_id: Mapped[int] = mapped_column(
        ForeignKey("document_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: "lab_results" | "medications" | "chronic_conditions"
    target_table: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The row as it would be inserted — column names match the target model.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    #: What the document called it, kept so a mis-normalization is visible.
    source_label: Mapped[str | None] = mapped_column(String(255))
    canonical_name: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float | None] = mapped_column(Float)

    dedupe_status: Mapped[str] = mapped_column(String(20), nullable=False, default=DEDUPE_NEW)
    existing_row_id: Mapped[int | None] = mapped_column(Integer)

    #: Reviewer's decision. Duplicates default to unaccepted so confirming an
    #: import never silently writes a second copy of a reading.
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    imported_row_id: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    document_import = relationship("DocumentImport", back_populates="items")
