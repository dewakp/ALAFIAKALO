"""Daily health-signal collector — the shared substrate for ALAFIA's pattern and
forecast engines (Basis req #3/#4/#5: overlay collected data, find relationships,
predict states).

Each "signal" is a per-day numeric series for one user, aggregated from a logged
domain (diet, vitals, activity, mood, sleep, symptoms, labs). Domains overlaid on
one timeline are what make cross-domain relationships and forecasts possible.

Pure-Python (no numpy/pandas) to keep the backend dependency-free.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nutrition import NutritionLog
from app.models.vitals import VitalsLog
from app.models.lifestyle import LifestyleEntry
from app.models.fitness import FitnessLog
from app.models.mood import MoodEntry
from app.models.sleep import SleepLog
from app.models.conditions import SymptomLog
from app.models.labs import LabResult
from app.models.ground_truth import EnvSocialLog

# Aggregation per signal: "sum" (intake/activity totals) or "mean" (measurements).
SUM = "sum"
MEAN = "mean"

# Human-readable labels + domain for each signal key. Domain drives the
# "cross-domain only" filter (the interesting relationships span domains).
SIGNAL_META: dict[str, dict[str, str]] = {
    "diet.calories":        {"label": "Calories", "domain": "diet", "agg": SUM, "unit": "kcal"},
    "diet.protein_g":       {"label": "Protein", "domain": "diet", "agg": SUM, "unit": "g"},
    "diet.carbs_g":         {"label": "Carbs", "domain": "diet", "agg": SUM, "unit": "g"},
    "diet.fat_g":           {"label": "Fat", "domain": "diet", "agg": SUM, "unit": "g"},
    "diet.sugar_g":         {"label": "Sugar", "domain": "diet", "agg": SUM, "unit": "g"},
    "diet.sodium_mg":       {"label": "Sodium", "domain": "diet", "agg": SUM, "unit": "mg"},
    "diet.potassium_mg":    {"label": "Potassium", "domain": "diet", "agg": SUM, "unit": "mg"},
    "diet.phosphorus_mg":   {"label": "Phosphorus", "domain": "diet", "agg": SUM, "unit": "mg"},
    "diet.water_ml":        {"label": "Fluid intake", "domain": "diet", "agg": SUM, "unit": "mL"},
    "vital.weight_kg":      {"label": "Weight", "domain": "vital", "agg": MEAN, "unit": "kg"},
    "vital.bp_systolic":    {"label": "Systolic BP", "domain": "vital", "agg": MEAN, "unit": "mmHg"},
    "vital.bp_diastolic":   {"label": "Diastolic BP", "domain": "vital", "agg": MEAN, "unit": "mmHg"},
    "vital.heart_rate":     {"label": "Heart rate", "domain": "vital", "agg": MEAN, "unit": "bpm"},
    "vital.spo2":           {"label": "Blood oxygen", "domain": "vital", "agg": MEAN, "unit": "%"},
    "vital.glucose":        {"label": "Blood glucose", "domain": "vital", "agg": MEAN, "unit": "mg/dL"},
    "vital.temperature_c":  {"label": "Body temperature", "domain": "vital", "agg": MEAN, "unit": "°C"},
    "activity.duration_min": {"label": "Exercise duration", "domain": "activity", "agg": SUM, "unit": "min"},
    "activity.calories":    {"label": "Calories burned", "domain": "activity", "agg": SUM, "unit": "kcal"},
    "activity.steps":       {"label": "Steps", "domain": "activity", "agg": SUM, "unit": ""},
    "mood.score":           {"label": "Mood", "domain": "mood", "agg": MEAN, "unit": "/10"},
    "mood.energy":          {"label": "Energy", "domain": "mood", "agg": MEAN, "unit": "/10"},
    "mood.stress":          {"label": "Stress", "domain": "mood", "agg": MEAN, "unit": "/10"},
    "sleep.hours":          {"label": "Sleep hours", "domain": "sleep", "agg": MEAN, "unit": "h"},
    "sleep.quality":        {"label": "Sleep quality", "domain": "sleep", "agg": MEAN, "unit": "/10"},
    "sleep.awakenings":     {"label": "Night awakenings", "domain": "sleep", "agg": MEAN, "unit": ""},
    "symptom.count":        {"label": "Symptom count", "domain": "symptom", "agg": SUM, "unit": ""},
    "symptom.severity_max": {"label": "Worst symptom severity", "domain": "symptom", "agg": MEAN, "unit": "/10"},
    "env.aqi":              {"label": "Air quality index", "domain": "env", "agg": MEAN, "unit": "AQI"},
    "env.ambient_temp_c":   {"label": "Ambient temperature", "domain": "env", "agg": MEAN, "unit": "°C"},
    "env.humidity_pct":     {"label": "Humidity", "domain": "env", "agg": MEAN, "unit": "%"},
    "social.work_stress":   {"label": "Work stress", "domain": "social", "agg": MEAN, "unit": "/10"},
    "social.financial_stress": {"label": "Financial stress", "domain": "social", "agg": MEAN, "unit": "/10"},
    "social.support":       {"label": "Social support", "domain": "social", "agg": MEAN, "unit": "/10"},
}


def signal_domain(key: str) -> str:
    meta = SIGNAL_META.get(key)
    if meta:
        return meta["domain"]
    return key.split(".")[0] if "." in key else "lab"


def signal_label(key: str) -> str:
    meta = SIGNAL_META.get(key)
    if meta:
        return meta["label"]
    if key.startswith("lab."):
        return f"Lab: {key[4:]}"
    return key


async def collect_signals(
    db: AsyncSession, user_id: int, start: date, end: date
) -> dict[str, dict[date, float]]:
    """Return {signal_key: {date: value}} for every available signal in range."""
    # accumulator[signal][date] -> list of raw values for that day
    acc: dict[str, dict[date, list[float]]] = defaultdict(lambda: defaultdict(list))

    def add(signal: str, d: date | None, v) -> None:
        if d is None or v is None:
            return
        acc[signal][d].append(float(v))

    # ── Diet (NutritionLog) ──
    rows = (await db.execute(
        select(NutritionLog).where(
            NutritionLog.user_id == user_id,
            NutritionLog.log_date >= start, NutritionLog.log_date <= end,
        )
    )).scalars().all()
    for r in rows:
        add("diet.calories", r.log_date, r.calories)
        add("diet.protein_g", r.log_date, r.protein_g)
        add("diet.carbs_g", r.log_date, r.carbs_g)
        add("diet.fat_g", r.log_date, r.fat_g)
        add("diet.sugar_g", r.log_date, r.sugar_g)
        add("diet.sodium_mg", r.log_date, r.sodium_mg)
        add("diet.potassium_mg", r.log_date, r.potassium_mg)
        add("diet.phosphorus_mg", r.log_date, r.phosphorus_mg)
        add("diet.water_ml", r.log_date, r.water_ml)

    # ── Vitals (VitalsLog + LifestyleEntry, merged) ──
    vrows = (await db.execute(
        select(VitalsLog).where(
            VitalsLog.user_id == user_id,
            VitalsLog.log_date >= start, VitalsLog.log_date <= end,
        )
    )).scalars().all()
    for r in vrows:
        add("vital.weight_kg", r.log_date, r.weight_kg)
        add("vital.bp_systolic", r.log_date, r.blood_pressure_systolic)
        add("vital.bp_diastolic", r.log_date, r.blood_pressure_diastolic)
        add("vital.heart_rate", r.log_date, r.heart_rate_bpm)
        add("vital.spo2", r.log_date, r.blood_oxygen_pct)
        add("vital.glucose", r.log_date, r.blood_glucose_mg_dl)
        add("vital.temperature_c", r.log_date, r.body_temperature_c)

    lrows = (await db.execute(
        select(LifestyleEntry).where(
            LifestyleEntry.user_id == user_id,
            LifestyleEntry.entry_date >= start, LifestyleEntry.entry_date <= end,
        )
    )).scalars().all()
    for r in lrows:
        add("vital.weight_kg", r.entry_date, r.weight_kg)
        add("vital.bp_systolic", r.entry_date, r.blood_pressure_systolic)
        add("vital.bp_diastolic", r.entry_date, r.blood_pressure_diastolic)
        add("vital.heart_rate", r.entry_date, r.resting_heart_rate)

    # ── Activity (FitnessLog) ──
    frows = (await db.execute(
        select(FitnessLog).where(
            FitnessLog.user_id == user_id,
            FitnessLog.log_date >= start, FitnessLog.log_date <= end,
        )
    )).scalars().all()
    for r in frows:
        add("activity.duration_min", r.log_date, r.duration_minutes)
        add("activity.calories", r.log_date, r.calories_burned)
        add("activity.steps", r.log_date, r.steps)

    # ── Mood (MoodEntry) ──
    mrows = (await db.execute(
        select(MoodEntry).where(
            MoodEntry.user_id == user_id,
            MoodEntry.entry_date >= start, MoodEntry.entry_date <= end,
        )
    )).scalars().all()
    for r in mrows:
        add("mood.score", r.entry_date, r.mood_score)
        add("mood.energy", r.entry_date, r.energy_level)
        add("mood.stress", r.entry_date, r.stress_level)

    # ── Sleep (SleepLog) ──
    srows = (await db.execute(
        select(SleepLog).where(
            SleepLog.user_id == user_id,
            SleepLog.sleep_date >= start, SleepLog.sleep_date <= end,
        )
    )).scalars().all()
    for r in srows:
        add("sleep.hours", r.sleep_date, r.total_hours)
        add("sleep.quality", r.sleep_date, r.quality_score)
        add("sleep.awakenings", r.sleep_date, r.times_awakened)

    # ── Symptoms (SymptomLog: daily count + worst severity) ──
    symrows = (await db.execute(
        select(SymptomLog).where(
            SymptomLog.user_id == user_id,
            SymptomLog.log_date >= start, SymptomLog.log_date <= end,
        )
    )).scalars().all()
    for r in symrows:
        add("symptom.count", r.log_date, 1)
        if r.severity is not None:
            add("symptom.severity_max", r.log_date, r.severity)

    # ── Environmental / social ground-truth factors (time-varying) ──
    erows = (await db.execute(
        select(EnvSocialLog).where(
            EnvSocialLog.user_id == user_id,
            EnvSocialLog.log_date >= start, EnvSocialLog.log_date <= end,
        )
    )).scalars().all()
    for r in erows:
        add("env.aqi", r.log_date, r.air_quality_index)
        add("env.ambient_temp_c", r.log_date, r.ambient_temp_c)
        add("env.humidity_pct", r.log_date, r.humidity_pct)
        add("social.work_stress", r.log_date, r.work_stress_level)
        add("social.financial_stress", r.log_date, r.financial_stress_level)
        add("social.support", r.log_date, r.social_support_level)

    # ── Labs (one signal per numeric test name) ──
    labrows = (await db.execute(
        select(LabResult).where(
            LabResult.user_id == user_id,
            LabResult.test_date >= start, LabResult.test_date <= end,
        )
    )).scalars().all()
    for r in labrows:
        if r.value is not None and r.test_name:
            key = f"lab.{r.test_name.strip().lower().replace(' ', '_')}"
            add(key, r.test_date, r.value)

    # Reduce each day's list per the signal's aggregation type.
    out: dict[str, dict[date, float]] = {}
    for signal, by_date in acc.items():
        agg = SIGNAL_META.get(signal, {}).get("agg", MEAN)
        reducer: Callable[[list[float]], float] = (
            (lambda xs: sum(xs)) if agg == SUM else (lambda xs: sum(xs) / len(xs))
        )
        # symptom.severity_max takes the max per day
        if signal == "symptom.severity_max":
            reducer = max
        out[signal] = {d: round(reducer(vals), 3) for d, vals in by_date.items() if vals}
    return out
