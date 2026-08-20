"""Stage a parsed document, then import what the patient accepts.

Two steps on purpose. `stage` writes only to `document_imports` /
`document_import_items`; `confirm` is the only thing that touches a clinical
table, and it writes exactly the rows the reviewer kept.

Canon §3aa applies throughout:

* conditions go to `chronic_conditions` — never `health_conditions`, which has
  no writer and would make every imported diagnosis invisible;
* a medication read off a document is a *prescription*, so it goes to
  `medications`, not `medication_dose_logs`, which records what was actually
  taken;
* duplicate checks read through `app/services/clinical_sources.py`, because
  querying those models directly here would both miss half the data and fail the
  guard in `tests/test_clinical_sources.py`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chronic_conditions import (
    ChronicCondition,
    ConditionCategory,
    ConditionSeverity,
)
from app.models.document_import import (
    DEDUPE_CONFLICT,
    DEDUPE_DUPLICATE,
    DEDUPE_NEW,
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PARSED,
    STATUS_REJECTED,
    DocumentImport,
    DocumentImportItem,
)
from app.models.labs import LabResult
from app.models.medications import Medication
from app.services import clinical_sources as sources
from app.services.docparse import classify as doc_types
from app.services.docparse.pipeline import ParseResult
from app.services.docparse.records_clinical import (
    records_from_condition_table,
    records_from_medication_table,
)

logger = logging.getLogger(__name__)

TABLE_LABS = "lab_results"
TABLE_MEDICATIONS = "medications"
TABLE_CONDITIONS = "chronic_conditions"

#: Which clinical table each document type feeds.
TARGET_FOR_DOC_TYPE = {
    doc_types.LAB_REPORT: TABLE_LABS,
    doc_types.DIALYSIS_FLOWSHEET: TABLE_LABS,
    doc_types.MEDICATION_LIST: TABLE_MEDICATIONS,
    doc_types.DISCHARGE_SUMMARY: TABLE_CONDITIONS,
}

#: Marks the provenance of anything this pipeline writes, so an imported row can
#: always be told apart from one the patient entered by hand.
IMPORT_SOURCE = "document_import"


# ── Staging ──────────────────────────────────────────────────────────────────

async def find_existing_import(
    db: AsyncSession, user_id: int, content_hash: str
) -> DocumentImport | None:
    """The same file staged before — re-uploading must not duplicate readings."""
    result = await db.execute(
        select(DocumentImport)
        .where(
            DocumentImport.user_id == user_id,
            DocumentImport.content_hash == content_hash,
            DocumentImport.status != STATUS_REJECTED,
        )
        .order_by(DocumentImport.id.desc())
    )
    return result.scalars().first()


async def stage(db: AsyncSession, user_id: int, parsed: ParseResult) -> DocumentImport:
    """Persist a parse result for review. Writes no clinical rows."""
    meta = parsed.metadata
    record = DocumentImport(
        user_id=user_id,
        filename=parsed.filename,
        content_hash=parsed.content_hash,
        doc_type=parsed.doc_type,
        doc_type_confidence=parsed.doc_type_confidence,
        classification_method=parsed.classification_method,
        extraction_method=parsed.extraction_method,
        layout_kind=parsed.layout_kind,
        page_count=parsed.page_count,
        parse_confidence=parsed.confidence,
        patient_name=meta.patient_name,
        report_date=str(meta.report_date) if meta.report_date else None,
        lab_name=meta.lab_name,
        ordering_provider=meta.ordering_provider,
        status=STATUS_PARSED if parsed.ok else STATUS_FAILED,
        error_detail=parsed.error_detail,
        notes=list(parsed.notes) or None,
    )
    db.add(record)
    await db.flush()

    target = TARGET_FOR_DOC_TYPE.get(parsed.doc_type)
    if target == TABLE_LABS:
        items = await _stage_labs(db, user_id, parsed)
    elif target == TABLE_MEDICATIONS:
        items = await _stage_medications(db, user_id, parsed)
    elif target == TABLE_CONDITIONS:
        items = await _stage_conditions(db, user_id, parsed)
    else:
        items = []
        if parsed.ok:
            record.error_detail = (
                f"This looks like a {parsed.doc_type.replace('_', ' ')}, which can be "
                "read but cannot be imported yet. The values below are shown for "
                "reference only."
            )

    for item in items:
        item.import_id = record.id
        db.add(item)

    await db.flush()
    return record


async def _stage_labs(db: AsyncSession, user_id: int, parsed: ParseResult) -> list[DocumentImportItem]:
    meta = parsed.metadata
    existing = await _existing_labs(db, user_id)
    items: list[DocumentImportItem] = []

    for index, record in enumerate(parsed.records):
        test_date = record.test_date or meta.report_date
        payload: dict[str, Any] = {
            "test_date": str(test_date) if test_date else None,
            "test_name": record.test_name,
            "category": record.category,
            "value": record.value,
            "value_string": record.value_text,
            "unit": record.unit,
            "reference_range_low": record.reference_low,
            "reference_range_high": record.reference_high,
            "is_abnormal": record.is_abnormal,
            "status": (record.status or "final").lower(),
            "ordering_provider": meta.ordering_provider,
            "performing_lab": meta.lab_name,
            "notes": "; ".join(record.notes) or None,
        }

        dedupe, existing_id = DEDUPE_NEW, None
        key = (str(test_date), record.test_name.lower())
        prior = existing.get(key)
        if prior is not None:
            prior_id, prior_value = prior
            existing_id = prior_id
            dedupe = DEDUPE_DUPLICATE if prior_value == record.value else DEDUPE_CONFLICT

        items.append(DocumentImportItem(
            target_table=TABLE_LABS,
            row_index=index,
            payload=payload,
            source_label=record.raw_name,
            canonical_name=record.test_name,
            confidence=record.confidence,
            dedupe_status=dedupe,
            existing_row_id=existing_id,
            # A duplicate is unticked by default: confirming an import must not
            # quietly write a second copy of a reading already on file.
            accepted=(dedupe != DEDUPE_DUPLICATE) and bool(test_date),
            error=None if test_date else "No date could be determined for this result.",
        ))
    return items


async def _existing_labs(db: AsyncSession, user_id: int) -> dict[tuple, tuple[int, float | None]]:
    """(date, lowercased test name) -> (row id, value) for this user's labs.

    `lab_results` is not one of the split-table models, so reading it directly
    is correct here.
    """
    result = await db.execute(
        select(LabResult.id, LabResult.test_date, LabResult.test_name, LabResult.value)
        .where(LabResult.user_id == user_id)
    )
    return {
        (str(row.test_date), (row.test_name or "").lower()): (row.id, row.value)
        for row in result
    }


async def _stage_medications(db: AsyncSession, user_id: int, parsed: ParseResult) -> list[DocumentImportItem]:
    # Prescriptions already on file, read through the canonical source.
    prescribed = await sources.medications_prescribed(db, user_id)
    known = {(m.name or "").lower() for m in prescribed}

    items: list[DocumentImportItem] = []
    records = []
    for table in parsed.tables:
        records.extend(records_from_medication_table(table))

    for index, record in enumerate(records):
        payload = {
            "name": record.name,
            "dosage": record.dosage,
            "dosage_unit": record.dosage_unit,
            "frequency": record.frequency,
            "route": record.route,
            "start_date": str(record.start_date) if record.start_date else None,
            "prescribing_doctor": record.prescribing_doctor or parsed.metadata.ordering_provider,
            "is_active": record.is_active,
            "notes": record.notes,
            "source": IMPORT_SOURCE,
        }
        duplicate = record.name.lower() in known
        items.append(DocumentImportItem(
            target_table=TABLE_MEDICATIONS,
            row_index=index,
            payload=payload,
            source_label=record.raw_name,
            canonical_name=record.name,
            confidence=record.confidence,
            dedupe_status=DEDUPE_DUPLICATE if duplicate else DEDUPE_NEW,
            accepted=not duplicate,
            error="; ".join(record.parse_notes) or None,
        ))
    return items


async def _stage_conditions(db: AsyncSession, user_id: int, parsed: ParseResult) -> list[DocumentImportItem]:
    current = await sources.conditions(db, user_id)
    known = {(c.name or "").lower() for c in current}

    items: list[DocumentImportItem] = []
    records = []
    for table in parsed.tables:
        records.extend(records_from_condition_table(table))

    for index, record in enumerate(records):
        payload = {
            "condition_name": record.condition_name,
            "category": record.category,
            "severity": record.severity,
            "icd10_code": record.icd10_code,
            "diagnosis_date": str(record.diagnosis_date) if record.diagnosis_date else None,
            "is_active": record.is_active,
            "stage": record.stage,
        }
        duplicate = record.condition_name.lower() in known
        items.append(DocumentImportItem(
            target_table=TABLE_CONDITIONS,
            row_index=index,
            payload=payload,
            source_label=record.raw_name,
            canonical_name=record.condition_name,
            confidence=record.confidence,
            dedupe_status=DEDUPE_DUPLICATE if duplicate else DEDUPE_NEW,
            accepted=not duplicate,
            error="; ".join(record.parse_notes) or None,
        ))
    return items


# ── Confirmation ─────────────────────────────────────────────────────────────

async def confirm(
    db: AsyncSession,
    user_id: int,
    record: DocumentImport,
    accepted_item_ids: list[int] | None = None,
) -> dict[str, int]:
    """Write the accepted rows into their clinical tables.

    `accepted_item_ids` overrides the staged decisions when the reviewer changed
    them. Returns a per-table count of what was written.
    """
    counts = {TABLE_LABS: 0, TABLE_MEDICATIONS: 0, TABLE_CONDITIONS: 0}

    for item in record.items:
        wanted = (
            item.id in accepted_item_ids
            if accepted_item_ids is not None
            else item.accepted
        )
        if not wanted or item.imported_row_id is not None:
            continue

        try:
            row = _build_row(user_id, item)
        except Exception as exc:  # noqa: BLE001 - one bad row must not sink the import
            logger.warning("Could not build %s row from item %s: %s", item.target_table, item.id, exc)
            item.error = f"Could not import this row: {exc}"
            continue

        if row is None:
            continue

        db.add(row)
        await db.flush()
        item.imported_row_id = row.id
        counts[item.target_table] = counts.get(item.target_table, 0) + 1

    record.status = STATUS_CONFIRMED
    record.confirmed_at = datetime.now(timezone.utc)
    await db.flush()
    return counts


def _build_row(user_id: int, item: DocumentImportItem):
    payload = dict(item.payload or {})

    if item.target_table == TABLE_LABS:
        return LabResult(
            user_id=user_id,
            test_date=_as_date(payload.get("test_date")),
            test_name=payload["test_name"],
            category=payload.get("category"),
            value=payload.get("value"),
            value_string=payload.get("value_string"),
            unit=payload.get("unit"),
            reference_range_low=payload.get("reference_range_low"),
            reference_range_high=payload.get("reference_range_high"),
            is_abnormal=payload.get("is_abnormal"),
            status=payload.get("status") or "final",
            ordering_provider=payload.get("ordering_provider"),
            performing_lab=payload.get("performing_lab"),
            notes=payload.get("notes"),
        )

    if item.target_table == TABLE_MEDICATIONS:
        # Prescriptions, not dose logs — canon §3aa.
        return Medication(
            user_id=user_id,
            name=payload["name"],
            dosage=payload.get("dosage"),
            dosage_unit=payload.get("dosage_unit"),
            frequency=payload.get("frequency"),
            route=payload.get("route"),
            start_date=_as_date(payload.get("start_date")),
            prescribing_doctor=payload.get("prescribing_doctor"),
            is_active=bool(payload.get("is_active", True)),
            notes=payload.get("notes"),
            source=payload.get("source") or IMPORT_SOURCE,
        )

    if item.target_table == TABLE_CONDITIONS:
        # chronic_conditions, never health_conditions — canon §3aa.
        return ChronicCondition(
            user_id=user_id,
            condition_name=payload["condition_name"],
            category=ConditionCategory(payload.get("category") or "other"),
            severity=ConditionSeverity(payload.get("severity") or "moderate"),
            icd10_code=payload.get("icd10_code"),
            diagnosis_date=_as_datetime(payload.get("diagnosis_date")),
            is_active=bool(payload.get("is_active", True)),
            stage=payload.get("stage"),
        )

    return None


def _as_date(value):
    from datetime import date as _date

    if not value:
        return None
    if isinstance(value, _date):
        return value
    return _date.fromisoformat(str(value)[:10])


def _as_datetime(value):
    parsed = _as_date(value)
    return datetime(parsed.year, parsed.month, parsed.day) if parsed else None


async def reject(db: AsyncSession, record: DocumentImport) -> None:
    record.status = STATUS_REJECTED
    await db.flush()
