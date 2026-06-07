"""Chart Dashboard API – provides aggregated, chart-ready data from all health domains."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, cast, Date as SADate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.nutrition import NutritionLog
from app.models.fitness import FitnessLog
from app.models.labs import LabResult
from app.models.mood import MoodEntry
from app.models.lifestyle import LifestyleEntry
from app.models.vitals import VitalsLog

router = APIRouter()

# ── Available datasets for the dashboard ────────────────────────────

DATASETS = {
    # Nutrition
    "calories":     {"model": NutritionLog, "date_col": "log_date", "value_col": "calories", "label": "Calories", "unit": "kcal", "domain": "nutrition"},
    "protein":      {"model": NutritionLog, "date_col": "log_date", "value_col": "protein_g", "label": "Protein", "unit": "g", "domain": "nutrition"},
    "carbs":        {"model": NutritionLog, "date_col": "log_date", "value_col": "carbs_g", "label": "Carbs", "unit": "g", "domain": "nutrition"},
    "fat":          {"model": NutritionLog, "date_col": "log_date", "value_col": "fat_g", "label": "Fat", "unit": "g", "domain": "nutrition"},
    "fiber":        {"model": NutritionLog, "date_col": "log_date", "value_col": "fiber_g", "label": "Fiber", "unit": "g", "domain": "nutrition"},
    "sugar":        {"model": NutritionLog, "date_col": "log_date", "value_col": "sugar_g", "label": "Sugar", "unit": "g", "domain": "nutrition"},
    "sodium":       {"model": NutritionLog, "date_col": "log_date", "value_col": "sodium_mg", "label": "Sodium", "unit": "mg", "domain": "nutrition"},
    "potassium":    {"model": NutritionLog, "date_col": "log_date", "value_col": "potassium_mg", "label": "Potassium", "unit": "mg", "domain": "nutrition"},
    "cholesterol":  {"model": NutritionLog, "date_col": "log_date", "value_col": "cholesterol_mg", "label": "Cholesterol", "unit": "mg", "domain": "nutrition"},
    "water":        {"model": NutritionLog, "date_col": "log_date", "value_col": "water_ml", "label": "Water Intake", "unit": "mL", "domain": "nutrition"},
    "caffeine":     {"model": NutritionLog, "date_col": "log_date", "value_col": "caffeine_mg", "label": "Caffeine", "unit": "mg", "domain": "nutrition"},

    # Fitness
    "duration":     {"model": FitnessLog, "date_col": "log_date", "value_col": "duration_minutes", "label": "Exercise Duration", "unit": "min", "domain": "fitness"},
    "distance":     {"model": FitnessLog, "date_col": "log_date", "value_col": "distance_km", "label": "Distance", "unit": "km", "domain": "fitness"},
    "calories_burned": {"model": FitnessLog, "date_col": "log_date", "value_col": "calories_burned", "label": "Calories Burned", "unit": "kcal", "domain": "fitness"},
    "heart_rate_avg": {"model": FitnessLog, "date_col": "log_date", "value_col": "heart_rate_avg", "label": "Avg Heart Rate", "unit": "bpm", "domain": "fitness"},
    "steps":        {"model": FitnessLog, "date_col": "log_date", "value_col": "steps", "label": "Steps", "unit": "steps", "domain": "fitness"},

    # Mood
    "mood_score":   {"model": MoodEntry, "date_col": "entry_date", "value_col": "mood_score", "label": "Mood Score", "unit": "/10", "domain": "mood"},
    "energy_level": {"model": MoodEntry, "date_col": "entry_date", "value_col": "energy_level", "label": "Energy Level", "unit": "/10", "domain": "mood"},
    "stress_level": {"model": MoodEntry, "date_col": "entry_date", "value_col": "stress_level", "label": "Stress Level", "unit": "/10", "domain": "mood"},
    "anxiety_level":{"model": MoodEntry, "date_col": "entry_date", "value_col": "anxiety_level", "label": "Anxiety Level", "unit": "/10", "domain": "mood"},
    "sleep_quality": {"model": MoodEntry, "date_col": "entry_date", "value_col": "sleep_quality", "label": "Sleep Quality", "unit": "/10", "domain": "mood"},
    "sleep_hours":  {"model": MoodEntry, "date_col": "entry_date", "value_col": "sleep_hours", "label": "Sleep Hours", "unit": "hrs", "domain": "mood"},

    # Vitals
    "bp_systolic":  {"model": VitalsLog, "date_col": "log_date", "value_col": "blood_pressure_systolic", "label": "Systolic BP", "unit": "mmHg", "domain": "vitals"},
    "bp_diastolic": {"model": VitalsLog, "date_col": "log_date", "value_col": "blood_pressure_diastolic", "label": "Diastolic BP", "unit": "mmHg", "domain": "vitals"},
    "heart_rate":   {"model": VitalsLog, "date_col": "log_date", "value_col": "heart_rate_bpm", "label": "Heart Rate", "unit": "bpm", "domain": "vitals"},
    "temperature":  {"model": VitalsLog, "date_col": "log_date", "value_col": "body_temperature_c", "label": "Body Temperature", "unit": "°C", "domain": "vitals"},
    "spo2":         {"model": VitalsLog, "date_col": "log_date", "value_col": "blood_oxygen_pct", "label": "SpO₂", "unit": "%", "domain": "vitals"},
    "glucose":      {"model": VitalsLog, "date_col": "log_date", "value_col": "blood_glucose_mg_dl", "label": "Blood Glucose", "unit": "mg/dL", "domain": "vitals"},
    "weight":       {"model": VitalsLog, "date_col": "log_date", "value_col": "weight_kg", "label": "Weight", "unit": "kg", "domain": "vitals"},
    "bmi":          {"model": VitalsLog, "date_col": "log_date", "value_col": "bmi", "label": "BMI", "unit": "", "domain": "vitals"},
    "body_fat":     {"model": VitalsLog, "date_col": "log_date", "value_col": "body_fat_pct", "label": "Body Fat %", "unit": "%", "domain": "vitals"},
    "pain_level":   {"model": VitalsLog, "date_col": "log_date", "value_col": "pain_level", "label": "Pain Level", "unit": "/10", "domain": "vitals"},

    # Lifestyle
    "ls_weight":    {"model": LifestyleEntry, "date_col": "entry_date", "value_col": "weight_kg", "label": "Weight (Lifestyle)", "unit": "kg", "domain": "lifestyle"},
    "ls_bp_sys":    {"model": LifestyleEntry, "date_col": "entry_date", "value_col": "blood_pressure_systolic", "label": "Systolic BP (LS)", "unit": "mmHg", "domain": "lifestyle"},
    "ls_bp_dia":    {"model": LifestyleEntry, "date_col": "entry_date", "value_col": "blood_pressure_diastolic", "label": "Diastolic BP (LS)", "unit": "mmHg", "domain": "lifestyle"},
    "ls_resting_hr":{"model": LifestyleEntry, "date_col": "entry_date", "value_col": "resting_heart_rate", "label": "Resting HR (LS)", "unit": "bpm", "domain": "lifestyle"},
    "screen_time":  {"model": LifestyleEntry, "date_col": "entry_date", "value_col": "screen_time_minutes", "label": "Screen Time", "unit": "min", "domain": "lifestyle"},
    "outdoor_time": {"model": LifestyleEntry, "date_col": "entry_date", "value_col": "outdoor_time_minutes", "label": "Outdoor Time", "unit": "min", "domain": "lifestyle"},
}


@router.get("/datasets")
async def list_datasets(current_user: User = Depends(get_current_user)):
    """Return available dataset definitions grouped by domain."""
    by_domain: dict[str, list] = {}
    for key, ds in DATASETS.items():
        by_domain.setdefault(ds["domain"], []).append({
            "key": key,
            "label": ds["label"],
            "unit": ds["unit"],
        })
    return by_domain


@router.get("/data")
async def get_chart_data(
    datasets: str = Query(..., description="Comma-separated dataset keys, e.g. 'calories,steps,mood_score'"),
    days: int = Query(90, ge=7, le=730, description="Number of past days to include"),
    aggregation: str = Query("daily", description="daily | weekly | monthly"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch time-series data for one or more datasets."""
    keys = [k.strip() for k in datasets.split(",") if k.strip()]
    if not keys:
        raise HTTPException(400, "At least one dataset key is required")
    invalid = [k for k in keys if k not in DATASETS]
    if invalid:
        raise HTTPException(400, f"Unknown dataset keys: {', '.join(invalid)}")

    cutoff = date.today() - timedelta(days=days)
    result = {}

    for key in keys:
        ds = DATASETS[key]
        model = ds["model"]
        date_col = getattr(model, ds["date_col"])
        value_col = getattr(model, ds["value_col"])

        if aggregation == "daily":
            q = (
                select(
                    cast(date_col, SADate).label("date"),
                    func.avg(value_col).label("value"),
                    func.min(value_col).label("min"),
                    func.max(value_col).label("max"),
                    func.count().label("count"),
                )
                .where(model.user_id == current_user.id, date_col >= cutoff, value_col.isnot(None))
                .group_by(cast(date_col, SADate))
                .order_by(cast(date_col, SADate))
            )
        elif aggregation == "weekly":
            week_expr = func.date_trunc("week", date_col)
            q = (
                select(
                    cast(week_expr, SADate).label("date"),
                    func.avg(value_col).label("value"),
                    func.min(value_col).label("min"),
                    func.max(value_col).label("max"),
                    func.count().label("count"),
                )
                .where(model.user_id == current_user.id, date_col >= cutoff, value_col.isnot(None))
                .group_by(week_expr)
                .order_by(week_expr)
            )
        else:  # monthly
            month_expr = func.date_trunc("month", date_col)
            q = (
                select(
                    cast(month_expr, SADate).label("date"),
                    func.avg(value_col).label("value"),
                    func.min(value_col).label("min"),
                    func.max(value_col).label("max"),
                    func.count().label("count"),
                )
                .where(model.user_id == current_user.id, date_col >= cutoff, value_col.isnot(None))
                .group_by(month_expr)
                .order_by(month_expr)
            )

        rows = await db.execute(q)
        result[key] = {
            "label": ds["label"],
            "unit": ds["unit"],
            "domain": ds["domain"],
            "points": [
                {
                    "date": str(row.date),
                    "value": round(float(row.value), 2) if row.value else None,
                    "min": round(float(row.min), 2) if row.min else None,
                    "max": round(float(row.max), 2) if row.max else None,
                    "count": row.count,
                }
                for row in rows
            ],
        }

    return result


@router.get("/correlate")
async def correlate_datasets(
    dataset_a: str = Query(..., description="First dataset key"),
    dataset_b: str = Query(..., description="Second dataset key"),
    days: int = Query(90, ge=7, le=730),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return paired data points for two datasets (scatter / correlation chart).

    Joins on date so only dates with both values are included.
    """
    for k in (dataset_a, dataset_b):
        if k not in DATASETS:
            raise HTTPException(400, f"Unknown dataset key: {k}")

    cutoff = date.today() - timedelta(days=days)
    pairs = []

    for key in (dataset_a, dataset_b):
        ds = DATASETS[key]
        model = ds["model"]
        date_col = getattr(model, ds["date_col"])
        value_col = getattr(model, ds["value_col"])
        q = (
            select(
                cast(date_col, SADate).label("date"),
                func.avg(value_col).label("value"),
            )
            .where(model.user_id == current_user.id, date_col >= cutoff, value_col.isnot(None))
            .group_by(cast(date_col, SADate))
            .order_by(cast(date_col, SADate))
        )
        rows = await db.execute(q)
        pairs.append({str(r.date): round(float(r.value), 2) for r in rows})

    # Merge on date
    common_dates = sorted(set(pairs[0].keys()) & set(pairs[1].keys()))
    return {
        "x": {"key": dataset_a, "label": DATASETS[dataset_a]["label"], "unit": DATASETS[dataset_a]["unit"]},
        "y": {"key": dataset_b, "label": DATASETS[dataset_b]["label"], "unit": DATASETS[dataset_b]["unit"]},
        "points": [
            {"date": d, "x": pairs[0][d], "y": pairs[1][d]}
            for d in common_dates
        ],
    }


@router.get("/summary")
async def dataset_summary(
    dataset: str = Query(..., description="Dataset key"),
    days: int = Query(90, ge=7, le=730),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return statistical summary for a dataset (avg, min, max, count, stddev, trend)."""
    if dataset not in DATASETS:
        raise HTTPException(400, f"Unknown dataset key: {dataset}")

    ds = DATASETS[dataset]
    model = ds["model"]
    date_col = getattr(model, ds["date_col"])
    value_col = getattr(model, ds["value_col"])
    cutoff = date.today() - timedelta(days=days)

    q = select(
        func.avg(value_col).label("avg"),
        func.min(value_col).label("min"),
        func.max(value_col).label("max"),
        func.count().label("count"),
        func.stddev(value_col).label("stddev"),
    ).where(model.user_id == current_user.id, date_col >= cutoff, value_col.isnot(None))

    result = await db.execute(q)
    row = result.one()

    # Simple trend: compare first-half avg vs second-half avg
    mid_date = cutoff + timedelta(days=days // 2)
    q1 = select(func.avg(value_col)).where(
        model.user_id == current_user.id, date_col >= cutoff, date_col < mid_date, value_col.isnot(None)
    )
    q2 = select(func.avg(value_col)).where(
        model.user_id == current_user.id, date_col >= mid_date, value_col.isnot(None)
    )
    r1 = await db.execute(q1)
    r2 = await db.execute(q2)
    avg1 = r1.scalar()
    avg2 = r2.scalar()

    trend = "stable"
    if avg1 and avg2:
        pct = ((avg2 - avg1) / avg1) * 100 if avg1 != 0 else 0
        if pct > 5:
            trend = "increasing"
        elif pct < -5:
            trend = "decreasing"

    return {
        "key": dataset,
        "label": ds["label"],
        "unit": ds["unit"],
        "days": days,
        "avg": round(float(row.avg), 2) if row.avg else None,
        "min": round(float(row.min), 2) if row.min else None,
        "max": round(float(row.max), 2) if row.max else None,
        "count": row.count,
        "stddev": round(float(row.stddev), 2) if row.stddev else None,
        "trend": trend,
    }
