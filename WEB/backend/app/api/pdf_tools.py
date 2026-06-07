"""PDF Tools — Lab Report Parsing & Flowsheet PDF Generation."""

import io
import re
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.chronic_conditions import TherapySession
from app.models.peritoneal_dialysis import PDSession
from app.schemas.wellness import LabReportParseResponse, FlowsheetPDFRequest

router = APIRouter()


def _parse_lab_text(text: str) -> dict:
    """Regex-based lab report parser — extracts test items, dates, provider info."""
    items = []
    parsing_notes = []
    panel_name = None
    lab_name = None
    doctor_name = None
    report_date = None

    lines = text.strip().split("\n")

    # Try to find date  (various formats)
    date_patterns = [
        r"(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\w+ \d{1,2},?\s*\d{4})",
    ]
    for pattern in date_patterns:
        m = re.search(pattern, text)
        if m:
            report_date = m.group(1)
            break

    # Try to find doctor / ordering provider
    doc_patterns = [
        r"(?:Dr\.?|Doctor|Physician|Ordering|Provider)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)",
        r"(?:Ordered by|Referred by)[:\s]+(.+?)(?:\n|$)",
    ]
    for pattern in doc_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            doctor_name = m.group(1).strip()
            break

    # Try to find lab name
    lab_patterns_hdr = [
        r"(?:Lab|Laboratory|Performed at|Facility)[:\s]+(.+?)(?:\n|$)",
    ]
    for pattern in lab_patterns_hdr:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            lab_name = m.group(1).strip()
            break

    # Parse individual lab values — "Test Name   Value   Unit   Reference Range"
    value_patterns = [
        # "Glucose  105  mg/dL  70-100"
        r"([A-Za-z\s/\(\)]+?)\s+(\d+\.?\d*)\s+([a-zA-Z/%]+)\s+(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)",
        # "Glucose  105  mg/dL"
        r"([A-Za-z\s/\(\)]+?)\s+(\d+\.?\d*)\s+([a-zA-Z/%]+)",
        # "Glucose: 105"
        r"([A-Za-z\s/\(\)]+?):\s*(\d+\.?\d*)",
    ]

    seen_tests: set[str] = set()
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for panel name (all caps line or specific keywords)
        if line.upper() == line and len(line) > 3 and not any(c.isdigit() for c in line):
            if not panel_name:
                panel_name = line.title()
            continue

        for pattern in value_patterns:
            m = re.match(pattern, line)
            if m:
                groups = m.groups()
                test_name = groups[0].strip()
                if test_name.lower() in seen_tests or len(test_name) < 2:
                    continue
                seen_tests.add(test_name.lower())

                item: dict = {"name": test_name, "value": float(groups[1])}
                if len(groups) >= 3:
                    item["unit"] = groups[2]
                if len(groups) >= 5:
                    item["reference_range"] = f"{groups[3]}-{groups[4]}"
                items.append(item)
                break

    if not items:
        parsing_notes.append("No structured lab values detected. The text may need manual review.")

    return {
        "panel_name": panel_name,
        "lab_name": lab_name,
        "doctor_name": doctor_name,
        "report_date": report_date,
        "items": items,
        "raw_text": text[:2000],
        "parsing_notes": parsing_notes,
    }


@router.post("/parse-lab-report", response_model=LabReportParseResponse)
async def parse_lab_report(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Extract structured lab data from uploaded PDF or text file."""
    content = await file.read()
    text = ""

    if file.content_type == "application/pdf" or (file.filename or "").endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except ImportError:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(io.BytesIO(content))
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            except ImportError:
                text = content.decode("utf-8", errors="ignore")
    else:
        text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        return LabReportParseResponse(
            parsing_notes=["Could not extract text from the uploaded file. Try a text-based PDF or plain text file."]
        )

    result = _parse_lab_text(text)
    return LabReportParseResponse(**result)


# ── PDF generation helpers ────────────────────────────────────────────────────

def _build_flowsheet_pdf(title: str, sections: list[tuple[str, list[tuple[str, str]]]]) -> bytes:
    """Render a clinical flowsheet as a proper PDF using reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FlowTitle",
        parent=styles["Title"],
        fontSize=16,
        textColor=colors.HexColor("#1a3c5e"),
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#2d6a9f"),
        spaceBefore=12,
        spaceAfter=4,
    )
    normal = styles["Normal"]
    footer_style = ParagraphStyle(
        "Footer",
        parent=normal,
        fontSize=8,
        textColor=colors.grey,
    )

    story = [
        Paragraph(title, title_style),
        Paragraph(
            f"Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}",
            ParagraphStyle("sub", parent=normal, fontSize=9, textColor=colors.grey),
        ),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2d6a9f"), spaceAfter=12),
    ]

    for section_title, rows in sections:
        if section_title:
            story.append(Paragraph(section_title, section_style))
        if rows:
            table_data = [[Paragraph(f"<b>{k}</b>", normal), Paragraph(str(v), normal)] for k, v in rows]
            tbl = Table(table_data, colWidths=[2.5 * inch, 4.5 * inch])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf2fb")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8daea")),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f7fbff")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(tbl)
        story.append(Spacer(1, 8))

    # Exchange table for PD (passed as raw Table already if needed)
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Paragraph("Generated by ALAFIA Health Platform — Confidential Medical Record", footer_style))

    doc.build(story)
    return buf.getvalue()


def _build_pd_exchange_table_rows(exchanges: list) -> list[tuple[str, str]]:
    """Convert PD exchange objects into label→value rows for the PDF table."""
    rows = []
    for ex in exchanges:
        rows.append((
            f"Exchange #{ex.exchange_number}",
            (
                f"Solution: {ex.solution_type or '-'}  |  "
                f"Inflow: {ex.inflow_volume_ml or '-'} mL  |  "
                f"Outflow: {ex.outflow_volume_ml or '-'} mL  |  "
                f"UF: {ex.uf_ml or '-'} mL  |  "
                f"Dwell: {ex.dwell_time_minutes or '-'} min  |  "
                f"Clarity: {ex.effluent_clarity or '-'}"
            ),
        ))
    return rows


@router.post("/generate-flowsheet")
async def generate_flowsheet_pdf(
    request: FlowsheetPDFRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a properly formatted PDF flowsheet for a dialysis session."""
    if request.session_type == "peritoneal_dialysis":
        result = await db.execute(
            select(PDSession).where(
                PDSession.id == request.session_id,
                PDSession.user_id == current_user.id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="PD session not found")

        title = f"Peritoneal Dialysis Flowsheet — {session.session_date}"
        sections = [
            ("Patient Info", [
                ("Patient", current_user.full_name or "—"),
                ("Date", str(session.session_date)),
                ("Modality", (session.modality or "").upper()),
            ]),
            ("Weights & Ultrafiltration", [
                ("Pre-Weight", f"{session.pre_weight_kg or '—'} kg"),
                ("Post-Weight", f"{session.post_weight_kg or '—'} kg"),
                ("Total UF", f"{session.total_uf_ml or '—'} mL"),
            ]),
            ("Blood Pressure", [
                ("Pre-BP", f"{session.pre_bp_systolic or '—'}/{session.pre_bp_diastolic or '—'} mmHg"),
                ("Post-BP", f"{session.post_bp_systolic or '—'}/{session.post_bp_diastolic or '—'} mmHg"),
            ]),
        ]
        if session.exchanges:
            sections.append(("Exchanges", _build_pd_exchange_table_rows(session.exchanges)))

    else:
        result = await db.execute(
            select(TherapySession).where(
                TherapySession.id == request.session_id,
                TherapySession.user_id == current_user.id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Therapy session not found")

        title = f"Hemodialysis Flowsheet — {session.session_date}"
        sections = [
            ("Patient Info", [
                ("Patient", current_user.full_name or "—"),
                ("Date", str(session.session_date)),
                ("Therapy Type", str(session.therapy_type)),
                ("Duration", f"{session.duration_minutes or '—'} min"),
            ]),
            ("Weights", [
                ("Pre-Weight", f"{session.pre_weight_kg or '—'} kg"),
                ("Post-Weight", f"{session.post_weight_kg or '—'} kg"),
            ]),
            ("Blood Pressure", [
                ("Pre-BP", f"{session.pre_bp_systolic or '—'}/{session.pre_bp_diastolic or '—'} mmHg"),
                ("Post-BP", f"{session.post_bp_systolic or '—'}/{session.post_bp_diastolic or '—'} mmHg"),
            ]),
        ]
        if session.notes:
            sections.append(("Notes", [("", session.notes)]))

    try:
        pdf_bytes = _build_flowsheet_pdf(title, sections)
        media_type = "application/pdf"
        filename = f"flowsheet_{request.session_id}.pdf"
    except Exception:
        # Fallback to plain text if reportlab unexpectedly fails
        lines = [title, "=" * len(title), ""]
        for sec_title, rows in sections:
            if sec_title:
                lines.append(f"[{sec_title}]")
            for k, v in rows:
                lines.append(f"  {k}: {v}" if k else f"  {v}")
            lines.append("")
        lines.append("--- Generated by ALAFIA ---")
        pdf_bytes = "\n".join(lines).encode("utf-8")
        media_type = "text/plain"
        filename = f"flowsheet_{request.session_id}.txt"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

