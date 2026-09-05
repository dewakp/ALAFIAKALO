"""Mental Health dashboard, assessments, breathing, gratitude endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import date, timedelta

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.mood import MoodEntry
from app.models.mental_health import MentalHealthAssessment, BreathingSession, GratitudeEntry
from app.schemas.mental_health import (
    AssessmentCreate, AssessmentResponse,
    BreathingSessionCreate, BreathingSessionResponse,
    GratitudeCreate, GratitudeResponse,
    MentalHealthStats, BreathingExerciseInfo,
)

router = APIRouter()

# ─── Breathing Exercise Library ────────────────────────────────────────

BREATHING_EXERCISES = [
    BreathingExerciseInfo(
        id="box_breathing",
        name="Box Breathing",
        description="Equal-length inhale, hold, exhale, hold. Used by Navy SEALs for calm focus.",
        inhale_seconds=4, hold_seconds=4, exhale_seconds=4, hold_after_exhale_seconds=4,
        recommended_cycles=4,
        benefits=["Reduces stress", "Improves focus", "Lowers heart rate"],
    ),
    BreathingExerciseInfo(
        id="4_7_8",
        name="4-7-8 Breathing",
        description="Dr. Andrew Weil's relaxation technique for sleep and anxiety relief.",
        inhale_seconds=4, hold_seconds=7, exhale_seconds=8, hold_after_exhale_seconds=0,
        recommended_cycles=4,
        benefits=["Promotes sleep", "Reduces anxiety", "Calms nervous system"],
    ),
    BreathingExerciseInfo(
        id="deep_breathing",
        name="Deep Belly Breathing",
        description="Slow, deep diaphragmatic breathing to activate the parasympathetic nervous system.",
        inhale_seconds=5, hold_seconds=2, exhale_seconds=5, hold_after_exhale_seconds=0,
        recommended_cycles=6,
        benefits=["Lowers blood pressure", "Reduces cortisol", "Full relaxation"],
    ),
    BreathingExerciseInfo(
        id="body_scan",
        name="Body Scan Meditation",
        description="Progressive relaxation through each body part with gentle breathing.",
        inhale_seconds=4, hold_seconds=0, exhale_seconds=6, hold_after_exhale_seconds=2,
        recommended_cycles=10,
        benefits=["Releases tension", "Mind-body awareness", "Deep relaxation"],
    ),
    BreathingExerciseInfo(
        id="grounding_5_4_3_2_1",
        name="5-4-3-2-1 Grounding",
        description="Engage 5 senses: 5 things you see, 4 you touch, 3 you hear, 2 you smell, 1 you taste.",
        inhale_seconds=4, hold_seconds=2, exhale_seconds=4, hold_after_exhale_seconds=0,
        recommended_cycles=5,
        benefits=["Stops panic attacks", "Anchors to present", "Reduces dissociation"],
    ),
]


def _compute_phq9(a: AssessmentCreate) -> tuple[int, str]:
    items = [a.phq_interest, a.phq_feeling_down, a.phq_sleep, a.phq_energy,
             a.phq_appetite, a.phq_self_esteem, a.phq_concentration,
             a.phq_psychomotor, a.phq_suicidal_ideation]
    total = sum(v or 0 for v in items)
    if total <= 4:
        severity = "minimal"
    elif total <= 9:
        severity = "mild"
    elif total <= 14:
        severity = "moderate"
    elif total <= 19:
        severity = "moderately_severe"
    else:
        severity = "severe"
    return total, severity


def _compute_gad7(a: AssessmentCreate) -> tuple[int, str]:
    items = [a.gad_nervous, a.gad_uncontrollable_worry, a.gad_excessive_worry,
             a.gad_trouble_relaxing, a.gad_restless, a.gad_irritable, a.gad_afraid]
    total = sum(v or 0 for v in items)
    if total <= 4:
        severity = "minimal"
    elif total <= 9:
        severity = "mild"
    elif total <= 14:
        severity = "moderate"
    else:
        severity = "severe"
    return total, severity


def _compute_who5(a: AssessmentCreate) -> tuple[int, str]:
    items = [a.who5_cheerful, a.who5_calm, a.who5_active, a.who5_rested, a.who5_interesting]
    raw = sum(v or 0 for v in items)
    pct = raw * 4  # WHO-5 percentage index (0-100)
    if pct >= 72:
        severity = "good"
    elif pct >= 50:
        severity = "moderate"
    elif pct >= 28:
        severity = "low"
    else:
        severity = "very_low"
    return pct, severity


# ─── Dashboard / Stats ────────────────────────────────────────────────

@router.get("/stats", response_model=MentalHealthStats)
async def get_mental_health_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute mental health dashboard statistics."""
    today = date.today()
    d7 = today - timedelta(days=7)
    d30 = today - timedelta(days=30)

    # Mood averages
    mood_7d = await db.execute(
        select(
            func.avg(MoodEntry.mood_score),
            func.avg(MoodEntry.stress_level),
            func.avg(MoodEntry.anxiety_level),
            func.avg(MoodEntry.sleep_quality),
            func.avg(MoodEntry.sleep_hours),
        ).where(MoodEntry.user_id == current_user.id, MoodEntry.entry_date >= d7)
    )
    r7 = mood_7d.one()

    mood_30d = await db.execute(
        select(func.avg(MoodEntry.mood_score), func.count(MoodEntry.id))
        .where(MoodEntry.user_id == current_user.id, MoodEntry.entry_date >= d30)
    )
    r30 = mood_30d.one()

    # Mood trend (compare last 7d avg vs previous 7d avg)
    d14 = today - timedelta(days=14)
    prev_7d = await db.execute(
        select(func.avg(MoodEntry.mood_score))
        .where(MoodEntry.user_id == current_user.id,
               MoodEntry.entry_date >= d14, MoodEntry.entry_date < d7)
    )
    prev_avg = prev_7d.scalar()
    cur_avg = r7[0]
    trend = None
    if cur_avg is not None and prev_avg is not None:
        diff = float(cur_avg) - float(prev_avg)
        trend = "improving" if diff > 0.5 else ("declining" if diff < -0.5 else "stable")

    # Streak (consecutive days with entries)
    entries_q = await db.execute(
        select(MoodEntry.entry_date)
        .where(MoodEntry.user_id == current_user.id)
        .order_by(MoodEntry.entry_date.desc())
        .distinct()
    )
    dates = [row[0] for row in entries_q.all()]
    streak = 0
    check = today
    for d in dates:
        if d == check:
            streak += 1
            check -= timedelta(days=1)
        elif d < check:
            break

    # Breathing minutes in last 30d
    br_result = await db.execute(
        select(func.sum(BreathingSession.duration_seconds))
        .where(BreathingSession.user_id == current_user.id, BreathingSession.session_date >= d30)
    )
    br_seconds = br_result.scalar() or 0

    # Latest assessments
    latest_phq9 = await db.execute(
        select(MentalHealthAssessment)
        .where(MentalHealthAssessment.user_id == current_user.id,
               MentalHealthAssessment.assessment_type == "phq9")
        .order_by(MentalHealthAssessment.assessment_date.desc()).limit(1)
    )
    phq9 = latest_phq9.scalar_one_or_none()

    latest_gad7 = await db.execute(
        select(MentalHealthAssessment)
        .where(MentalHealthAssessment.user_id == current_user.id,
               MentalHealthAssessment.assessment_type == "gad7")
        .order_by(MentalHealthAssessment.assessment_date.desc()).limit(1)
    )
    gad7 = latest_gad7.scalar_one_or_none()

    latest_who5 = await db.execute(
        select(MentalHealthAssessment)
        .where(MentalHealthAssessment.user_id == current_user.id,
               MentalHealthAssessment.assessment_type == "who5")
        .order_by(MentalHealthAssessment.assessment_date.desc()).limit(1)
    )
    who5 = latest_who5.scalar_one_or_none()

    # Compute wellness score (0-100 composite)
    wellness = None
    components = []
    if cur_avg is not None:
        components.append(float(cur_avg) * 10)  # mood out of 100
    if r7[2] is not None:  # anxiety inverse
        components.append((10 - float(r7[2])) * 10)
    if r7[1] is not None:  # stress inverse
        components.append((10 - float(r7[1])) * 10)
    if r7[3] is not None:  # sleep quality
        components.append(float(r7[3]) * 10)
    if components:
        wellness = int(sum(components) / len(components))

    return MentalHealthStats(
        avg_mood_7d=round(float(r7[0]), 1) if r7[0] else None,
        avg_mood_30d=round(float(r30[0]), 1) if r30[0] else None,
        avg_stress_7d=round(float(r7[1]), 1) if r7[1] else None,
        avg_anxiety_7d=round(float(r7[2]), 1) if r7[2] else None,
        avg_sleep_quality_7d=round(float(r7[3]), 1) if r7[3] else None,
        avg_sleep_hours_7d=round(float(r7[4]), 1) if r7[4] else None,
        mood_trend=trend,
        total_entries_30d=int(r30[1]) if r30[1] else 0,
        streak_days=streak,
        total_breathing_minutes_30d=round(br_seconds / 60, 1),
        latest_phq9_score=phq9.total_score if phq9 else None,
        latest_phq9_severity=phq9.severity if phq9 else None,
        latest_gad7_score=gad7.total_score if gad7 else None,
        latest_gad7_severity=gad7.severity if gad7 else None,
        latest_who5_score=who5.total_score if who5 else None,
        wellness_score=wellness,
    )


# ─── Assessments CRUD ─────────────────────────────────────────────────

@router.get("/assessments", response_model=list[AssessmentResponse])
async def list_assessments(
    assessment_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(MentalHealthAssessment).where(MentalHealthAssessment.user_id == current_user.id)
    if assessment_type:
        query = query.where(MentalHealthAssessment.assessment_type == assessment_type)
    query = query.order_by(MentalHealthAssessment.assessment_date.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/assessments", response_model=AssessmentResponse, status_code=201)
async def create_assessment(
    data: AssessmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    d = data.model_dump()
    if data.assessment_type == "phq9":
        score, severity = _compute_phq9(data)
    elif data.assessment_type == "gad7":
        score, severity = _compute_gad7(data)
    elif data.assessment_type == "who5":
        score, severity = _compute_who5(data)
    else:
        score, severity = 0, "unknown"

    d["total_score"] = score
    d["severity"] = severity

    entry = MentalHealthAssessment(**d, user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/assessments/{assessment_id}", status_code=204)
async def delete_assessment(
    assessment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MentalHealthAssessment).where(
            MentalHealthAssessment.id == assessment_id,
            MentalHealthAssessment.user_id == current_user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Assessment not found")
    await db.delete(entry)


# ─── Breathing Exercises ──────────────────────────────────────────────

@router.get("/breathing/exercises", response_model=list[BreathingExerciseInfo])
async def list_breathing_exercises():
    """Return the library of available breathing exercises."""
    return BREATHING_EXERCISES


@router.get("/breathing/sessions", response_model=list[BreathingSessionResponse])
async def list_breathing_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BreathingSession)
        .where(BreathingSession.user_id == current_user.id)
        .order_by(BreathingSession.session_date.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.post("/breathing/sessions", response_model=BreathingSessionResponse, status_code=201)
async def create_breathing_session(
    data: BreathingSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = BreathingSession(**data.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


# ─── Gratitude Journal ────────────────────────────────────────────────

@router.get("/gratitude", response_model=list[GratitudeResponse])
async def list_gratitude_entries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GratitudeEntry)
        .where(GratitudeEntry.user_id == current_user.id)
        .order_by(GratitudeEntry.entry_date.desc())
        .limit(30)
    )
    return result.scalars().all()


@router.post("/gratitude", response_model=GratitudeResponse, status_code=201)
async def create_gratitude_entry(
    data: GratitudeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = GratitudeEntry(**data.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/gratitude/{entry_id}", status_code=204)
async def delete_gratitude_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GratitudeEntry).where(
            GratitudeEntry.id == entry_id,
            GratitudeEntry.user_id == current_user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Gratitude entry not found")
    await db.delete(entry)
