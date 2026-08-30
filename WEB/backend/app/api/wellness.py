import logging
"""Wellness endpoints — score, trends, daily recs, health improvements."""

import json
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.labs import LabResult
from app.models.chronic_conditions import TherapySession, IntradialyticReading
from app.models.nutrition import NutritionLog
from app.models.fitness import FitnessLog
from app.models.mood import MoodEntry
from app.models.sleep import SleepLog
from app.models.vitals import VitalsLog
from app.models.medications import Medication
from app.models.wellness import WellnessScore as WellnessScoreModel
from app.schemas.wellness import (
    WellnessScoreResponse, HealthTrendResponse, TrendStream, TrendDataPoint,
    DailyRecommendationsResponse, RecommendationItem, HealthImprovementsResponse,
    HEBCSScoreResponse, WhatIfRequest, WhatIfResponse, WhatIfPathwayDelta,
)
from app.services.hebcs_engine import compute_hebcs, ESRD_PATHWAYS

logger = logging.getLogger(__name__)

router = APIRouter()


async def _compute_wellness_score(user_id: int, db: AsyncSession) -> dict:
    """Wellness score from measured values, not from how often the user logged.

    What this replaces, component by component — every one of them counted
    attendance and none of them looked at a value:

        nutrition            min(100, entry_count * 3.3)   30 entries = 100%
        fitness              min(100, workout_count * 8.3)
        vitals               min(100, vitals_count * 10)   no reading was read
        medication_adherence 80 if any active med row else 50
        sleep / mood         defaulted to 50 when absent

    …then averaged flat, so an account with no data landed near 50 whatever the
    patient's actual condition — which is exactly how a score of 50 appeared
    beside a page full of bad signs. Worse, the explanation said "Great
    nutrition tracking consistency", naming what it really measured while being
    presented as health.

    Now: intake scored against this patient's own goals, blood pressure read as
    a value, adherence measured against the prescription, and anything with no
    data reported as UNKNOWN rather than defaulted. `overall_score` is None when
    nothing at all was measured.
    """
    from app.services import health_score as hs
    from app.services import clinical_sources as sources
    from app.services.nutrient_goals_service import compute_goals
    from app.models.user import User as UserModel

    today = date.today()
    cutoff = today - timedelta(days=30)

    user = (await db.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one_or_none()

    # ── This patient's goals decide WHICH nutrients are worth averaging ───
    conditions = list(await sources.conditions(db, user_id, active_only=True))
    _goals_preview = compute_goals(
        date_of_birth=str(user.date_of_birth) if user and user.date_of_birth else None,
        sex=user.gender if user else None,
        height_cm=user.height_cm if user else None,
        current_weight_kg=user.current_weight_kg if user else None,
        target_weight_kg=user.target_weight_kg if user else None,
        activity_level=user.activity_level if user else None,
        conditions=conditions,
    )

    # ── Nutrition: mean daily intake vs this patient's own goals ──────────
    # Which nutrients to average is decided by the GOALS, not by a list typed
    # here: whatever `compute_goals` produces for this patient is what gets
    # scored, so adding a goal needs no second edit. Goal keys are already the
    # column names.
    goal_keys = [str(g.get("key") or "") for g in (_goals_preview.get("goals") or [])]
    nutrient_cols = {
        key: getattr(NutritionLog, key)
        for key in goal_keys
        if key and hasattr(NutritionLog, key)
    }
    intake: dict[str, float | None] = {}
    for key, col in nutrient_cols.items():
        # Per-day totals first, then the mean over days that HAVE data — a
        # patient who logs twice a week must not read as eating a seventh of
        # their potassium.
        daily = (await db.execute(
            select(func.sum(col)).where(
                NutritionLog.user_id == user_id,
                NutritionLog.log_date >= cutoff,
                col.isnot(None),
            ).group_by(NutritionLog.log_date)
        )).scalars().all()
        vals = [float(v) for v in daily if v is not None]
        intake[key] = sum(vals) / len(vals) if vals else None

    goals_payload = _goals_preview
    on_dialysis = any(
        "dialysis" in (getattr(c, "name", "") or "").lower()
        or "renal" in (getattr(c, "name", "") or "").lower()
        or str(getattr(c, "icd11_code", "") or "").upper().startswith("GB6")
        for c in conditions
    )

    # ── Fitness ──────────────────────────────────────────────────────────
    fit_count = (await db.execute(
        select(func.count(FitnessLog.id)).where(
            FitnessLog.user_id == user_id, FitnessLog.log_date >= cutoff)
    )).scalar() or 0
    any_fitness = (await db.execute(
        select(func.count(FitnessLog.id)).where(FitnessLog.user_id == user_id)
    )).scalar() or 0
    # No activity EVER is unknown; none in the window on an active logger is a
    # real zero.
    workouts_per_week = (fit_count / (30 / 7)) if any_fitness else None

    # ── Sleep ────────────────────────────────────────────────────────────
    sleep_row = (await db.execute(
        select(func.avg(SleepLog.total_hours), func.avg(SleepLog.quality_score))
        .where(SleepLog.user_id == user_id, SleepLog.sleep_date >= cutoff)
    )).first()
    avg_sleep = float(sleep_row[0]) if sleep_row and sleep_row[0] is not None else None
    avg_quality = float(sleep_row[1]) if sleep_row and sleep_row[1] is not None else None

    # ── Mood ─────────────────────────────────────────────────────────────
    mood_row = (await db.execute(
        select(func.avg(MoodEntry.mood_score), func.avg(MoodEntry.energy_level),
               func.avg(MoodEntry.stress_level))
        .where(MoodEntry.user_id == user_id, MoodEntry.entry_date >= cutoff)
    )).first()
    avg_mood = float(mood_row[0]) if mood_row and mood_row[0] is not None else None
    avg_energy = float(mood_row[1]) if mood_row and mood_row[1] is not None else None
    avg_stress = float(mood_row[2]) if mood_row and mood_row[2] is not None else None

    # ── Vitals: the reading, not the fact that one exists ────────────────
    vitals = (await db.execute(
        select(VitalsLog).where(
            VitalsLog.user_id == user_id, VitalsLog.log_date >= cutoff)
        .order_by(VitalsLog.log_date.desc()).limit(1)
    )).scalar_one_or_none()

    # ── Medication adherence vs the prescription ─────────────────────────
    # Through clinical_sources, never the models directly: prescribed and taken
    # live in different tables and reading one alone is how a physician saw two
    # drugs stopped in 2017 beside 921 dose logs (canon 3aa).
    prescribed = [m.name for m in
                  await sources.medications_prescribed(db, user_id, active_only=True)]
    logged = [m.name for m in await sources.medications_taken(db, user_id, since=cutoff)]

    components = [
        hs.nutrition_adherence(intake, goals_payload.get("goals") or []),
        hs.medication_adherence(list(prescribed), list(logged)),
        hs.vitals_component(
            bmi=getattr(vitals, "bmi", None) if vitals else None,
            systolic=getattr(vitals, "blood_pressure_systolic", None) if vitals else None,
            diastolic=getattr(vitals, "blood_pressure_diastolic", None) if vitals else None,
            on_dialysis=on_dialysis,
        ),
        hs.sleep_component(avg_hours=avg_sleep, avg_quality=avg_quality),
        hs.mood_component(avg_mood=avg_mood, avg_energy=avg_energy, avg_stress=avg_stress),
        hs.fitness_component(workouts_per_week),
    ]
    result = hs.overall_score(components)
    by_key = result["component_scores"]

    # ── Explanation: say what was measured AND what was not ──────────────
    parts: list[str] = []
    nutrition_detail = result["detail"].get("nutrition") or {}
    shortfalls = nutrition_detail.get("shortfalls") or []
    if by_key.get("nutrition") is None:
        parts.append("No meals with nutrient data in the last 30 days, so "
                     "nutrition could not be assessed.")
    elif shortfalls:
        parts.append("Nutrition is short on " + ", ".join(shortfalls) + ".")
    else:
        parts.append("Intake is within your targets.")

    med_detail = result["detail"].get("medication_adherence") or {}
    if med_detail.get("not_logged"):
        parts.append("No doses logged for " + ", ".join(med_detail["not_logged"]) + ".")

    if result["components_unknown"]:
        parts.append("Not assessed for lack of data: "
                     + ", ".join(result["components_unknown"]) + ".")

    return {
        "overall_score": result["overall_score"],
        "nutrition_score": by_key.get("nutrition"),
        "fitness_score": by_key.get("fitness"),
        "sleep_score": by_key.get("sleep"),
        "mood_score": by_key.get("mood"),
        "vitals_score": by_key.get("vitals"),
        "medication_adherence_score": by_key.get("medication_adherence"),
        "confidence": result["confidence"],
        "components_unknown": result["components_unknown"],
        "detail": result["detail"],
        "explanation": " ".join(parts),
        "recommendations": json.dumps(parts),
    }


@router.get("/omega", response_model=HEBCSScoreResponse)
async def get_hebcs_omega_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """HEBCS Ω — Clinical biomarker wellness score using the published
    trapezoidal/pathway/geometric-mean framework (7-pathway ESRD model).

    Returns Ω ∈ (0, 1) with per-pathway and per-biomarker breakdown.
    """
    # Fetch each user's most recent lab value per test_name, WITH the range the
    # lab reported for it — there is no single optimal BUN, so the band has to
    # come from the report rather than from a number written into the engine.
    result = await db.execute(
        select(
            LabResult.test_name,
            LabResult.value,
            LabResult.test_date,
            LabResult.reference_range_low,
            LabResult.reference_range_high,
        )
        .where(LabResult.user_id == current_user.id, LabResult.value.isnot(None))
        .order_by(LabResult.test_name, LabResult.test_date.desc())
    )
    rows = result.all()

    # Keep only the most recent value per analyte
    biomarker_values: dict[str, float] = {}
    lab_ranges: dict[str, tuple[float | None, float | None]] = {}
    latest_date: date | None = None
    seen: set[str] = set()
    for test_name, value, test_date, ref_low, ref_high in rows:
        if test_name not in seen:
            biomarker_values[test_name] = value
            if ref_low is not None and ref_high is not None:
                lab_ranges[test_name] = (ref_low, ref_high)
            seen.add(test_name)
            if latest_date is None or test_date > latest_date:
                latest_date = test_date

    # nPCR carries 40% of the Nutritional pathway and this lab reports it as
    # N/A on every date, so the pathway has always scored on albumin and BUN
    # alone. It is computable from urea kinetics — see services/urea_kinetics.py
    # — and is passed in as DERIVED so it is scored without being counted as
    # measured.
    derived: dict[str, float] = {}
    try:
        from app.services import urea_kinetics as uk

        pre_bun = biomarker_values.get("BUN")
        post_bun = next((biomarker_values.get(k) for k in
                         ("BUN Post", "BUN-P", "BUN - Post")
                         if biomarker_values.get(k) is not None), None)

        # Kt/V and URR are CALCULATED, not looked up — a lab reports them only
        # when it chooses to, and this record has them on 6 of 12 dates. Both
        # come from the two BUN draws the lab does report, plus the session.
        # Validated against every date that has both inputs and a reported
        # value: 1.61/1.62, 1.34/1.35, 1.44/1.44, 0.90/0.90.
        if biomarker_values.get("spKt/V") is None:
            session = (await db.execute(
                select(TherapySession)
                .where(TherapySession.user_id == user_id,
                       TherapySession.duration_minutes.isnot(None))
                .order_by(TherapySession.scheduled_date.desc()).limit(1)
            )).scalar_one_or_none()
            if session is not None:
                # UF comes from the MACHINE minus saline returned, never from
                # pre-minus-post weight: that figure inherits every scale error
                # and averages -0.02 L across this record, against +0.87 L from
                # the readings. A post-dialysis weight of 0.3 kg in this data
                # produced a "60,900 ml removed".
                readings = (await db.execute(
                    select(IntradialyticReading)
                    .where(IntradialyticReading.session_id == session.id)
                    .order_by(IntradialyticReading.reading_number)
                )).scalars().all()
                uf_l = uk.net_ultrafiltration_litres(readings)
                if uf_l is None:
                    uf_l = session.total_uf_liters
                if uf_l is None and session.fluid_removed_ml is not None:
                    uf_l = session.fluid_removed_ml / 1000.0
                ktv = uk.single_pool_ktv(
                    pre_bun, post_bun, session.duration_minutes, uf_l,
                    session.post_dialysis_weight_kg)
                if ktv is not None:
                    derived["KtV (Dialysis Adequacy)"] = ktv.value

        if biomarker_values.get("URR") is None and biomarker_values.get("URR%") is None:
            urr = uk.urea_reduction_ratio(pre_bun, post_bun)
            if urr is not None:
                derived["URR (Urea Reduction Ratio)"] = urr.value

        # nPCR needs a Kt/V, computed or reported.
        npcr = uk.estimate_npcr(
            pre_bun,
            biomarker_values.get("spKt/V") or derived.get("KtV (Dialysis Adequacy)"))
        if npcr is not None:
            derived["nPCR (Protein Catabolic Rate)"] = npcr.value
    except Exception:  # noqa: BLE001 - a derivation must not break the score
        logger.warning("Could not derive urea kinetics", exc_info=True)

    # Ranges the labs actually reported — this patient's own first, then the
    # range most commonly reported for that analyte across the population.
    # Anything with neither keeps the framework's published band, and says so.
    from app.services import reference_ranges as refs
    resolved_ranges = await refs.resolve(db, current_user.id)
    resolved_ranges.update(lab_ranges)      # the latest row for this patient wins

    result_data = compute_hebcs(biomarker_values, derived_values=derived,
                                reference_ranges=resolved_ranges)
    omega = result_data["omega"]

    # Build plain-language interpretation
    if omega >= 0.70:
        interp = f"Your wellness score is {omega:.3f} (Ω), which is above 0.70 — indicating relatively well-managed health given your ESRD diagnosis."
    elif omega >= 0.50:
        interp = f"Your wellness score is {omega:.3f} (Ω). Several pathways are sub-optimal. Review your Bone Mineral, Hematologic, and Dialysis Adequacy pathways for priority areas."
    elif omega >= 0.35:
        interp = f"Your wellness score is {omega:.3f} (Ω), indicating moderate clinical burden across multiple pathways. Close monitoring of all low-scoring pathways is recommended."
    else:
        interp = f"Your wellness score is {omega:.3f} (Ω), indicating high clinical burden. Immediate clinical review is advised."

    # Add specific pathway flags
    low_pathways = [
        name for name, pdata in result_data["pathways"].items()
        if pdata["score"] is not None and pdata["score"] < 0.5
    ]
    if low_pathways:
        interp += f" Critical pathways: {', '.join(low_pathways)}."

    # Say what could NOT be assessed. A pathway with no biomarker drops out of
    # the geometric mean silently, so without this the score reads as a
    # whole-patient verdict when part of the patient was never looked at.
    if result_data["unscored_pathways"]:
        interp += (" Not assessed for lack of recent results: "
                   + ", ".join(result_data["unscored_pathways"]) + ".")

    # A pathway scored on less than half its evidence is worth saying out loud.
    thin = [name for name, pdata in result_data["pathways"].items()
            if pdata["score"] is not None and pdata["coverage"] < 0.5]
    if thin:
        interp += (" Based on limited results: " + ", ".join(thin) + ".")

    from app.schemas.wellness import HEBCSPathwayResult, HEBCSBiomarkerDetail
    pathway_response = {
        name: HEBCSPathwayResult(
            score=pdata["score"],
            weight=pdata["weight"],
            coverage=pdata["coverage"],
            coverage_with_derived=pdata["coverage_with_derived"],
            measured=pdata["measured"],
            derived=pdata["derived"],
            expected=pdata["expected"],
            biomarkers=[HEBCSBiomarkerDetail(**b) for b in pdata["biomarkers"]],
        )
        for name, pdata in result_data["pathways"].items()
    }

    return HEBCSScoreResponse(
        computed_at=datetime.now(timezone.utc),
        lab_date_used=latest_date,
        omega=result_data["omega"],
        omega_pct=result_data["omega_pct"],
        data_coverage=result_data["data_coverage"],
        pathways=pathway_response,
        unscored_pathways=result_data["unscored_pathways"],
        interpretation=interp,
    )


@router.get("/score", response_model=WellnessScoreResponse)
async def get_wellness_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculate and return current wellness score (0-100)."""
    data = await _compute_wellness_score(current_user.id, db)
    today = date.today()

    # `confidence`, `components_unknown` and `detail` are computed per request
    # and have no column — the stored row is the history series. Splitting on
    # the model's real columns keeps them out of the constructor rather than
    # relying on the dict happening to match the table.
    columns = {c.name for c in WellnessScoreModel.__table__.columns}
    persisted = {k: v for k, v in data.items() if k in columns}

    score_obj = WellnessScoreModel(
        user_id=current_user.id, score_date=today, **persisted,
    )
    db.add(score_obj)
    await db.flush()
    await db.refresh(score_obj)

    return WellnessScoreResponse(
        **{c: getattr(score_obj, c) for c in columns},
        confidence=data.get("confidence"),
        components_unknown=data.get("components_unknown") or [],
        detail=data.get("detail"),
    )


@router.get("/score/history", response_model=list[WellnessScoreResponse])
async def get_wellness_score_history(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() - timedelta(days=days)
    result = await db.execute(
        select(WellnessScoreModel)
        .where(WellnessScoreModel.user_id == current_user.id, WellnessScoreModel.score_date >= cutoff)
        .order_by(WellnessScoreModel.score_date.desc())
    )
    return result.scalars().all()


@router.get("/trends", response_model=HealthTrendResponse)
async def get_health_trends(
    days: int = Query(90, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Multi-dimensional health trend analysis across data streams."""
    cutoff = date.today() - timedelta(days=days)
    streams = []

    # Nutrition trend (daily calories)
    result = await db.execute(
        select(
            NutritionLog.log_date.label("d"),
            func.sum(NutritionLog.calories),
        )
        .where(NutritionLog.user_id == current_user.id, NutritionLog.log_date >= cutoff)
        .group_by(NutritionLog.log_date).order_by(NutritionLog.log_date)
    )
    nutr_data = result.all()
    if nutr_data:
        vals = [r[1] or 0 for r in nutr_data]
        trend = "improving" if len(vals) > 1 and vals[-1] <= vals[0] else "stable"
        streams.append(TrendStream(
            name="Daily Calories",
            data=[TrendDataPoint(date=str(r[0])[:10], value=float(r[1] or 0)) for r in nutr_data],
            trend=trend,
        ))

    # Mood trend
    result = await db.execute(
        select(MoodEntry.entry_date, MoodEntry.mood_score)
        .where(MoodEntry.user_id == current_user.id, MoodEntry.entry_date >= cutoff)
        .order_by(MoodEntry.entry_date)
    )
    mood_data = result.all()
    if mood_data:
        vals = [r[1] for r in mood_data if r[1]]
        trend = "improving" if len(vals) > 1 and vals[-1] > vals[0] else "stable"
        streams.append(TrendStream(
            name="Mood Score",
            data=[TrendDataPoint(date=str(r[0])[:10], value=float(r[1])) for r in mood_data if r[1]],
            trend=trend,
        ))

    # Fitness trend (weekly workout count)
    result = await db.execute(
        select(
            func.date_trunc("week", FitnessLog.log_date).label("w"),
            func.count(FitnessLog.id),
        )
        .where(FitnessLog.user_id == current_user.id, FitnessLog.log_date >= cutoff)
        .group_by("w").order_by("w")
    )
    fit_data = result.all()
    if fit_data:
        streams.append(TrendStream(
            name="Weekly Workouts",
            data=[TrendDataPoint(date=str(r[0])[:10], value=float(r[1])) for r in fit_data],
            trend="stable",
        ))

    # Lab trends (weight if available)
    result = await db.execute(
        select(VitalsLog.log_date, VitalsLog.weight_kg)
        .where(VitalsLog.user_id == current_user.id, VitalsLog.weight_kg.isnot(None), VitalsLog.log_date >= cutoff)
        .order_by(VitalsLog.log_date)
    )
    weight_data = result.all()
    if weight_data:
        streams.append(TrendStream(
            name="Weight (kg)",
            data=[TrendDataPoint(date=str(r[0])[:10], value=float(r[1])) for r in weight_data],
            trend="stable",
        ))

    # Summary
    total_streams = len(streams)
    summary = f"Analyzing {total_streams} health data streams over the past {days} days."
    correlations = []
    suggestions = []
    if any(s.trend == "improving" for s in streams):
        correlations.append("Positive trends detected in multiple health areas.")
    suggestions.append("Continue monitoring your health metrics regularly.")

    return HealthTrendResponse(
        overall_summary=summary, streams=streams,
        correlations=correlations, suggestions=suggestions,
    )


@router.get("/recommendations", response_model=DailyRecommendationsResponse)
async def get_daily_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Personalized daily recommendations across 7 categories."""
    today_str = str(date.today())
    recs: dict[str, list[RecommendationItem]] = {
        "nutrition": [], "fitness": [], "sleep": [], "medication": [],
        "mood": [], "hydration": [], "general": [],
    }

    # Nutrition recs
    result = await db.execute(
        select(func.count(NutritionLog.id)).where(
            NutritionLog.user_id == current_user.id,
            NutritionLog.log_date >= (date.today() - timedelta(days=1)),
        )
    )
    yesterday_meals = result.scalar() or 0
    if yesterday_meals < 3:
        recs["nutrition"].append(RecommendationItem(
            category="nutrition", title="Log your meals",
            description="You logged fewer than 3 meals yesterday. Try tracking all meals today.",
            priority="high", action="Go to Nutrition",
        ))
    recs["nutrition"].append(RecommendationItem(
        category="nutrition", title="Eat colorful vegetables",
        description="Aim for at least 5 servings of varied vegetables today.",
        priority="medium",
    ))

    # Fitness recs
    result = await db.execute(
        select(func.count(FitnessLog.id)).where(
            FitnessLog.user_id == current_user.id,
            FitnessLog.log_date >= (date.today() - timedelta(days=7)),
        )
    )
    weekly_workouts = result.scalar() or 0
    target = 4
    if weekly_workouts < target:
        recs["fitness"].append(RecommendationItem(
            category="fitness", title="Get moving today",
            description=f"You've had {weekly_workouts} workouts this week (target: {target}). Try a 30-minute walk.",
            priority="high", action="Go to Fitness",
        ))

    # Sleep recs
    recs["sleep"].append(RecommendationItem(
        category="sleep", title="Aim for 7-8 hours",
        description="Consistent bedtime and wake time improve sleep quality.",
        priority="medium",
    ))

    # Medication recs
    result = await db.execute(
        select(Medication).where(Medication.user_id == current_user.id, Medication.is_active == True)
    )
    active_meds = result.scalars().all()
    if active_meds:
        recs["medication"].append(RecommendationItem(
            category="medication", title="Take your medications",
            description=f"You have {len(active_meds)} active medication(s). Don't forget today's doses.",
            priority="high",
        ))

    # Mood recs
    recs["mood"].append(RecommendationItem(
        category="mood", title="Check in with yourself",
        description="Take a moment to log your mood and reflect on how you're feeling.",
        priority="medium", action="Go to Mood",
    ))

    # Hydration recs
    recs["hydration"].append(RecommendationItem(
        category="hydration", title="Stay hydrated",
        description="Aim for 8 glasses of water today. Adjust based on activity level.",
        priority="medium",
    ))

    # General recs
    recs["general"].append(RecommendationItem(
        category="general", title="Health check reminder",
        description="Schedule your next routine check-up if it's been over 6 months.",
        priority="low",
    ))

    all_recs = [r for v in recs.values() for r in v]
    return DailyRecommendationsResponse(
        date=today_str, recommendations=all_recs, **recs,
    )


@router.get("/improvements", response_model=HealthImprovementsResponse)
async def get_health_improvements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Score-based health improvement recommendations."""
    data = await _compute_wellness_score(current_user.id, db)
    score = data["overall_score"]

    nutrition_improvements = []
    fitness_improvements = []
    sleep_improvements = []
    mood_improvements = []
    medical_improvements = []

    if data["nutrition_score"] < 70:
        nutrition_improvements.extend([
            "Log meals consistently to track nutrient intake.",
            "Focus on whole foods: fruits, vegetables, lean proteins, whole grains.",
            "Reduce processed food and added sugar intake.",
        ])
    if data["fitness_score"] < 70:
        fitness_improvements.extend([
            "Start with 150 minutes of moderate exercise per week.",
            "Include both cardio and strength training.",
            "Take breaks from sitting every hour.",
        ])
    if data["sleep_score"] < 70:
        sleep_improvements.extend([
            "Maintain a consistent sleep schedule.",
            "Limit caffeine after 2 PM.",
            "Create a dark, quiet sleep environment.",
        ])
    if data["mood_score"] < 60:
        mood_improvements.extend([
            "Practice daily gratitude journaling.",
            "Engage in activities you enjoy.",
            "Consider mindfulness meditation for stress management.",
        ])
    if data["vitals_score"] < 50:
        medical_improvements.extend([
            "Log vitals regularly to track health trends.",
            "Schedule a check-up with your healthcare provider.",
        ])

    summary = f"Your wellness score is {score:.0f}/100. "
    if score >= 80:
        summary += "You're doing great! Keep up the healthy habits."
    elif score >= 60:
        summary += "You're on the right track. Focus on the areas below for improvement."
    else:
        summary += "There are several areas where you can improve. Start with small changes."

    return HealthImprovementsResponse(
        summary=summary, wellness_score=score,
        nutrition_improvements=nutrition_improvements,
        fitness_improvements=fitness_improvements,
        sleep_improvements=sleep_improvements,
        mood_improvements=mood_improvements,
        medical_improvements=medical_improvements,
    )


# ── HEBCS What-If Simulator ────────────────────────────────────────────────

async def _fetch_latest_biomarkers(user_id: int, db: AsyncSession) -> dict[str, float]:
    """Return the most recent value per lab test_name for this user."""
    result = await db.execute(
        select(LabResult.test_name, LabResult.value, LabResult.test_date)
        .where(LabResult.user_id == user_id, LabResult.value.isnot(None))
        .order_by(LabResult.test_name, LabResult.test_date.desc())
    )
    biomarkers: dict[str, float] = {}
    seen: set[str] = set()
    for test_name, value, _ in result.all():
        if test_name not in seen:
            biomarkers[test_name] = value
            seen.add(test_name)
    return biomarkers


@router.post("/whatif", response_model=WhatIfResponse)
async def what_if_scenario(
    request: WhatIfRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """HEBCS What-If Clinical Simulator.

    Override any subset of biomarker values to simulate how a clinical
    intervention (dietary change, medication adjustment, dialysis
    parameter change) would affect the patient's Ω wellness score.

    Example: {"Phosphorus": 4.5, "Albumin": 4.2} asks
    "What would my Ω be if phosphorus dropped to 4.5 and albumin
    improved to 4.2?"
    """
    # Baseline: real latest lab values
    baseline_bio = await _fetch_latest_biomarkers(current_user.id, db)

    # Scenario: override with hypothetical values
    overrides = request.to_biomarker_dict()
    scenario_bio = {**baseline_bio, **overrides}

    # If both Calcium and Phosphorus are present (either real or overridden),
    # recompute CaxP product automatically for the scenario
    ca = scenario_bio.get("Calcium")
    p = scenario_bio.get("Phosphorus")
    if ca is not None and p is not None:
        scenario_bio["CaxP Product"] = ca * p
    ca_b = baseline_bio.get("Calcium")
    p_b = baseline_bio.get("Phosphorus")
    if ca_b is not None and p_b is not None:
        baseline_bio["CaxP Product"] = ca_b * p_b

    baseline_result = compute_hebcs(baseline_bio)
    scenario_result = compute_hebcs(scenario_bio)

    baseline_omega = baseline_result["omega"]
    scenario_omega = scenario_result["omega"]
    delta = scenario_omega - baseline_omega

    # Per-pathway deltas
    pathway_deltas: dict[str, WhatIfPathwayDelta] = {}
    for pname in baseline_result["pathways"]:
        b_score = baseline_result["pathways"][pname]["score"]
        s_score = scenario_result["pathways"][pname].get("score")
        pathway_deltas[pname] = WhatIfPathwayDelta(
            baseline_score=b_score,
            scenario_score=s_score,
            delta=(s_score - b_score) if (s_score is not None and b_score is not None) else None,
        )

    # Interpretation
    delta_pct = delta * 100
    if abs(delta_pct) < 0.5:
        interp = f"Minimal change (Δ = {delta_pct:+.1f}%). The selected parameter adjustments have little impact on your overall Ω."
    elif delta > 0:
        top_gainers = sorted(
            [(n, d.delta) for n, d in pathway_deltas.items() if d.delta and d.delta > 0],
            key=lambda x: x[1], reverse=True,
        )[:2]
        gainers_str = ", ".join(f"{n} (+{v:.2f})" for n, v in top_gainers)
        interp = (
            f"This intervention would improve your Ω by {delta_pct:+.1f}% "
            f"({baseline_omega:.3f} → {scenario_omega:.3f}). "
            f"Pathways gaining most: {gainers_str}."
        )
    else:
        top_losers = sorted(
            [(n, d.delta) for n, d in pathway_deltas.items() if d.delta and d.delta < 0],
            key=lambda x: x[1],
        )[:2]
        losers_str = ", ".join(f"{n} ({v:.2f})" for n, v in top_losers)
        interp = (
            f"This scenario worsens your Ω by {abs(delta_pct):.1f}% "
            f"({baseline_omega:.3f} → {scenario_omega:.3f}). "
            f"Most affected pathways: {losers_str}."
        )

    return WhatIfResponse(
        scenario_name=request.scenario_name,
        baseline_omega=baseline_omega,
        scenario_omega=scenario_omega,
        delta_omega=delta,
        delta_pct=delta_pct,
        pathway_deltas=pathway_deltas,
        overridden_biomarkers=list(overrides.keys()),
        interpretation=interp,
    )
