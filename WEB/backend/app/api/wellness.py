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

router = APIRouter()


async def _compute_wellness_score(user_id: int, db: AsyncSession) -> dict:
    """Compute wellness score from all available health data (deterministic, keyword-driven)."""
    today = date.today()
    cutoff = today - timedelta(days=30)
    scores = {}

    # Nutrition score (based on logging consistency)
    result = await db.execute(
        select(func.count(NutritionLog.id)).where(NutritionLog.user_id == user_id, NutritionLog.log_date >= cutoff)
    )
    nutr_count = result.scalar() or 0
    scores["nutrition"] = min(100, nutr_count * 3.3)  # ~30 entries for 100

    # Fitness score
    result = await db.execute(
        select(func.count(FitnessLog.id)).where(FitnessLog.user_id == user_id, FitnessLog.log_date >= cutoff)
    )
    fit_count = result.scalar() or 0
    scores["fitness"] = min(100, fit_count * 8.3)  # ~12 workouts for 100

    # Sleep score
    result = await db.execute(
        select(func.avg(SleepLog.total_hours)).where(SleepLog.user_id == user_id, SleepLog.sleep_date >= cutoff)
    )
    avg_sleep = result.scalar()
    scores["sleep"] = min(100, max(0, (avg_sleep or 0) / 8 * 100)) if avg_sleep else 50

    # Mood score
    result = await db.execute(
        select(func.avg(MoodEntry.mood_score)).where(MoodEntry.user_id == user_id, MoodEntry.entry_date >= cutoff)
    )
    avg_mood = result.scalar()
    scores["mood"] = min(100, (avg_mood or 5) / 10 * 100) if avg_mood else 50

    # Vitals score (based on presence of recent vitals)
    result = await db.execute(
        select(func.count(VitalsLog.id)).where(VitalsLog.user_id == user_id, VitalsLog.log_date >= cutoff)
    )
    vitals_count = result.scalar() or 0
    scores["vitals"] = min(100, vitals_count * 10)

    # Medication adherence (placeholder: based on having active meds logged)
    result = await db.execute(
        select(func.count(Medication.id)).where(Medication.user_id == user_id, Medication.is_active == True)
    )
    med_count = result.scalar() or 0
    scores["medication_adherence"] = 80 if med_count > 0 else 50

    overall = sum(scores.values()) / len(scores)

    # Explanation
    parts = []
    if scores["nutrition"] >= 70:
        parts.append("Great nutrition tracking consistency.")
    else:
        parts.append("Consider logging meals more consistently.")
    if scores["fitness"] >= 70:
        parts.append("Excellent fitness activity level.")
    else:
        parts.append("Try to add more physical activity.")
    if scores["sleep"] >= 70:
        parts.append("Good sleep patterns.")
    else:
        parts.append("Focus on improving sleep quality and duration.")

    return {
        "overall_score": round(overall, 1),
        "nutrition_score": round(scores["nutrition"], 1),
        "fitness_score": round(scores["fitness"], 1),
        "sleep_score": round(scores["sleep"], 1),
        "mood_score": round(scores["mood"], 1),
        "vitals_score": round(scores["vitals"], 1),
        "medication_adherence_score": round(scores["medication_adherence"], 1),
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
    # Fetch each user's most recent lab value per test_name
    result = await db.execute(
        select(
            LabResult.test_name,
            LabResult.value,
            LabResult.test_date,
        )
        .where(LabResult.user_id == current_user.id, LabResult.value.isnot(None))
        .order_by(LabResult.test_name, LabResult.test_date.desc())
    )
    rows = result.all()

    # Keep only the most recent value per analyte
    biomarker_values: dict[str, float] = {}
    latest_date: date | None = None
    seen: set[str] = set()
    for test_name, value, test_date in rows:
        if test_name not in seen:
            biomarker_values[test_name] = value
            seen.add(test_name)
            if latest_date is None or test_date > latest_date:
                latest_date = test_date

    result_data = compute_hebcs(biomarker_values)
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

    from app.schemas.wellness import HEBCSPathwayResult, HEBCSBiomarkerDetail
    pathway_response = {
        name: HEBCSPathwayResult(
            score=pdata["score"],
            weight=pdata["weight"],
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

    # Save score
    score_obj = WellnessScoreModel(
        user_id=current_user.id,
        score_date=today,
        **{k: v for k, v in data.items()},
    )
    db.add(score_obj)
    await db.flush()
    await db.refresh(score_obj)
    return score_obj


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
