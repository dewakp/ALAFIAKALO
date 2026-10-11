# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

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
from datetime import date, datetime, time, timedelta
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chronic_conditions import IntradialyticReading, TherapySession
from app.models.conditions import SymptomLog
from app.models.elimination import BowelMovement, UrinationLog, VomitingLog
from app.models.fitness import FitnessLog
from app.models.ground_truth import EnvSocialLog
from app.models.labs import LabResult
from app.models.lifestyle import LifestyleEntry
from app.models.mood import MoodEntry
from app.models.nutrition import NutritionLog
from app.models.sleep import SleepLog
from app.models.vitals import VitalsLog
from app.services import clinical_sources
from app.services.docparse.dictionaries import analyte_key
from app.services.elimination_text import blood_in_row


def _as_dt(day: date) -> datetime:
    """`therapy_sessions.scheduled_date` is `timestamp WITHOUT time zone`.

    §3aa: comparing a tz-aware value to that column makes asyncpg raise
    `DataError`, the endpoint 500s, and the page renders "no sessions found" on
    a patient with thousands. A naive midnight is what the column holds.
    """
    return datetime.combine(day, time.min)


def _as_date(value: str | None) -> date | None:
    """The clinical_sources views carry dates as ISO-ish strings."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

# Aggregation per signal: "sum" (intake/activity totals) or "mean" (measurements).
SUM = "sum"
MEAN = "mean"
#: MIN and MAX exist because a mean destroys the finding on some signals.
#: §3am: "for intradialytic the NADIR is the finding, not the mean — a session
#: ending below 90 systolic is intradialytic hypotension that a mean hides."
#: A patient whose readings run 150/90 then 59/32 has a perfectly ordinary mean.
MIN = "min"
MAX = "max"

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
    # Declared MAX, not MEAN. It was MEAN with the max applied by a hardcoded
    # `if signal == "symptom.severity_max"` in the reducer — so the declaration
    # and the behaviour disagreed, and removing that branch without fixing this
    # line would have quietly turned the worst severity of the day into its
    # average.
    "symptom.severity_max": {"label": "Worst symptom severity", "domain": "symptom", "agg": MAX, "unit": "/10"},
    "env.aqi":              {"label": "Air quality index", "domain": "env", "agg": MEAN, "unit": "AQI"},
    "env.ambient_temp_c":   {"label": "Ambient temperature", "domain": "env", "agg": MEAN, "unit": "°C"},
    "env.humidity_pct":     {"label": "Humidity", "domain": "env", "agg": MEAN, "unit": "%"},
    "social.work_stress":   {"label": "Work stress", "domain": "social", "agg": MEAN, "unit": "/10"},
    "social.financial_stress": {"label": "Financial stress", "domain": "social", "agg": MEAN, "unit": "/10"},
    "social.support":       {"label": "Social support", "domain": "social", "agg": MEAN, "unit": "/10"},

    # ── Dialysis / flowsheets ────────────────────────────────────────────────
    # The largest clinical series this product holds, and until 2026-10-11 the
    # insight surface could not see ANY of it. Measured on the reference record:
    #
    #     weight    vitals_logs 41        therapy_sessions 5,221   -> 0.8% seen
    #     systolic  vitals_logs 43        flowsheets 18,526        -> 0.23% seen
    #
    # So `vital.weight_kg` was forecast from 41 points while 5,221 existed, and
    # no relationship could involve dialysis at all. §3am found this in the AI
    # tool and §3ba in the wellness score; this is the same fault, third surface.
    #
    # Kept as SEPARATE signals rather than merged into `vital.*`, which is the
    # whole point of §3am: post runs well below pre BY DESIGN, so averaging the
    # sources together manufactures a number no instrument ever read. Printing
    # pre-systolic over post-systolic as `sys/dia` once produced "91/83" — a
    # pulse pressure of 8, read as catastrophic, from two ordinary means.
    "dialysis.pre_weight_kg":   {"label": "Pre-dialysis weight", "domain": "dialysis", "agg": MEAN, "unit": "kg"},
    "dialysis.post_weight_kg":  {"label": "Post-dialysis weight", "domain": "dialysis", "agg": MEAN, "unit": "kg"},
    "dialysis.dry_weight_kg":   {"label": "Target dry weight", "domain": "dialysis", "agg": MEAN, "unit": "kg"},
    "dialysis.fluid_removed_ml": {"label": "Fluid removed", "domain": "dialysis", "agg": SUM, "unit": "mL"},
    "dialysis.pre_systolic":    {"label": "Pre-dialysis systolic", "domain": "dialysis", "agg": MEAN, "unit": "mmHg"},
    "dialysis.pre_diastolic":   {"label": "Pre-dialysis diastolic", "domain": "dialysis", "agg": MEAN, "unit": "mmHg"},
    "dialysis.post_systolic":   {"label": "Post-dialysis systolic", "domain": "dialysis", "agg": MEAN, "unit": "mmHg"},
    "dialysis.post_diastolic":  {"label": "Post-dialysis diastolic", "domain": "dialysis", "agg": MEAN, "unit": "mmHg"},
    "dialysis.nadir_systolic":  {"label": "Lowest systolic during treatment", "domain": "dialysis", "agg": MIN, "unit": "mmHg"},
    "dialysis.readings_under_90": {"label": "Readings below 90 systolic", "domain": "dialysis", "agg": SUM, "unit": ""},
    "dialysis.machine_minutes": {"label": "Time on dialysis (machine)", "domain": "dialysis", "agg": MEAN, "unit": "min"},
    "dialysis.treatments":      {"label": "Treatments", "domain": "dialysis", "agg": SUM, "unit": ""},

    # ── Medication ───────────────────────────────────────────────────────────
    "medication.doses":         {"label": "Doses taken", "domain": "medication", "agg": SUM, "unit": ""},
    "medication.unit_administered": {"label": "Drugs given at the unit", "domain": "medication", "agg": MAX, "unit": ""},

    # ── Elimination ──────────────────────────────────────────────────────────
    "elimination.bowel_movements": {"label": "Bowel movements", "domain": "elimination", "agg": SUM, "unit": ""},
    "elimination.blood_episodes": {"label": "Episodes with blood", "domain": "elimination", "agg": SUM, "unit": ""},
    "elimination.vomiting":     {"label": "Vomiting episodes", "domain": "elimination", "agg": SUM, "unit": ""},
    "elimination.urinations":   {"label": "Urinations", "domain": "elimination", "agg": SUM, "unit": ""},

    # ── Events (hospital stays and operations) ───────────────────────────────
    # An admission is not a daily measurement, it is an EVENT — and an event is
    # exactly what a relationship engine needs on the timeline, because what
    # changed around it is the clinical question.
    "event.hospital_admissions": {"label": "Hospital admissions", "domain": "event", "agg": SUM, "unit": ""},
    "event.surgical_procedures": {"label": "Procedures", "domain": "event", "agg": SUM, "unit": ""},
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

    # ── Labs (one signal per ANALYTE, not per spelling) ──
    #
    # Keyed on `analyte_key()`, never on the raw printed name. §3ax: one
    # patient's history is stored as `ALP` until July 2025 and `Alk Phos`
    # after, because the report format changed — and on the dev copy of
    # production 219 stored names are 155 analytes, with 50 SPLIT across two or
    # three spellings (`K+`/`Potassium`, `CRE`/`Creatinine`, `HGB`/
    # `Hemoglobin`). Keying on the wording made each spelling its own signal,
    # so a forecast or correlation ran on half a series and the two halves could
    # not be related to each other.
    labrows = (await db.execute(
        select(LabResult).where(
            LabResult.user_id == user_id,
            LabResult.test_date >= start, LabResult.test_date <= end,
        )
    )).scalars().all()
    for r in labrows:
        if r.value is not None and r.test_name:
            add(f"lab.{analyte_key(r.test_name)}", r.test_date, r.value)

    # ── Dialysis / flowsheets ───────────────────────────────────────────────
    #
    # `scheduled_date` is a DateTime stored at midnight, so it is taken as a
    # date. Sessions are NOT filtered by status: a pre-treatment weight is a
    # measurement that was taken, whatever the treatment went on to do, and
    # §3ac's completed-only rule governs solute REMOVAL credit, not whether an
    # observation happened.
    sessions = (await db.execute(
        select(TherapySession).where(
            TherapySession.user_id == user_id,
            TherapySession.scheduled_date >= _as_dt(start),
            TherapySession.scheduled_date < _as_dt(end + timedelta(days=1)),
        )
    )).scalars().all()
    session_day: dict[int, date] = {}
    for s in sessions:
        day = s.scheduled_date.date() if s.scheduled_date else None
        if day is None:
            continue
        session_day[s.id] = day
        add("dialysis.treatments", day, 1)
        add("dialysis.pre_weight_kg", day, s.pre_dialysis_weight_kg)
        add("dialysis.post_weight_kg", day, s.post_dialysis_weight_kg)
        add("dialysis.dry_weight_kg", day, s.dry_weight_kg)
        add("dialysis.fluid_removed_ml", day, s.fluid_removed_ml)
        add("dialysis.pre_systolic", day, s.pre_systolic_bp)
        add("dialysis.pre_diastolic", day, s.pre_diastolic_bp)
        add("dialysis.post_systolic", day, s.post_systolic_bp)
        add("dialysis.post_diastolic", day, s.post_diastolic_bp)
        # `machine_total_time_minutes` ONLY — deliberately NOT
        # `duration_minutes`. §3av measured that column holding the WALL CLOCK
        # when written by the app and the MACHINE's time on dialysis when
        # written by the 2026-06-04 import, with no way to tell which from the
        # row. "Anything that averages, charts or models duration across this
        # record is mixing two different measurements", so there is no duration
        # signal rather than a signal that silently mixes two instruments.
        add("dialysis.machine_minutes", day, s.machine_total_time_minutes)

    if session_day:
        readings = (await db.execute(
            select(IntradialyticReading).where(
                IntradialyticReading.session_id.in_(list(session_day)))
        )).scalars().all()
        for r in readings:
            day = session_day.get(r.session_id)
            if day is None or r.systolic_bp is None:
                continue
            # The NADIR, reduced with MIN — §3am. And the count below 90 stated
            # explicitly beside it, because "25 of 32 treatments ended below 90
            # mmHg systolic (lowest 54)" is the finding a score hides.
            add("dialysis.nadir_systolic", day, r.systolic_bp)
            if r.systolic_bp < 90:
                add("dialysis.readings_under_90", day, 1)

    # ── Medication — THROUGH `clinical_sources`, never the tables ───────────
    #
    # §3aa: `medication_dose_logs` is a guarded model with exactly one reader,
    # and medications live in THREE places. `administration_days` is what
    # carries the third — drugs the unit gives during dialysis, which on this
    # record is Epogene ×1,962 / Venofer ×1,248 / Doxercalciferol ×788 and
    # appears in ZERO dose logs because the patient never types them in.
    for day, count in await clinical_sources.dose_counts_by_day(db, user_id, start):
        if isinstance(day, date) and start <= day <= end:
            add("medication.doses", day, count)
    for iso in await clinical_sources.administration_days(db, user_id, start):
        day = date.fromisoformat(iso)
        if start <= day <= end:
            add("medication.unit_administered", day, 1)

    # ── Elimination ─────────────────────────────────────────────────────────
    #
    # `blood_present` is TRUE on ZERO of 648 migrated rows while 134 of them say
    # so in the notes ("Bloody" 109, "Very bloody" 5, "traces of blood" 2,
    # "Blooy" 1) — two importers write only `notes` and name no structured
    # column. §3ba: `elimination_text.blood_in_row` is the one reader, a set
    # column always wins, and only NULL falls through to the words. Counting the
    # boolean here would report one bowel movement in five as unremarkable.
    bowel = (await db.execute(
        select(BowelMovement).where(
            BowelMovement.user_id == user_id,
            BowelMovement.log_date >= start, BowelMovement.log_date <= end,
        )
    )).scalars().all()
    for r in bowel:
        add("elimination.bowel_movements", r.log_date, 1)
        if blood_in_row(flag=r.blood_present, notes=r.notes):
            add("elimination.blood_episodes", r.log_date, 1)

    for model, signal in ((VomitingLog, "elimination.vomiting"),
                          (UrinationLog, "elimination.urinations")):
        rows = (await db.execute(
            select(model).where(
                model.user_id == user_id,
                model.log_date >= start, model.log_date <= end,
            )
        )).scalars().all()
        for r in rows:
            add(signal, r.log_date, 1)

    # ── Events: stays and operations, through `clinical_sources` ────────────
    #
    # Both models are §3aa-guarded, and either row can stand alone: day-case
    # surgery and anything recorded years later have no admission, so a reader
    # that starts from stays loses exactly the operations that matter most.
    # Both views expose their date as a STRING (`HospitalizationView.admitted`,
    # `ProcedureView.performed`), not a date object — read off the dataclasses
    # rather than assumed. A first pass here used `getattr(stay, "admitted_on")`
    # with a fallback, which is a guess wearing a safety net: both names were
    # wrong, `getattr` cannot fail, and every admission would have been dropped
    # in silence (§0, and §3am's `getattr(row, name, None)` lesson exactly).
    for stay in await clinical_sources.hospitalizations(db, user_id, since=start):
        day = _as_date(stay.admitted)
        if day and start <= day <= end:
            add("event.hospital_admissions", day, 1)
    for proc in await clinical_sources.procedures(db, user_id, since=start):
        day = _as_date(proc.performed)
        if day and start <= day <= end:
            add("event.surgical_procedures", day, 1)

    # Reduce each day's list per the signal's aggregation type.
    #
    # MIN and MAX are declared in SIGNAL_META like every other aggregation. The
    # previous version hardcoded `if signal == "symptom.severity_max": reducer =
    # max` — correct for that one signal and unreachable for any other, so
    # `dialysis.nadir_systolic` would have been silently MEANED, which is the
    # one thing §3am says destroys the finding.
    _REDUCERS: dict[str, Callable[[list[float]], float]] = {
        SUM: sum,
        MEAN: lambda xs: sum(xs) / len(xs),
        MIN: min,
        MAX: max,
    }
    out: dict[str, dict[date, float]] = {}
    for signal, by_date in acc.items():
        agg = SIGNAL_META.get(signal, {}).get("agg", MEAN)
        reducer = _REDUCERS.get(agg, _REDUCERS[MEAN])
        out[signal] = {d: round(reducer(vals), 3) for d, vals in by_date.items() if vals}
    return out
