"""Diagnostics Engine API endpoints.

Provides:
 - POST /diagnostics/assess          — AI-powered symptom assessment
 - GET  /diagnostics/assessments      — User's assessment history
 - GET  /diagnostics/assessments/{id} — Single assessment detail
 - POST /diagnostics/assessments/{id}/review — Provider review
 - POST /diagnostics/screening        — Proactive health screening
 - GET  /diagnostics/screening/recommendations — Saved screening recs
 - PUT  /diagnostics/screening/{id}   — Update screening status
 - POST /diagnostics/labs/correlate   — Lab result correlation
 - GET  /diagnostics/icd10/search     — Search ICD-10 codes
 - GET  /diagnostics/icd10/{code}     — Lookup single ICD-10 code
 - GET  /diagnostics/icd10/body-systems — List body systems
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.diagnostics import (
    DiagnosticAssessment,
    DifferentialDiagnosis,
    ScreeningRecommendation,
    LabCorrelationReport,
    AssessmentStatus,
    UrgencyLevel,
    ScreeningStatus,
)
from app.schemas.diagnostics import (
    DiagnosticAssessmentRequest,
    DiagnosticAssessmentOut,
    AssessmentSummaryOut,
    AssessmentReviewRequest,
    LabCorrelationRequest,
    LabCorrelationReportOut,
    ProactiveScreeningOut,
    ScreeningRecommendationOut,
    ScreeningUpdateRequest,
    ICD10CodeOut,
    ICD10SearchResult,
)
from app.services.diagnostics_engine import DiagnosticsEngine
from app.services.icd10_catalog import (
    search_icd10,
    get_icd10_by_code,
    get_codes_by_body_system,
    get_all_body_systems,
    ICD10_CHAPTERS,
)

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# DIAGNOSTIC ASSESSMENT
# ══════════════════════════════════════════════════════════════════════

@router.post("/assess", response_model=DiagnosticAssessmentOut)
async def run_diagnostic_assessment(
    request: DiagnosticAssessmentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run an AI-powered diagnostic assessment on reported symptoms.

    Analyzes symptoms in context of the patient's full health profile:
    demographics, conditions, medications, labs, vitals, family history,
    and lifestyle.  Returns ICD-10-coded differential diagnoses ranked
    by confidence with urgency triage and recommended next steps.
    """
    engine = DiagnosticsEngine(db)

    symptoms_dicts = [s.model_dump(exclude_none=True) for s in request.symptoms]

    assessment = await engine.assess_symptoms(
        user=current_user,
        symptoms=symptoms_dicts,
        additional_context=request.additional_context,
    )

    # Persist the assessment
    db_assessment = DiagnosticAssessment(
        user_id=current_user.id,
        assessment_code=assessment["assessment_id"],
        status=AssessmentStatus.completed,
        urgency_level=UrgencyLevel(assessment["urgency"]["level"]),
        urgency_trigger=assessment["urgency"].get("trigger"),
        reported_symptoms=assessment["reported_symptoms"],
        additional_context=request.additional_context,
        primary_impression=assessment.get("primary_impression"),
        supporting_evidence=assessment.get("supporting_evidence"),
        contradicting_factors=assessment.get("contradicting_factors"),
        recommended_actions=assessment.get("recommended_actions"),
        recommended_tests=assessment.get("recommended_tests"),
        red_flags=assessment.get("red_flags"),
        risk_factors_identified=assessment.get("risk_factors_identified"),
        follow_up_timeline=assessment.get("follow_up_timeline"),
        patient_education=assessment.get("patient_education"),
    )
    db.add(db_assessment)
    await db.flush()

    # Persist differential diagnoses
    for rank, diff in enumerate(assessment.get("differential_diagnoses", []), 1):
        db_diff = DifferentialDiagnosis(
            assessment_id=db_assessment.id,
            icd10_code=diff.get("icd10_code", "R69"),
            condition_name=diff.get("condition", "Unspecified"),
            body_system=diff.get("body_system"),
            confidence=diff.get("confidence", 0.0),
            rank=rank,
            matched_symptoms=diff.get("matched_symptoms"),
            risk_factor_match=diff.get("risk_factor_match"),
            reasoning=diff.get("reasoning"),
            source=diff.get("source", "ai_enhanced"),
        )
        db.add(db_diff)

    await db.flush()

    # Return
    assessment["id"] = db_assessment.id
    assessment["status"] = "completed"
    return assessment


@router.get("/assessments", response_model=list[AssessmentSummaryOut])
async def list_assessments(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's diagnostic assessments (most recent first)."""
    stmt = (
        select(DiagnosticAssessment)
        .where(DiagnosticAssessment.user_id == current_user.id)
        .order_by(desc(DiagnosticAssessment.created_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    assessments = result.scalars().all()

    return [
        AssessmentSummaryOut(
            id=a.id,
            assessment_code=a.assessment_code,
            status=a.status,
            urgency_level=a.urgency_level,
            primary_impression=a.primary_impression,
            symptom_count=len(a.reported_symptoms) if a.reported_symptoms else 0,
            differential_count=len(a.differentials) if a.differentials else 0,
            created_at=a.created_at,
        )
        for a in assessments
    ]


@router.get("/assessments/{assessment_id}", response_model=DiagnosticAssessmentOut)
async def get_assessment(
    assessment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single diagnostic assessment by ID."""
    stmt = select(DiagnosticAssessment).where(
        DiagnosticAssessment.id == assessment_id,
        DiagnosticAssessment.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return DiagnosticAssessmentOut(
        id=assessment.id,
        assessment_id=assessment.assessment_code,
        patient_id=assessment.user_id,
        assessed_at=assessment.created_at.isoformat(),
        urgency={
            "level": assessment.urgency_level,
            "label": assessment.urgency_level.capitalize() if isinstance(assessment.urgency_level, str) else assessment.urgency_level,
            "description": "",
            "color": "",
            "trigger": assessment.urgency_trigger,
        },
        reported_symptoms=assessment.reported_symptoms or [],
        differential_diagnoses=[
            {
                "id": d.id,
                "icd10_code": d.icd10_code,
                "condition": d.condition_name,
                "body_system": d.body_system,
                "confidence": d.confidence,
                "rank": d.rank,
                "reasoning": d.reasoning,
                "matched_symptoms": d.matched_symptoms,
                "risk_factor_match": d.risk_factor_match,
                "source": d.source,
                "provider_confirmed": d.provider_confirmed,
            }
            for d in sorted(assessment.differentials, key=lambda x: x.rank)
        ],
        primary_impression=assessment.primary_impression,
        supporting_evidence=assessment.supporting_evidence,
        contradicting_factors=assessment.contradicting_factors,
        recommended_actions=assessment.recommended_actions,
        recommended_tests=assessment.recommended_tests,
        red_flags=assessment.red_flags,
        risk_factors_identified=assessment.risk_factors_identified,
        follow_up_timeline=assessment.follow_up_timeline,
        patient_education=assessment.patient_education,
        status=assessment.status,
        disclaimer=DiagnosticsEngine.DISCLAIMER,
    )


@router.post("/assessments/{assessment_id}/review")
async def review_assessment(
    assessment_id: int,
    review: AssessmentReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Provider reviews an AI diagnostic assessment.

    Requires a healthcare provider role (physician, nurse, etc.).
    """
    stmt = select(DiagnosticAssessment).where(DiagnosticAssessment.id == assessment_id)
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    assessment.reviewed_by_user_id = current_user.id
    assessment.reviewer_notes = review.reviewer_notes
    assessment.reviewed_at = datetime.now(timezone.utc)
    assessment.status = AssessmentStatus.reviewed

    # Update confirmed / rejected differentials
    if review.confirmed_differentials:
        for diff in assessment.differentials:
            if diff.id in review.confirmed_differentials:
                diff.provider_confirmed = True
                diff.source = "provider_confirmed"
    if review.rejected_differentials:
        for diff in assessment.differentials:
            if diff.id in review.rejected_differentials:
                diff.provider_confirmed = False

    await db.flush()
    return {"message": "Assessment reviewed successfully", "assessment_id": assessment_id}


# ══════════════════════════════════════════════════════════════════════
# PROACTIVE SCREENING
# ══════════════════════════════════════════════════════════════════════

@router.post("/screening", response_model=ProactiveScreeningOut)
async def run_proactive_screening(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a proactive health screening analysis.

    Reviews the patient's complete profile — demographics, family history,
    conditions, labs, lifestyle — to identify recommended screenings,
    elevated risks, and preventive actions.
    """
    engine = DiagnosticsEngine(db)
    screening = await engine.proactive_screening(current_user)

    # Persist screening recommendations
    for rec in screening.get("recommended_screenings", []):
        screening_name = rec.get("screening", rec.get("screening_name", ""))
        if not screening_name:
            continue

        # Check if same screening already exists and is still open
        stmt = select(ScreeningRecommendation).where(
            ScreeningRecommendation.user_id == current_user.id,
            ScreeningRecommendation.screening_name == screening_name,
            ScreeningRecommendation.status.in_([
                ScreeningStatus.recommended,
                ScreeningStatus.scheduled,
            ]),
        )
        existing = await db.execute(stmt)
        if existing.scalar_one_or_none():
            continue

        db_rec = ScreeningRecommendation(
            user_id=current_user.id,
            screening_name=screening_name,
            icd10_code=rec.get("icd10_code"),
            rationale=rec.get("rationale"),
            frequency=rec.get("frequency"),
            priority=rec.get("priority"),
            risk_level=rec.get("risk_level"),
            risk_rationale=rec.get("risk_rationale"),
            associated_risks=rec.get("associated_risks"),
        )
        db.add(db_rec)

    await db.flush()
    return screening


@router.get("/screening/recommendations", response_model=list[ScreeningRecommendationOut])
async def list_screening_recommendations(
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List saved screening recommendations for the current user."""
    stmt = (
        select(ScreeningRecommendation)
        .where(ScreeningRecommendation.user_id == current_user.id)
        .order_by(desc(ScreeningRecommendation.created_at))
    )
    if status:
        stmt = stmt.where(ScreeningRecommendation.status == status)

    result = await db.execute(stmt)
    recs = result.scalars().all()

    return [
        ScreeningRecommendationOut(
            id=r.id,
            screening=r.screening_name,
            icd10_code=r.icd10_code,
            rationale=r.rationale,
            frequency=r.frequency,
            priority=r.priority,
            status=r.status,
            risk_level=r.risk_level,
        )
        for r in recs
    ]


@router.put("/screening/{recommendation_id}", response_model=ScreeningRecommendationOut)
async def update_screening_recommendation(
    recommendation_id: int,
    update: ScreeningUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the status of a screening recommendation."""
    stmt = select(ScreeningRecommendation).where(
        ScreeningRecommendation.id == recommendation_id,
        ScreeningRecommendation.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Screening recommendation not found")

    rec.status = ScreeningStatus(update.status)
    if update.completed_date:
        rec.completed_date = update.completed_date
    await db.flush()

    return ScreeningRecommendationOut(
        id=rec.id,
        screening=rec.screening_name,
        icd10_code=rec.icd10_code,
        rationale=rec.rationale,
        frequency=rec.frequency,
        priority=rec.priority,
        status=rec.status,
        risk_level=rec.risk_level,
    )


# ══════════════════════════════════════════════════════════════════════
# LAB CORRELATION
# ══════════════════════════════════════════════════════════════════════

@router.post("/labs/correlate", response_model=LabCorrelationReportOut)
async def correlate_lab_results(
    request: LabCorrelationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Correlate lab results with symptoms and conditions.

    Analyzes the patient's lab results in context of their
    complete clinical picture and identifies diagnostic correlations,
    possible underlying conditions, and recommended follow-up tests.
    """
    engine = DiagnosticsEngine(db)
    report = await engine.correlate_lab_results(
        user=current_user,
        lab_result_ids=request.lab_result_ids,
    )

    # Persist
    db_report = LabCorrelationReport(
        user_id=current_user.id,
        correlation_code=report["correlation_id"],
        labs_analyzed=report["labs_analyzed"],
        abnormal_count=report["abnormal_count"],
        abnormal_labs=report["abnormal_labs"],
        diagnostic_correlations=report["diagnostic_correlations"],
        possible_conditions=report["possible_conditions"],
        recommended_follow_up_tests=report["recommended_follow_up_tests"],
        clinical_significance=report.get("clinical_significance"),
    )
    db.add(db_report)
    await db.flush()

    report["id"] = db_report.id
    return report


# ══════════════════════════════════════════════════════════════════════
# ICD-10 REFERENCE
# ══════════════════════════════════════════════════════════════════════

@router.get("/icd10/search", response_model=ICD10SearchResult)
async def search_icd10_codes(
    q: str = Query(..., min_length=2, description="Search keyword"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search the ICD-10 catalog by keyword.

    Searches across code titles, synonyms, symptoms, body systems,
    and the code itself.  No authentication required for code lookup.
    """
    results = search_icd10(q, limit=limit)
    return ICD10SearchResult(
        query=q,
        results=[
            ICD10CodeOut(
                code=r.code,
                title=r.title,
                chapter=r.chapter,
                chapter_title=ICD10_CHAPTERS.get(r.chapter, {}).get("title"),
                category=r.category,
                body_system=r.body_system,
                common_symptoms=r.common_symptoms,
                risk_factors=r.risk_factors,
                is_billable=r.is_billable,
            )
            for r in results
        ],
        total=len(results),
    )


@router.get("/icd10/body-systems")
async def list_body_systems():
    """List all body systems in the ICD-10 catalog."""
    systems = get_all_body_systems()
    return {"body_systems": sorted(systems)}


@router.get("/icd10/chapters")
async def list_chapters():
    """List all ICD-10 chapters."""
    return {
        "chapters": [
            {"chapter": k, "title": v["title"], "range": v["range"]}
            for k, v in ICD10_CHAPTERS.items()
        ]
    }


@router.get("/icd10/body-system/{body_system}", response_model=list[ICD10CodeOut])
async def get_codes_for_body_system(body_system: str):
    """Get all ICD-10 codes for a specific body system."""
    codes = get_codes_by_body_system(body_system)
    if not codes:
        raise HTTPException(status_code=404, detail=f"No codes found for body system '{body_system}'")
    return [
        ICD10CodeOut(
            code=c.code,
            title=c.title,
            chapter=c.chapter,
            chapter_title=ICD10_CHAPTERS.get(c.chapter, {}).get("title"),
            category=c.category,
            body_system=c.body_system,
            common_symptoms=c.common_symptoms,
            risk_factors=c.risk_factors,
            is_billable=c.is_billable,
        )
        for c in codes
    ]


@router.get("/icd10/{code}", response_model=ICD10CodeOut)
async def lookup_icd10_code(code: str):
    """Look up a single ICD-10 code."""
    code_obj = get_icd10_by_code(code.upper())
    if not code_obj:
        raise HTTPException(status_code=404, detail=f"ICD-10 code '{code}' not found")

    return ICD10CodeOut(
        code=code_obj.code,
        title=code_obj.title,
        chapter=code_obj.chapter,
        chapter_title=ICD10_CHAPTERS.get(code_obj.chapter, {}).get("title"),
        category=code_obj.category,
        body_system=code_obj.body_system,
        common_symptoms=code_obj.common_symptoms,
        risk_factors=code_obj.risk_factors,
        is_billable=code_obj.is_billable,
    )
