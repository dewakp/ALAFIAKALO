"""Chart Dashboard API – provides aggregated, chart-ready data from all health domains."""

from datetime import date, timedelta
from statistics import mean, stdev

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, cast, or_, Date as SADate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.chronic_conditions import TherapySession
from app.models.elimination import BowelMovement, UrinationLog, VomitingLog
from app.models.nutrition import NutritionLog
from app.models.fitness import FitnessLog
from app.models.labs import LabResult
from app.models.mood import MoodEntry
from app.models.lifestyle import LifestyleEntry
from app.models.peritoneal_dialysis import PDSession
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


# ── Composite weight series ─────────────────────────────────────────
#
# Body weight is recorded in many places: vitals logs, lifestyle entries,
# fitness logs, meal (food & meds) logs, elimination logs, dialysis therapy
# sessions (HD + PD) and lab reports. The procedure below unions them all
# into one chronological series with per-day mean/min/max/count, a 7-day
# rolling average (the same smoothing used for therapy dry-weight tracking),
# and overall summary statistics.

# Plausible human body-weight bounds — guards against unit mix-ups and junk.
WEIGHT_KG_MIN, WEIGHT_KG_MAX = 20.0, 500.0

# (source name, model, date column, weight columns)
WEIGHT_SOURCES = [
    ("vitals",      VitalsLog,      "log_date",       ["weight_kg"]),
    ("lifestyle",   LifestyleEntry, "entry_date",     ["weight_kg"]),
    ("fitness",     FitnessLog,     "log_date",       ["weight_kg"]),
    ("meals",       NutritionLog,   "log_date",       ["pre_meal_weight_kg", "post_meal_weight_kg"]),
    ("elimination", BowelMovement,  "log_date",       ["pre_event_weight_kg", "post_event_weight_kg"]),
    ("elimination", UrinationLog,   "log_date",       ["pre_event_weight_kg", "post_event_weight_kg"]),
    ("elimination", VomitingLog,    "log_date",       ["pre_event_weight_kg", "post_event_weight_kg"]),
    ("therapy",     TherapySession, "scheduled_date", ["pre_dialysis_weight_kg", "post_dialysis_weight_kg"]),
    ("therapy",     PDSession,      "session_date",   ["pre_weight_kg", "post_weight_kg"]),
]

# Virtual datasets exposed through the regular chart endpoints.
VIRTUAL_DATASETS = {
    "weight_all":    {"label": "Weight (All Sources)", "unit": "kg", "domain": "weight"},
    "weight_all_7d": {"label": "Weight 7-Day Rolling Avg", "unit": "kg", "domain": "weight"},
}


async def _collect_weight_observations(user_id: int, db: AsyncSession, cutoff: date) -> list[tuple]:
    """Retrieve every weight measurement for a user across all record types.

    Returns [(date, value_kg, source), …] sorted chronologically.
    """
    obs: list[tuple] = []
    for source, model, date_name, col_names in WEIGHT_SOURCES:
        date_col = getattr(model, date_name)
        cols = [getattr(model, c) for c in col_names]
        q = (
            select(cast(date_col, SADate).label("d"), *cols)
            .where(
                model.user_id == user_id,
                date_col >= cutoff,
                or_(*[c.isnot(None) for c in cols]),
            )
        )
        for row in await db.execute(q):
            for v in row[1:]:
                if v is not None and WEIGHT_KG_MIN <= v <= WEIGHT_KG_MAX:
                    obs.append((row.d, float(v), source))

    # Lab reports: any result named like "Weight…" in kg or lb (converted).
    q = (
        select(cast(LabResult.test_date, SADate).label("d"), LabResult.value, LabResult.unit)
        .where(
            LabResult.user_id == user_id,
            LabResult.test_date >= cutoff,
            LabResult.value.isnot(None),
            LabResult.test_name.ilike("%weight%"),
        )
    )
    for row in await db.execute(q):
        unit = (row.unit or "kg").strip().lower()
        if unit in ("kg", "kgs", "kilogram", "kilograms"):
            v = float(row.value)
        elif unit in ("lb", "lbs", "pound", "pounds"):
            v = float(row.value) * 0.45359237
        else:
            continue
        if WEIGHT_KG_MIN <= v <= WEIGHT_KG_MAX:
            obs.append((row.d, round(v, 2), "labs"))

    # Deliberately excluded: therapy_sessions.previous_post_weight_kg (a copy of
    # an earlier session's measurement — would double-count and its true date is
    # unknown), food serving weights, and undated profile snapshots.
    obs.sort(key=lambda o: o[0])
    return obs


async def _weight_references(user_id: int, db: AsyncSession) -> dict:
    """Reference weights that are targets/snapshots rather than dated measurements:
    latest dialysis dry weight and the profile's current/target weight."""
    refs: dict[str, float | None] = {}
    row = (
        await db.execute(
            select(TherapySession.dry_weight_kg)
            .where(TherapySession.user_id == user_id, TherapySession.dry_weight_kg.isnot(None))
            .order_by(TherapySession.scheduled_date.desc())
            .limit(1)
        )
    ).first()
    refs["dry_weight_kg"] = float(row.dry_weight_kg) if row else None

    urow = (
        await db.execute(
            select(User.current_weight_kg, User.target_weight_kg).where(User.id == user_id)
        )
    ).first()
    refs["profile_current_weight_kg"] = float(urow.current_weight_kg) if urow and urow.current_weight_kg else None
    refs["profile_target_weight_kg"] = float(urow.target_weight_kg) if urow and urow.target_weight_kg else None
    return refs


def _bucket_date(d: date, aggregation: str) -> date:
    if aggregation == "weekly":
        return d - timedelta(days=d.weekday())  # Monday of that week
    if aggregation == "monthly":
        return d.replace(day=1)
    return d


def build_weight_series(obs: list[tuple], aggregation: str = "daily") -> dict:
    """Turn raw observations into a chart-ready series + summary statistics.

    Points carry value (mean), min, max, count, per-source counts and — for
    daily aggregation — a trailing 7-day rolling average of the daily means.
    """
    if not obs:
        return {"points": [], "summary": {"count": 0, "avg": None, "stddev": None,
                                          "min": None, "max": None, "sources": {}, "trend": "stable"}}

    # Daily means first (they feed the rolling average regardless of bucket).
    by_day: dict[date, dict] = {}
    for d, v, src in obs:
        rec = by_day.setdefault(d, {"values": [], "sources": {}})
        rec["values"].append(v)
        rec["sources"][src] = rec["sources"].get(src, 0) + 1
    days_sorted = sorted(by_day)
    daily_mean = {d: mean(by_day[d]["values"]) for d in days_sorted}

    # Trailing 7-day rolling average over daily means.
    rolling: dict[date, float] = {}
    for d in days_sorted:
        window = [daily_mean[x] for x in days_sorted if d - timedelta(days=6) <= x <= d]
        rolling[d] = mean(window)

    # Bucket into the requested aggregation.
    buckets: dict[date, dict] = {}
    for d in days_sorted:
        b = _bucket_date(d, aggregation)
        rec = buckets.setdefault(b, {"values": [], "sources": {}, "rolling": []})
        rec["values"].extend(by_day[d]["values"])
        rec["rolling"].append(rolling[d])
        for s, n in by_day[d]["sources"].items():
            rec["sources"][s] = rec["sources"].get(s, 0) + n

    points = [
        {
            "date": str(b),
            "value": round(mean(rec["values"]), 2),
            "min": round(min(rec["values"]), 2),
            "max": round(max(rec["values"]), 2),
            "count": len(rec["values"]),
            "rolling_7d": round(mean(rec["rolling"]), 2),
            "sources": rec["sources"],
        }
        for b, rec in sorted(buckets.items())
    ]

    # Overall summary over the raw observations.
    values = [v for _, v, _ in obs]
    src_totals: dict[str, int] = {}
    for _, _, s in obs:
        src_totals[s] = src_totals.get(s, 0) + 1

    # Trend: first-half vs second-half of daily means.
    trend = "stable"
    if len(days_sorted) >= 2:
        mid = days_sorted[len(days_sorted) // 2]
        first = [daily_mean[d] for d in days_sorted if d < mid]
        second = [daily_mean[d] for d in days_sorted if d >= mid]
        if first and second and mean(first) != 0:
            pct = (mean(second) - mean(first)) / mean(first) * 100
            if pct > 2:
                trend = "increasing"
            elif pct < -2:
                trend = "decreasing"

    summary = {
        "count": len(values),
        "avg": round(mean(values), 2),
        "stddev": round(stdev(values), 2) if len(values) > 1 else None,
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "sources": src_totals,
        "trend": trend,
    }
    return {"points": points, "summary": summary}


@router.get("/weight-series")
async def get_weight_series(
    days: int = Query(365, ge=7, le=730, description="Number of past days to include"),
    aggregation: str = Query("daily", description="daily | weekly | monthly"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Composite weight time series unified from every record type that captures
    weight: vitals, lifestyle, fitness, meals (food & meds log), elimination,
    dialysis therapy sessions (HD/PD) and lab reports.

    Includes per-point mean/min/max/count, a 7-day rolling average, and overall
    summary statistics (avg, std dev, min, max, per-source counts, trend).
    """
    cutoff = date.today() - timedelta(days=days)
    obs = await _collect_weight_observations(current_user.id, db, cutoff)
    series = build_weight_series(obs, aggregation)
    series["summary"].update(await _weight_references(current_user.id, db))
    return {
        "label": "Weight (All Sources)",
        "unit": "kg",
        "days": days,
        "aggregation": aggregation,
        **series,
    }


@router.get("/datasets")
async def list_datasets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return available dataset definitions grouped by domain.

    Each dataset carries a `count` of the user's non-null entries so the UI can
    distinguish populated metrics from ones with no data yet.
    """
    # One query per model: COUNT(col) counts non-null values per dataset.
    by_model: dict = {}
    for key, ds in DATASETS.items():
        by_model.setdefault(ds["model"], []).append(key)

    counts: dict[str, int] = {}
    for model, keys in by_model.items():
        cols = [func.count(getattr(model, DATASETS[k]["value_col"])).label(k) for k in keys]
        row = (await db.execute(select(*cols).where(model.user_id == current_user.id))).one()
        counts.update({k: getattr(row, k) or 0 for k in keys})

    by_domain: dict[str, list] = {}
    for key, ds in DATASETS.items():
        by_domain.setdefault(ds["domain"], []).append({
            "key": key,
            "label": ds["label"],
            "unit": ds["unit"],
            "count": counts.get(key, 0),
        })

    # Composite weight datasets — count is the total observations across sources.
    weight_obs = await _collect_weight_observations(current_user.id, db, date(1900, 1, 1))
    for key, ds in VIRTUAL_DATASETS.items():
        by_domain.setdefault(ds["domain"], []).append({
            "key": key,
            "label": ds["label"],
            "unit": ds["unit"],
            "count": len(weight_obs),
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
    invalid = [k for k in keys if k not in DATASETS and k not in VIRTUAL_DATASETS]
    if invalid:
        raise HTTPException(400, f"Unknown dataset keys: {', '.join(invalid)}")

    cutoff = date.today() - timedelta(days=days)
    result = {}

    # Composite weight datasets share one observation sweep.
    virtual_keys = [k for k in keys if k in VIRTUAL_DATASETS]
    if virtual_keys:
        obs = await _collect_weight_observations(current_user.id, db, cutoff)
        series = build_weight_series(obs, aggregation)
        for key in virtual_keys:
            vds = VIRTUAL_DATASETS[key]
            result[key] = {
                "label": vds["label"],
                "unit": vds["unit"],
                "domain": vds["domain"],
                "points": [
                    {
                        "date": p["date"],
                        "value": p["rolling_7d"] if key == "weight_all_7d" else p["value"],
                        "min": p["min"],
                        "max": p["max"],
                        "count": p["count"],
                        "sources": p["sources"],
                    }
                    for p in series["points"]
                ],
            }

    for key in keys:
        if key in VIRTUAL_DATASETS:
            continue
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
                    "value": round(float(row.value), 2) if row.value is not None else None,
                    "min": round(float(row.min), 2) if row.min is not None else None,
                    "max": round(float(row.max), 2) if row.max is not None else None,
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
        if k not in DATASETS and k not in VIRTUAL_DATASETS:
            raise HTTPException(400, f"Unknown dataset key: {k}")

    cutoff = date.today() - timedelta(days=days)
    pairs = []

    for key in (dataset_a, dataset_b):
        if key in VIRTUAL_DATASETS:
            obs = await _collect_weight_observations(current_user.id, db, cutoff)
            pts = build_weight_series(obs)["points"]
            field = "rolling_7d" if key == "weight_all_7d" else "value"
            pairs.append({p["date"]: p[field] for p in pts})
            continue
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
    def _meta(key):
        return DATASETS.get(key) or VIRTUAL_DATASETS[key]

    common_dates = sorted(set(pairs[0].keys()) & set(pairs[1].keys()))
    return {
        "x": {"key": dataset_a, "label": _meta(dataset_a)["label"], "unit": _meta(dataset_a)["unit"]},
        "y": {"key": dataset_b, "label": _meta(dataset_b)["label"], "unit": _meta(dataset_b)["unit"]},
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
    if dataset not in DATASETS and dataset not in VIRTUAL_DATASETS:
        raise HTTPException(400, f"Unknown dataset key: {dataset}")

    if dataset in VIRTUAL_DATASETS:
        cutoff = date.today() - timedelta(days=days)
        obs = await _collect_weight_observations(current_user.id, db, cutoff)
        if dataset == "weight_all_7d":
            # Summarize the smoothed series rather than raw observations.
            pts = build_weight_series(obs)["points"]
            vals = [p["rolling_7d"] for p in pts]
            obs = [(date.fromisoformat(p["date"]), v, "rolling") for p, v in zip(pts, vals)]
        series = build_weight_series(obs)
        s = series["summary"]
        s.update(await _weight_references(current_user.id, db))
        vds = VIRTUAL_DATASETS[dataset]
        return {"key": dataset, "label": vds["label"], "unit": vds["unit"], "days": days, **s}

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
        "avg": round(float(row.avg), 2) if row.avg is not None else None,
        "min": round(float(row.min), 2) if row.min is not None else None,
        "max": round(float(row.max), 2) if row.max is not None else None,
        "count": row.count,
        "stddev": round(float(row.stddev), 2) if row.stddev is not None else None,
        "trend": trend,
    }
