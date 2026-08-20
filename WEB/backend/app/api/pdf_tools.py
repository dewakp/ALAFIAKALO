"""PDF tools — document import and clinical report generation.

Upload is a two-step flow. `parse-document` reads a file and stages what it
found; nothing reaches a clinical table until `confirm`. A parser is sometimes
wrong, and `lab_results` is the wrong place to discover that.

Report generation goes through `app/services/docreport.py`: one spec renders as
both the text the clients preview and the PDF they download, so the two cannot
drift apart.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.chronic_conditions import TherapySession
from app.models.document_import import (
    STATUS_CONFIRMED,
    STATUS_PARSED,
    DocumentImport,
    DocumentImportItem,
)
from app.models.peritoneal_dialysis import PDSession
from app.models.user import User
from app.schemas.wellness import (
    ConfirmImportRequest,
    ConfirmImportResponse,
    DocumentImportDetail,
    DocumentImportSummary,
    FlowsheetPDFRequest,
    FlowsheetResponse,
    LabReportItem,
    LabReportParseResponse,
)
from app.services import document_import_service as importer
from app.services import docreport
from app.services.docparse import pipeline

logger = logging.getLogger(__name__)
router = APIRouter()

#: Uploads are read fully into memory to be parsed; keep that bounded.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


# ── Document import ──────────────────────────────────────────────────────────

async def _load_import(db: AsyncSession, user_id: int, import_id: int) -> DocumentImport:
    result = await db.execute(
        select(DocumentImport)
        .options(selectinload(DocumentImport.items))
        .where(DocumentImport.id == import_id, DocumentImport.user_id == user_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return record


def _item_view(item: DocumentImportItem) -> LabReportItem:
    payload = item.payload or {}
    low, high = payload.get("reference_range_low"), payload.get("reference_range_high")
    if low is not None and high is not None:
        reference = f"{low:g} – {high:g}"
    elif high is not None:
        reference = f"≤ {high:g}"
    elif low is not None:
        reference = f"≥ {low:g}"
    else:
        reference = None

    value = payload.get("value_string")
    if value is None and payload.get("value") is not None:
        raw = payload["value"]
        value = f"{raw:g}" if isinstance(raw, (int, float)) else str(raw)

    return LabReportItem(
        test_name=item.canonical_name or payload.get("test_name") or payload.get("name") or "—",
        value=value,
        unit=payload.get("unit") or payload.get("dosage_unit"),
        reference_range=reference,
        is_abnormal=payload.get("is_abnormal"),
        category=payload.get("category"),
        test_date=payload.get("test_date") or payload.get("start_date") or payload.get("diagnosis_date"),
        confidence=item.confidence,
        source_label=item.source_label,
        dedupe_status=item.dedupe_status,
        item_id=item.id,
        accepted=item.accepted,
        note=item.error,
    )


def _summary(record: DocumentImport) -> dict:
    items = record.items or []
    return {
        "id": record.id,
        "filename": record.filename,
        "doc_type": record.doc_type,
        "status": record.status,
        "page_count": record.page_count,
        "parse_confidence": record.parse_confidence,
        "report_date": record.report_date,
        "lab_name": record.lab_name,
        "item_count": len(items),
        "new_count": sum(1 for i in items if i.dedupe_status == "new"),
        "duplicate_count": sum(1 for i in items if i.dedupe_status == "duplicate"),
        "conflict_count": sum(1 for i in items if i.dedupe_status == "conflict"),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "error_detail": record.error_detail,
    }


@router.post("/parse-document", response_model=LabReportParseResponse)
@router.post("/parse-lab-report", response_model=LabReportParseResponse)
async def parse_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read a clinical document and stage what it contains for review.

    `parse-lab-report` is kept as an alias so existing clients keep working; the
    pipeline is source- and layout-agnostic, so the name is now only historical.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large (limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )

    parsed = await pipeline.parse(content, file.filename, file.content_type)

    # The same file twice is the same readings twice. Return what was staged
    # before rather than creating a second import.
    existing = await importer.find_existing_import(db, current_user.id, parsed.content_hash)
    if existing is not None:
        await db.refresh(existing, ["items"])
        return _response_for(existing, parsed, already_imported=True)

    record = await importer.stage(db, current_user.id, parsed)
    await db.commit()
    await db.refresh(record, ["items"])
    return _response_for(record, parsed)


def _response_for(
    record: DocumentImport, parsed: pipeline.ParseResult, already_imported: bool = False
) -> LabReportParseResponse:
    return LabReportParseResponse(
        patient_name=record.patient_name,
        report_date=record.report_date,
        lab_name=record.lab_name,
        ordering_physician=record.ordering_provider,
        items=[_item_view(i) for i in (record.items or [])],
        raw_text_preview=parsed.raw_text[:2000] or None,
        parsing_notes=list(record.notes or []),
        import_id=record.id,
        doc_type=record.doc_type,
        doc_type_confidence=record.doc_type_confidence,
        confidence=record.parse_confidence,
        target_table=importer.TARGET_FOR_DOC_TYPE.get(record.doc_type or ""),
        page_count=record.page_count,
        error=record.error_detail,
        already_imported=already_imported,
    )


@router.get("/imports", response_model=list[DocumentImportSummary])
async def list_imports(
    limit: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentImport)
        .options(selectinload(DocumentImport.items))
        .where(DocumentImport.user_id == current_user.id)
        .order_by(DocumentImport.id.desc())
        .limit(limit)
    )
    return [DocumentImportSummary(**_summary(r)) for r in result.scalars().all()]


@router.get("/imports/{import_id}", response_model=DocumentImportDetail)
async def get_import(
    import_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await _load_import(db, current_user.id, import_id)
    return DocumentImportDetail(
        **_summary(record),
        patient_name=record.patient_name,
        ordering_provider=record.ordering_provider,
        target_table=importer.TARGET_FOR_DOC_TYPE.get(record.doc_type or ""),
        layout_kind=record.layout_kind,
        extraction_method=record.extraction_method,
        notes=list(record.notes or []),
        items=[_item_view(i) for i in record.items],
    )


@router.post("/imports/{import_id}/confirm", response_model=ConfirmImportResponse)
async def confirm_import(
    import_id: int,
    request: ConfirmImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Write the accepted rows into their clinical tables."""
    record = await _load_import(db, current_user.id, import_id)
    if record.status == STATUS_CONFIRMED:
        raise HTTPException(status_code=409, detail="This import was already confirmed.")
    if record.status != STATUS_PARSED:
        raise HTTPException(
            status_code=409,
            detail=f"This import cannot be confirmed (status: {record.status}).",
        )

    counts = await importer.confirm(db, current_user.id, record, request.accepted_item_ids)
    await db.commit()

    total = sum(counts.values())
    written = ", ".join(f"{n} → {table}" for table, n in counts.items() if n)
    return ConfirmImportResponse(
        import_id=record.id,
        status=record.status,
        imported={k: v for k, v in counts.items() if v},
        total_imported=total,
        message=f"Imported {total} record(s): {written}" if total else "Nothing was imported.",
    )


@router.post("/imports/{import_id}/reject", response_model=ConfirmImportResponse)
async def reject_import(
    import_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await _load_import(db, current_user.id, import_id)
    await importer.reject(db, record)
    await db.commit()
    return ConfirmImportResponse(
        import_id=record.id, status=record.status,
        message="Import discarded. Nothing was written to your records.",
    )


# ── Flowsheet reports ────────────────────────────────────────────────────────

async def _flowsheet_spec(
    db: AsyncSession, user: User, request: FlowsheetPDFRequest
) -> tuple[docreport.ReportSpec, int]:
    """Build the report spec and report how many sessions it covers."""
    peritoneal = request.session_type == "peritoneal_dialysis"
    model = PDSession if peritoneal else TherapySession
    label = "Peritoneal Dialysis" if peritoneal else "Hemodialysis"

    # The two models name their date differently, and `scheduled_date` is a
    # DateTime *without* timezone — comparing it to an aware value makes asyncpg
    # raise, the endpoint 500s, and the page renders the empty-state copy on a
    # patient with hundreds of sessions. A naive datetime keeps that honest.
    date_column = model.session_date if peritoneal else model.scheduled_date

    query = select(model).where(model.user_id == user.id)
    if request.session_id is not None:
        query = query.where(model.id == request.session_id)
        window = None
    else:
        window = date.today() - timedelta(days=max(request.days, 1))
        cutoff = window if peritoneal else datetime(window.year, window.month, window.day)
        query = query.where(date_column >= cutoff)

    sessions = (await db.execute(query.order_by(date_column.desc()))).scalars().all()

    meta = [("Patient", user.full_name or user.email or "—")]
    if window is not None:
        meta.append(("Period", f"{window} to {date.today()} ({request.days} days)"))
    meta.append(("Sessions", str(len(sessions))))

    sections: list[docreport.Section] = []
    if not sessions:
        # Say the window was empty. A report with no rows and no explanation
        # reads as "no treatment", which is a different clinical claim.
        sections.append(docreport.TextSection(
            heading="No sessions found",
            body=(
                f"No {label.lower()} sessions are recorded"
                + (f" in the last {request.days} days." if window else " for this id.")
                + " This reflects what is on file, not necessarily what took place."
            ),
        ))
    elif peritoneal:
        sections.append(docreport.TableSection(
            heading="Sessions",
            columns=["Date", "Modality", "Pre wt", "Post wt", "Total UF", "Pre BP", "Post BP"],
            rows=[[
                str(s.session_date), (s.modality or "—").upper(),
                _fmt(s.pre_weight_kg, "kg"), _fmt(s.post_weight_kg, "kg"),
                _fmt(s.total_uf_ml, "mL"),
                _bp(s.pre_bp_systolic, s.pre_bp_diastolic),
                _bp(s.post_bp_systolic, s.post_bp_diastolic),
            ] for s in sessions],
            widths=[1.1, 1.0, 0.9, 0.9, 1.0, 1.0, 1.0],
        ))
        for session in sessions:
            if getattr(session, "exchanges", None):
                sections.append(docreport.TableSection(
                    heading=f"Exchanges — {session.session_date}",
                    columns=["#", "Solution", "Inflow", "Outflow", "UF", "Dwell", "Clarity"],
                    rows=[[
                        str(e.exchange_number), e.solution_type or "—",
                        _fmt(e.inflow_volume_ml, "mL"), _fmt(e.outflow_volume_ml, "mL"),
                        _fmt(e.uf_ml, "mL"), _fmt(e.dwell_time_minutes, "min"),
                        e.effluent_clarity or "—",
                    ] for e in session.exchanges],
                ))
    else:
        sections.append(docreport.TableSection(
            heading="Sessions",
            columns=["Date", "Type", "Duration", "Pre wt", "Post wt", "UF", "Pre BP", "Post BP"],
            rows=[[
                str(s.scheduled_date)[:10],
                _enum(s.therapy_type),
                _fmt(s.duration_minutes, "min"),
                _fmt(s.pre_dialysis_weight_kg, "kg"),
                _fmt(s.post_dialysis_weight_kg, "kg"),
                _fmt(s.fluid_removed_ml, "mL"),
                _bp(s.pre_standing_systolic_bp, s.pre_standing_diastolic_bp),
                _bp(s.post_standing_systolic_bp, s.post_standing_diastolic_bp),
            ] for s in sessions],
            widths=[1.1, 1.1, 0.9, 0.9, 0.9, 0.9, 1.0, 1.0],
        ))
        notes = [s for s in sessions if getattr(s, "notes", None)]
        if notes:
            sections.append(docreport.TextSection(
                heading="Notes",
                body="\n\n".join(f"{s.session_date}: {s.notes}" for s in notes),
            ))

    spec = docreport.ReportSpec(
        title=f"{label} Flowsheet",
        subtitle=user.full_name or None,
        meta=meta,
        sections=sections,
    )
    return spec, len(sessions)


def _fmt(value, unit: str) -> str:
    return f"{value:g} {unit}" if value is not None else "—"


def _enum(value) -> str:
    """Enum members print as `TherapyType.HEMODIALYSIS` otherwise."""
    if value is None:
        return "—"
    return str(getattr(value, "value", value)).replace("_", " ").title()


def _bp(systolic, diastolic) -> str:
    if systolic is None and diastolic is None:
        return "—"
    return f"{systolic or '—'}/{diastolic or '—'}"


@router.post("/generate-flowsheet", response_model=FlowsheetResponse)
async def generate_flowsheet(
    request: FlowsheetPDFRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Flowsheet as JSON — the text preview plus a link to the PDF.

    Takes `{session_type, days}`, which is what web, iOS and Android already
    send. The previous handler required a `session_id` and returned raw PDF
    bytes, so every client got a 422.
    """
    spec, count = await _flowsheet_spec(db, current_user, request)
    query = f"session_type={request.session_type}&days={request.days}"
    if request.session_id is not None:
        query += f"&session_id={request.session_id}"

    return FlowsheetResponse(
        title=spec.title,
        generated_at=spec.stamp,
        content=docreport.render_text(spec),
        session_count=count,
        pdf_url=f"/api/v1/pdf/reports/flowsheet.pdf?{query}",
    )


@router.get("/reports/flowsheet.pdf")
async def flowsheet_pdf(
    session_type: str = Query("hemodialysis"),
    days: int = Query(30, ge=1, le=365),
    session_id: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The same report as a real PDF."""
    request = FlowsheetPDFRequest(session_type=session_type, days=days, session_id=session_id)
    spec, _ = await _flowsheet_spec(db, current_user, request)

    try:
        payload = docreport.render_pdf(spec)
        media_type, suffix = "application/pdf", "pdf"
    except Exception:  # noqa: BLE001 - still hand back the report, as text
        logger.exception("PDF rendering failed; falling back to text")
        payload = docreport.render_text(spec).encode("utf-8")
        media_type, suffix = "text/plain", "txt"

    stamp = datetime.now().strftime("%Y%m%d")
    filename = f"flowsheet_{session_type}_{stamp}.{suffix}"
    return StreamingResponse(
        __import__("io").BytesIO(payload),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
