"""The clinician's patient board — one registry of shareable data categories.

A clinician opening a patient sees a board of category cards (latest/summary per
category, plus the patient's current score), and opening a card gives trends and
the full rows behind it.

Every category is described once here — its label, how to summarise it, and how
to detail it — so the board, the per-category view and the `all` grant cannot
drift apart. Adding a category means adding one `Category` below; the board, the
detail route and `all` all pick it up.

Nothing in here decides *whether* the clinician may see a category. That is the
caller's job (`grant_covers`), and it is enforced per category, so a patient who
shares only labs does not leak a nutrition summary through the board.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chronic_conditions import IntradialyticReading, TherapySession
from app.models.conditions import SymptomLog
from app.models.ehr import EHRConnection
from app.models.elimination import BowelMovement, UrinationLog, VomitingLog
from app.models.fitness import FitnessLog
from app.models.labs import LabResult
from app.models.lifestyle import LifestyleEntry
from app.models.mood import MoodEntry
from app.models.nutrition import NutritionLog
from app.models.peritoneal_dialysis import PDSession
from app.models.vitals import VitalsLog
from app.models.wellness import WellnessScore
from app.services import clinical_sources as sources

DEFAULT_WINDOW_DAYS = 90


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _round(value: float | None, places: int = 1) -> float | None:
    return None if value is None else round(float(value), places)


@dataclass
class Summary:
    """What a card shows before it is opened."""

    items: list[dict] = field(default_factory=list)   # [{label, value, danger?}]
    count: int | None = None                          # rows in the window
    last_updated: str | None = None
    empty_reason: str | None = None                   # set when there is nothing to show


@dataclass
class Detail:
    """What opening a card shows: trends plus the rows behind them."""

    series: list[dict] = field(default_factory=list)  # [{label, unit, points:[{date,value}]}]
    rows: list[dict] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)  # [{key, label}] — render order


@dataclass
class Category:
    key: str
    label: str
    icon: str
    summarise: Callable[[AsyncSession, int], Awaitable[Summary]]
    detail: Callable[[AsyncSession, int, int], Awaitable[Detail]]


def _window(days: int) -> date:
    return date.today() - timedelta(days=days)


# ── Recency helper ───────────────────────────────────────────────────────

async def _latest_date(db: AsyncSession, model, uid: int, column) -> date | None:
    return (await db.execute(
        select(func.max(column)).where(model.user_id == uid))).scalar()


def _stale_note(last: date | None) -> str:
    """Why a windowed card is empty, in a form a clinician can act on.

    A fixed 7-day window makes any patient who logs less often look like they
    log nothing. Across this database SIX of the seven users with nutrition data
    fell outside the window, so their card read "Nothing logged in the last 7
    days" while holding months of history. When the window is empty, say when
    they last logged instead — "last logged 60 days ago" is a clinical finding;
    a blank card is a dead end.
    """
    if last is None:
        return "Never logged."
    days = (date.today() - last).days
    if days <= 0:
        return "Logged today."
    return f"Nothing in the last 7 days — last logged {days} day{'s' if days != 1 else ''} ago ({last})."


# ── Wellness score ───────────────────────────────────────────────────────

async def _score_summary(db: AsyncSession, uid: int) -> Summary:
    row = (await db.execute(
        select(WellnessScore).where(WellnessScore.user_id == uid)
        .order_by(WellnessScore.score_date.desc()).limit(1)
    )).scalar_one_or_none()
    if row is None:
        return Summary(empty_reason="No wellness score calculated yet.")
    items = [{"label": "Overall", "value": _round(row.overall_score), "unit": "/100"}]
    for label, val in (
        ("Nutrition", row.nutrition_score), ("Fitness", row.fitness_score),
        ("Sleep", row.sleep_score), ("Mood", row.mood_score),
        ("Vitals", row.vitals_score), ("Medication", row.medication_adherence_score),
    ):
        if val is not None:
            items.append({"label": label, "value": _round(val), "unit": "/100"})
    return Summary(items=items, last_updated=_iso(row.score_date))


async def _score_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    rows = (await db.execute(
        select(WellnessScore).where(
            WellnessScore.user_id == uid, WellnessScore.score_date >= _window(days)
        ).order_by(WellnessScore.score_date)
    )).scalars().all()
    series = [{
        "label": "Overall score", "unit": "/100",
        "points": [{"date": str(r.score_date), "value": _round(r.overall_score)} for r in rows],
    }]
    for label, attr in (
        ("Nutrition", "nutrition_score"), ("Fitness", "fitness_score"),
        ("Sleep", "sleep_score"), ("Mood", "mood_score"), ("Vitals", "vitals_score"),
    ):
        pts = [{"date": str(r.score_date), "value": _round(getattr(r, attr))}
               for r in rows if getattr(r, attr) is not None]
        if pts:
            series.append({"label": label, "unit": "/100", "points": pts})
    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "overall", "label": "Overall"},
                 {"key": "explanation", "label": "Explanation"}],
        rows=[{"date": str(r.score_date), "overall": _round(r.overall_score),
               "explanation": r.explanation} for r in reversed(rows)],
    )


# ── Vitals ───────────────────────────────────────────────────────────────

async def _vitals_summary(db: AsyncSession, uid: int) -> Summary:
    row = (await db.execute(
        select(VitalsLog).where(VitalsLog.user_id == uid)
        .order_by(VitalsLog.log_date.desc(), VitalsLog.id.desc()).limit(1)
    )).scalar_one_or_none()
    if row is None:
        return Summary(empty_reason="No vitals recorded.")
    items = []
    if row.blood_pressure_systolic:
        items.append({"label": "Blood pressure",
                      "value": f"{row.blood_pressure_systolic}/{row.blood_pressure_diastolic}",
                      "unit": "mmHg"})
    if row.heart_rate_bpm:
        items.append({"label": "Heart rate", "value": row.heart_rate_bpm, "unit": "bpm"})
    if row.weight_kg:
        items.append({"label": "Weight", "value": _round(row.weight_kg), "unit": "kg"})
    if row.blood_oxygen_pct:
        items.append({"label": "SpO₂", "value": _round(row.blood_oxygen_pct), "unit": "%"})
    total = (await db.execute(
        select(func.count(VitalsLog.id)).where(VitalsLog.user_id == uid))).scalar() or 0
    return Summary(items=items, count=total, last_updated=str(row.log_date))


async def _vitals_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    rows = (await db.execute(
        select(VitalsLog).where(VitalsLog.user_id == uid, VitalsLog.log_date >= _window(days))
        .order_by(VitalsLog.log_date)
    )).scalars().all()

    def pts(attr, conv=lambda v: v):
        return [{"date": str(r.log_date), "value": conv(getattr(r, attr))}
                for r in rows if getattr(r, attr) is not None]

    series = []
    for label, attr, unit in (
        ("Systolic", "blood_pressure_systolic", "mmHg"),
        ("Diastolic", "blood_pressure_diastolic", "mmHg"),
        ("Heart rate", "heart_rate_bpm", "bpm"),
        ("Weight", "weight_kg", "kg"),
    ):
        p = pts(attr, lambda v: _round(v))
        if p:
            series.append({"label": label, "unit": unit, "points": p})
    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "bp", "label": "BP"},
                 {"key": "hr", "label": "HR"}, {"key": "weight", "label": "Weight"},
                 {"key": "spo2", "label": "SpO₂"}],
        rows=[{
            "date": str(r.log_date),
            "bp": (f"{r.blood_pressure_systolic}/{r.blood_pressure_diastolic}"
                   if r.blood_pressure_systolic else None),
            "hr": r.heart_rate_bpm,
            "weight": _round(r.weight_kg),
            "spo2": _round(r.blood_oxygen_pct),
        } for r in reversed(rows)],
    )


# ── Labs ─────────────────────────────────────────────────────────────────

async def _labs_summary(db: AsyncSession, uid: int) -> Summary:
    rows = (await db.execute(
        select(LabResult).where(LabResult.user_id == uid)
        .order_by(LabResult.test_date.desc(), LabResult.id.desc()).limit(6)
    )).scalars().all()
    if not rows:
        return Summary(empty_reason="No lab results.")
    abnormal = (await db.execute(
        select(func.count(LabResult.id)).where(
            LabResult.user_id == uid, LabResult.is_abnormal.is_(True))
    )).scalar() or 0
    total = (await db.execute(
        select(func.count(LabResult.id)).where(LabResult.user_id == uid))).scalar() or 0
    items = [{
        "label": r.test_name,
        "value": r.value_string or (_round(r.value, 2) if r.value is not None else None),
        "unit": r.unit,
        "danger": bool(r.is_abnormal),
    } for r in rows]
    if abnormal:
        items.insert(0, {"label": "Abnormal results", "value": abnormal, "danger": True})
    return Summary(items=items, count=total, last_updated=str(rows[0].test_date))


async def _labs_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    # Labs deliberately ignore the day window that the daily categories use.
    # They are episodic — a panel drawn every few months, not a daily log — so
    # windowing them to 90 days routinely returns a single draw, where every
    # test has one point and no test has a trend. Verified against a real
    # record: 422 results, 409 of them numeric, and zero series under a
    # 365-day window. Take the most recent results across all history instead.
    rows = (await db.execute(
        select(LabResult).where(LabResult.user_id == uid)
        .order_by(LabResult.test_date.desc(), LabResult.id.desc()).limit(400)
    )).scalars().all()
    rows = list(reversed(rows))  # chronological, for the series

    # One series per test with at least two numeric points — a single reading is
    # not a trend, and a panel carries dozens of one-off tests.
    by_test: OrderedDict[str, list] = OrderedDict()
    for r in rows:
        if r.value is not None:
            by_test.setdefault(r.test_name, []).append(r)
    series = [{
        "label": name, "unit": rs[0].unit,
        "points": [{"date": str(r.test_date), "value": _round(r.value, 2)} for r in rs[-24:]],
    } for name, rs in by_test.items() if len(rs) >= 2]
    # Most-moved tests first: a clinician wants the panel that is changing.
    series.sort(key=lambda s: len(s["points"]), reverse=True)

    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "name", "label": "Test"},
                 {"key": "value", "label": "Value"}, {"key": "range", "label": "Reference"}],
        rows=[{
            "date": str(r.test_date), "name": r.test_name,
            "value": f"{r.value_string or _round(r.value, 2) or '—'} {r.unit or ''}".strip(),
            "range": (f"{r.reference_range_low}–{r.reference_range_high}"
                      if r.reference_range_low is not None else None),
            "danger": bool(r.is_abnormal),
        } for r in reversed(rows)],
    )


# ── Nutrients ────────────────────────────────────────────────────────────

async def _nutrition_summary(db: AsyncSession, uid: int) -> Summary:
    since = _window(7)
    agg = (await db.execute(
        select(
            func.coalesce(func.sum(NutritionLog.calories), 0),
            func.coalesce(func.sum(NutritionLog.protein_g), 0),
            func.coalesce(func.sum(NutritionLog.carbs_g), 0),
            func.coalesce(func.sum(NutritionLog.fat_g), 0),
            func.count(func.distinct(NutritionLog.log_date)),
            func.count(NutritionLog.id),
            func.max(NutritionLog.log_date),
        ).where(NutritionLog.user_id == uid, NutritionLog.log_date >= since)
    )).one()
    kcal, protein, carbs, fat, day_count, entries, last = agg
    if not entries:
        last_seen = await _latest_date(db, NutritionLog, uid, NutritionLog.log_date)
        return Summary(empty_reason=_stale_note(last_seen))
    d = max(int(day_count or 1), 1)
    return Summary(
        items=[
            {"label": "Calories / day", "value": _round(float(kcal) / d, 0), "unit": "kcal"},
            {"label": "Protein / day", "value": _round(float(protein) / d), "unit": "g"},
            {"label": "Carbs / day", "value": _round(float(carbs) / d), "unit": "g"},
            {"label": "Fat / day", "value": _round(float(fat) / d), "unit": "g"},
        ],
        count=int(entries), last_updated=str(last) if last else None,
    )


async def _nutrition_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    daily = (await db.execute(
        select(
            NutritionLog.log_date,
            func.coalesce(func.sum(NutritionLog.calories), 0),
            func.coalesce(func.sum(NutritionLog.protein_g), 0),
            func.coalesce(func.sum(NutritionLog.carbs_g), 0),
            func.coalesce(func.sum(NutritionLog.fat_g), 0),
        ).where(NutritionLog.user_id == uid, NutritionLog.log_date >= _window(days))
        .group_by(NutritionLog.log_date).order_by(NutritionLog.log_date)
    )).all()
    series = []
    for idx, (label, unit) in enumerate(
        ((("Calories"), "kcal"), ("Protein", "g"), ("Carbs", "g"), ("Fat", "g")), start=1
    ):
        pts = [{"date": str(r[0]), "value": _round(float(r[idx]), 0 if idx == 1 else 1)}
               for r in daily]
        if any(p["value"] for p in pts):
            series.append({"label": label, "unit": unit, "points": pts})

    rows = (await db.execute(
        select(NutritionLog).where(
            NutritionLog.user_id == uid, NutritionLog.log_date >= _window(days))
        .order_by(NutritionLog.log_date.desc(), NutritionLog.id.desc()).limit(200)
    )).scalars().all()
    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "meal", "label": "Meal"},
                 {"key": "food", "label": "Food"}, {"key": "calories", "label": "kcal"},
                 {"key": "protein", "label": "Protein"}],
        rows=[{"date": str(r.log_date), "meal": r.meal_type, "food": r.food_name,
               "calories": _round(r.calories, 0), "protein": _round(r.protein_g)} for r in rows],
    )


# ── Fitness ──────────────────────────────────────────────────────────────

async def _fitness_summary(db: AsyncSession, uid: int) -> Summary:
    since = _window(7)
    sessions, minutes, calories, steps, last = (await db.execute(
        select(
            func.count(FitnessLog.id),
            func.coalesce(func.sum(FitnessLog.duration_minutes), 0),
            func.coalesce(func.sum(FitnessLog.calories_burned), 0),
            func.coalesce(func.sum(FitnessLog.steps), 0),
            func.max(FitnessLog.log_date),
        ).where(FitnessLog.user_id == uid, FitnessLog.log_date >= since)
    )).one()
    if not sessions:
        last_seen = await _latest_date(db, FitnessLog, uid, FitnessLog.log_date)
        return Summary(empty_reason=_stale_note(last_seen))
    return Summary(
        items=[
            {"label": "Sessions (7d)", "value": int(sessions)},
            {"label": "Active minutes", "value": int(minutes or 0), "unit": "min"},
            {"label": "Calories burned", "value": _round(float(calories or 0), 0), "unit": "kcal"},
            {"label": "Steps", "value": int(steps or 0)},
        ],
        count=int(sessions), last_updated=str(last) if last else None,
    )


async def _fitness_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    daily = (await db.execute(
        select(
            FitnessLog.log_date,
            func.coalesce(func.sum(FitnessLog.duration_minutes), 0),
            func.coalesce(func.sum(FitnessLog.calories_burned), 0),
            func.coalesce(func.sum(FitnessLog.steps), 0),
        ).where(FitnessLog.user_id == uid, FitnessLog.log_date >= _window(days))
        .group_by(FitnessLog.log_date).order_by(FitnessLog.log_date)
    )).all()
    series = []
    for idx, (label, unit) in enumerate(
        (("Active minutes", "min"), ("Calories burned", "kcal"), ("Steps", "")), start=1
    ):
        pts = [{"date": str(r[0]), "value": _round(float(r[idx]), 0)} for r in daily]
        if any(p["value"] for p in pts):
            series.append({"label": label, "unit": unit, "points": pts})

    rows = (await db.execute(
        select(FitnessLog).where(FitnessLog.user_id == uid, FitnessLog.log_date >= _window(days))
        .order_by(FitnessLog.log_date.desc(), FitnessLog.id.desc()).limit(200)
    )).scalars().all()
    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "activity", "label": "Activity"},
                 {"key": "minutes", "label": "Minutes"}, {"key": "calories", "label": "kcal"},
                 {"key": "intensity", "label": "Intensity"}],
        rows=[{"date": str(r.log_date), "activity": r.activity_type,
               "minutes": r.duration_minutes, "calories": _round(r.calories_burned, 0),
               "intensity": r.intensity} for r in rows],
    )


# ── Elimination ──────────────────────────────────────────────────────────

async def _elimination_summary(db: AsyncSession, uid: int) -> Summary:
    since = _window(7)

    async def count(model):
        return (await db.execute(
            select(func.count(model.id)).where(model.user_id == uid, model.log_date >= since)
        )).scalar() or 0

    async def latest(model):
        return (await db.execute(
            select(func.max(model.log_date)).where(model.user_id == uid))).scalar()

    stool, urine, vomit = await count(BowelMovement), await count(UrinationLog), await count(VomitingLog)
    if not (stool or urine or vomit):
        dates = [d for d in (await latest(BowelMovement), await latest(UrinationLog),
                             await latest(VomitingLog)) if d]
        return Summary(empty_reason=_stale_note(max(dates) if dates else None))

    blood = (await db.execute(
        select(func.count(BowelMovement.id)).where(
            BowelMovement.user_id == uid, BowelMovement.log_date >= since,
            BowelMovement.blood_present.is_(True))
    )).scalar() or 0

    items = [
        {"label": "Bowel movements (7d)", "value": int(stool)},
        {"label": "Urinations (7d)", "value": int(urine)},
    ]
    if vomit:
        items.append({"label": "Vomiting episodes (7d)", "value": int(vomit), "danger": True})
    if blood:
        items.append({"label": "With blood", "value": int(blood), "danger": True})

    dates = [d for d in [await latest(BowelMovement), await latest(UrinationLog),
                         await latest(VomitingLog)] if d]
    return Summary(items=items, count=int(stool + urine + vomit),
                   last_updated=str(max(dates)) if dates else None)


async def _elimination_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    since = _window(days)

    async def daily(model, label):
        res = (await db.execute(
            select(model.log_date, func.count(model.id))
            .where(model.user_id == uid, model.log_date >= since)
            .group_by(model.log_date).order_by(model.log_date)
        )).all()
        return {"label": label, "unit": "per day",
                "points": [{"date": str(d), "value": int(c)} for d, c in res]}

    series = [s for s in (
        await daily(BowelMovement, "Bowel movements"),
        await daily(UrinationLog, "Urinations"),
        await daily(VomitingLog, "Vomiting"),
    ) if s["points"]]

    stools = (await db.execute(
        select(BowelMovement).where(BowelMovement.user_id == uid, BowelMovement.log_date >= since)
        .order_by(BowelMovement.log_date.desc()).limit(120)
    )).scalars().all()
    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "bristol", "label": "Bristol"},
                 {"key": "consistency", "label": "Consistency"},
                 {"key": "blood", "label": "Blood"}, {"key": "pain", "label": "Pain"}],
        rows=[{"date": str(r.log_date), "bristol": r.bristol_scale,
               "consistency": r.consistency, "blood": "yes" if r.blood_present else None,
               "pain": r.pain_level, "danger": bool(r.blood_present)} for r in stools],
    )


# ── Medications ──────────────────────────────────────────────────────────
#
# TWO tables, and the clinically important one is not the obvious one.
#
#   `medications`           the prescription / profile list
#   `medication_dose_logs`  what the patient actually TOOK, written by the
#                           Medications screen every time they log an intake
#
# Reading only `medications` showed one real patient "Meperidine (stopped),
# Ibuprofen (stopped)" — while their own screen showed Calcitriol and Calcium
# Carbonate taken that morning, backed by 921 dose logs against 2 prescriptions,
# none of them active. A physician would have concluded the patient was on
# nothing. So the card leads with what is being taken and keeps the prescription
# list alongside it, labelled, because "prescribed" and "taken" are different
# clinical facts and neither substitutes for the other.

_DOSE_WINDOW_DAYS = 30


async def _dose_rollup(db: AsyncSession, uid: int, since: date) -> list:
    """(name, doses, last_taken) per medication, most recently taken first.

    Grouped case-insensitively: the same drug arrives as both "Calcium
    Carbonate" and "Calcium carbonate", and showing them as two medications
    misrepresents the regimen.
    """
    name = func.min(MedicationDoseLog.medication_name)  # a representative casing
    return (await db.execute(
        select(
            name,
            func.count(MedicationDoseLog.id),
            func.max(MedicationDoseLog.log_date),
        )
        .where(MedicationDoseLog.user_id == uid, MedicationDoseLog.log_date >= since)
        .group_by(func.lower(MedicationDoseLog.medication_name))
        .order_by(func.max(MedicationDoseLog.log_date).desc(),
                  func.count(MedicationDoseLog.id).desc())
    )).all()


async def _medications_summary(db: AsyncSession, uid: int) -> Summary:
    taken = await sources.medications_taken(db, uid)
    active = await sources.medications_prescribed(db, uid, active_only=True)
    if not taken and not active:
        return Summary(empty_reason="No medications taken or prescribed.")

    items = [{"label": m.name, "value": m.doses,
              "unit": "dose" if m.doses == 1 else "doses",
              "note": f"last {m.last}"} for m in taken[:6]]
    items += [{"label": f"{m.name} (prescribed)", "value": m.detail} for m in active[:3]]

    lasts = [m.last for m in taken if m.last]
    return Summary(items=items, count=len(taken) + len(active),
                   last_updated=max(lasts) if lasts else None)


async def _medications_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    since = _window(days)

    # Doses per day: the adherence picture a clinician is actually asking about.
    per_day = await sources.dose_counts_by_day(db, uid, since)
    series = ([{"label": "Doses taken", "unit": "per day",
                "points": [{"date": str(d), "value": int(c)} for d, c in per_day]}]
              if len(per_day) >= 2 else [])

    rows = [{"name": m.name, "detail": m.detail, "last": m.last,
             "source": m.source, "status": "active"}
            for m in await sources.medications_taken(db, uid, since=since)]
    rows += [{"name": m.name, "detail": m.detail, "last": m.last,
              "source": m.source, "status": "active" if m.active else "stopped"}
             for m in await sources.medications_prescribed(db, uid)]

    return Detail(
        series=series,
        columns=[{"key": "name", "label": "Medication"}, {"key": "detail", "label": "Detail"},
                 {"key": "source", "label": "Source"}, {"key": "last", "label": "Last / start"},
                 {"key": "status", "label": "Status"}],
        rows=rows,
    )


# ── Journal ──────────────────────────────────────────────────────────────
# Journal entries live on MoodEntry.journal_entry — the web Journal page writes
# them through /mood — so this reads mood rows that carry text.

async def _journal_summary(db: AsyncSession, uid: int) -> Summary:
    rows = (await db.execute(
        select(MoodEntry).where(
            MoodEntry.user_id == uid, MoodEntry.journal_entry.isnot(None),
            MoodEntry.journal_entry != "",
        ).order_by(MoodEntry.entry_date.desc()).limit(3)
    )).scalars().all()
    if not rows:
        return Summary(empty_reason="No journal entries.")
    total = (await db.execute(
        select(func.count(MoodEntry.id)).where(
            MoodEntry.user_id == uid, MoodEntry.journal_entry.isnot(None),
            MoodEntry.journal_entry != "")
    )).scalar() or 0
    return Summary(
        items=[{"label": str(r.entry_date),
                "value": (r.journal_entry or "")[:120] + ("…" if len(r.journal_entry or "") > 120 else "")}
               for r in rows],
        count=int(total), last_updated=str(rows[0].entry_date),
    )


async def _journal_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    rows = (await db.execute(
        select(MoodEntry).where(
            MoodEntry.user_id == uid, MoodEntry.entry_date >= _window(days),
            MoodEntry.journal_entry.isnot(None), MoodEntry.journal_entry != "",
        ).order_by(MoodEntry.entry_date.desc()).limit(200)
    )).scalars().all()
    return Detail(
        columns=[{"key": "date", "label": "Date"}, {"key": "entry", "label": "Entry"},
                 {"key": "mood", "label": "Mood"}],
        rows=[{"date": str(r.entry_date), "entry": r.journal_entry, "mood": r.mood_score}
              for r in rows],
    )


# ── Mood ─────────────────────────────────────────────────────────────────

async def _mood_summary(db: AsyncSession, uid: int) -> Summary:
    row = (await db.execute(
        select(MoodEntry).where(MoodEntry.user_id == uid)
        .order_by(MoodEntry.entry_date.desc()).limit(1)
    )).scalar_one_or_none()
    if row is None:
        return Summary(empty_reason="No mood entries.")
    items = [{"label": "Mood", "value": row.mood_score, "unit": "/10"}]
    for label, val, unit in (("Energy", row.energy_level, "/10"),
                             ("Stress", row.stress_level, "/10"),
                             ("Sleep", row.sleep_hours, "h")):
        if val is not None:
            items.append({"label": label, "value": _round(val), "unit": unit})
    total = (await db.execute(
        select(func.count(MoodEntry.id)).where(MoodEntry.user_id == uid))).scalar() or 0
    return Summary(items=items, count=int(total), last_updated=str(row.entry_date))


async def _mood_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    rows = (await db.execute(
        select(MoodEntry).where(MoodEntry.user_id == uid, MoodEntry.entry_date >= _window(days))
        .order_by(MoodEntry.entry_date)
    )).scalars().all()
    series = []
    for label, attr, unit in (("Mood", "mood_score", "/10"), ("Energy", "energy_level", "/10"),
                              ("Stress", "stress_level", "/10"), ("Sleep", "sleep_hours", "h")):
        pts = [{"date": str(r.entry_date), "value": _round(getattr(r, attr))}
               for r in rows if getattr(r, attr) is not None]
        if pts:
            series.append({"label": label, "unit": unit, "points": pts})
    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "mood", "label": "Mood"},
                 {"key": "energy", "label": "Energy"}, {"key": "stress", "label": "Stress"},
                 {"key": "sleep", "label": "Sleep h"}],
        rows=[{"date": str(r.entry_date), "mood": r.mood_score, "energy": r.energy_level,
               "stress": r.stress_level, "sleep": _round(r.sleep_hours)}
              for r in reversed(rows)],
    )


# ── Conditions ───────────────────────────────────────────────────────────
#
# TWO tables again, the same trap as medications:
#
#   `health_conditions`   the general problem list
#   `chronic_conditions`  long-term disease management (the Conditions screen,
#                         and what the dialysis / chemo flowsheets hang off)
#
# One real patient had 0 rows in the first and 4 in the second — including
# End-Stage Renal Disease, severe and active, on a record with 730 dialysis
# sessions. The board said "No active conditions." Reading one table and calling
# it the problem list hides exactly the diagnoses that matter most.

def _enum_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value)).replace("_", " ").title()


async def _conditions_summary(db: AsyncSession, uid: int) -> Summary:
    rows = await sources.conditions(db, uid, active_only=True)
    if not rows:
        return Summary(empty_reason="No active conditions.")
    return Summary(
        items=[{"label": c.name,
                "value": (c.severity or "").replace("_", " ").title() or None,
                # Severe/critical disease is the headline on a clinical board.
                "danger": c.is_severe} for c in rows[:6]],
        count=len(rows),
    )


async def _conditions_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    rows = await sources.conditions(db, uid)
    return Detail(
        columns=[{"key": "name", "label": "Condition"}, {"key": "category", "label": "Category"},
                 {"key": "severity", "label": "Severity"},
                 {"key": "diagnosed", "label": "Diagnosed"}, {"key": "status", "label": "Status"}],
        rows=[{"name": c.name,
               "category": (c.category or "").replace("_", " ").title() or None,
               "severity": (c.severity or "").replace("_", " ").title() or None,
               "diagnosed": c.diagnosed,
               "status": "active" if c.active else "resolved",
               "danger": c.is_severe} for c in rows],
    )


# ── Connected records (EHR) ──────────────────────────────────────────────

async def _connected_summary(db: AsyncSession, uid: int) -> Summary:
    rows = (await db.execute(
        select(EHRConnection).where(EHRConnection.user_id == uid)
        .order_by(EHRConnection.last_sync_at.desc().nullslast())
    )).scalars().all()
    if not rows:
        return Summary(empty_reason="No connected health records.")
    return Summary(
        items=[{"label": r.org_name or r.provider, "value": r.status,
                "note": _iso(r.last_sync_at)} for r in rows[:6]],
        count=len(rows),
        last_updated=_iso(rows[0].last_sync_at),
    )


async def _connected_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    rows = (await db.execute(
        select(EHRConnection).where(EHRConnection.user_id == uid)
    )).scalars().all()
    # Deliberately no tokens, URLs or FHIR patient ids: this is a clinical view,
    # not a credential store, and those fields would be an access-token leak.
    return Detail(
        columns=[{"key": "org", "label": "Organisation"}, {"key": "provider", "label": "Provider"},
                 {"key": "status", "label": "Status"}, {"key": "last_sync", "label": "Last sync"}],
        rows=[{"org": r.org_name, "provider": r.provider, "status": r.status,
               "last_sync": _iso(r.last_sync_at)} for r in rows],
    )


# ── Therapies ────────────────────────────────────────────────────────────
# Two sources: the general `therapy_sessions` table (dialysis, chemo,
# radiation, physio …) and `pd_sessions`, which the PD flowsheet writes on its
# own. A clinician asking "what therapy is this patient on" means both, so the
# card merges them rather than making the dialysis patients look untreated.

async def _therapies_summary(db: AsyncSession, uid: int) -> Summary:
    sessions = (await db.execute(
        select(TherapySession).where(TherapySession.user_id == uid)
        .order_by(TherapySession.scheduled_date.desc()).limit(200)
    )).scalars().all()
    session_total = (await db.execute(
        select(func.count(TherapySession.id)).where(TherapySession.user_id == uid))).scalar() or 0
    pd_count = (await db.execute(
        select(func.count(PDSession.id)).where(PDSession.user_id == uid))).scalar() or 0
    pd_last = (await db.execute(
        select(func.max(PDSession.session_date)).where(PDSession.user_id == uid))).scalar()

    if not sessions and not pd_count:
        return Summary(empty_reason="No therapy sessions recorded.")

    # Count from the database, not from the capped query below: the card said
    # "200 sessions" on a patient with 730 because len() counted the LIMIT.
    # Per-type counts come from a GROUP BY, not from the capped list above —
    # counting the LIMIT reported "Hemodialysis 200" on a patient with 730.
    by_type = (await db.execute(
        select(TherapySession.therapy_type, func.count(TherapySession.id))
        .where(TherapySession.user_id == uid)
        .group_by(TherapySession.therapy_type)
        .order_by(func.count(TherapySession.id).desc())
    )).all()
    items: list[dict] = [{
        "label": str(getattr(t, "value", t)).replace("_", " ").title(),
        "value": int(n), "unit": "sessions",
    } for t, n in by_type[:4]]
    if pd_count:
        items.append({"label": "Peritoneal Dialysis", "value": int(pd_count), "unit": "sessions"})

    dates = [d for d in (
        sessions[0].scheduled_date if sessions else None,
        pd_last,
    ) if d]
    last = max((str(d)[:10] for d in dates), default=None)
    return Summary(items=items, count=int(session_total) + int(pd_count), last_updated=last)


async def _therapies_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    """Hemodialysis and PD sessions in the window, with the numbers a nephrologist trends.

    Three defects lived here, and each rendered as an absence rather than an error:

    - `days` was accepted and never used, so the period buttons did nothing and the
      card always showed the same list.
    - `series` was built ONLY from `PDSession`, so a haemodialysis patient — 2005
      sessions, 1770 ultrafiltration values — got "No trend to plot for this period".
      Peritoneal is the modality this database has none of.
    - A `.limit(200)` stood in for a window, the same shape as the bug that once
      reported "200 sessions" for a patient with 730.

    Weight/UF/duration/BP carry different units, which is what splits them into
    small multiples downstream instead of one unreadable dual-axis plot.
    """
    since = _window(days)
    sessions = (await db.execute(
        select(TherapySession)
        .where(TherapySession.user_id == uid, TherapySession.scheduled_date >= since)
        .order_by(TherapySession.scheduled_date.desc())
    )).scalars().all()
    pd_rows = (await db.execute(
        select(PDSession)
        .where(PDSession.user_id == uid, PDSession.session_date >= since)
        .order_by(PDSession.session_date.desc())
    )).scalars().all()

    # Readings per session, so the row can say "6 readings" without N+1 queries.
    reading_counts = dict((await db.execute(
        select(IntradialyticReading.session_id, func.count(IntradialyticReading.id))
        .where(IntradialyticReading.user_id == uid)
        .group_by(IntradialyticReading.session_id)
    )).all())

    rows = [{
        "session_id": s.id,                       # the row is a link, not just text
        "date": str(s.scheduled_date)[:10],
        "therapy": getattr(s.therapy_type, "value", str(s.therapy_type)).replace("_", " ").title(),
        "name": s.therapy_name,
        "session": (f"{s.session_number} of {s.total_sessions_planned}"
                    if s.session_number and s.total_sessions_planned else s.session_number),
        "status": getattr(s.status, "value", str(s.status)),
        "pre_weight_kg": _round(s.pre_dialysis_weight_kg),
        "post_weight_kg": _round(s.post_dialysis_weight_kg),
        "fluid_removed_ml": _round(s.fluid_removed_ml, 0),
        "duration_minutes": s.duration_minutes,
        "pre_bp": (f"{s.pre_systolic_bp}/{s.pre_diastolic_bp}"
                   if s.pre_systolic_bp and s.pre_diastolic_bp else None),
        "post_bp": (f"{s.post_systolic_bp}/{s.post_diastolic_bp}"
                    if s.post_systolic_bp and s.post_diastolic_bp else None),
        "pre_heart_rate": s.pre_heart_rate,
        "post_heart_rate": s.post_heart_rate,
        "readings": reading_counts.get(s.id, 0),
        "flowsheet_status": getattr(s.flowsheet_status, "value", s.flowsheet_status),
        "reviewed_at": _iso(s.reviewed_at),
    } for s in sessions]
    rows += [{
        "session_id": None,                       # PD sessions have their own screen
        "date": str(p.session_date),
        "therapy": "Peritoneal Dialysis",
        "name": (p.modality or "").upper() or None,
        "session": None,
        "status": "completed",
        "fluid_removed_ml": _round(p.total_uf_ml, 0),
        "readings": 0,
    } for p in pd_rows]
    rows.sort(key=lambda r: r["date"], reverse=True)

    def _points(items, date_attr, value_attr, places=1):
        out = []
        for it in reversed(items):
            value = getattr(it, value_attr, None)
            if value is not None:
                out.append({"date": str(getattr(it, date_attr))[:10],
                            "value": _round(value, places)})
        return out

    candidates = [
        ("Pre-dialysis weight", "kg", _points(sessions, "scheduled_date", "pre_dialysis_weight_kg")),
        ("Post-dialysis weight", "kg", _points(sessions, "scheduled_date", "post_dialysis_weight_kg")),
        ("Fluid removed", "mL", _points(sessions, "scheduled_date", "fluid_removed_ml", 0)),
        ("Session duration", "min", _points(sessions, "scheduled_date", "duration_minutes", 0)),
        ("Pre systolic BP", "mmHg", _points(sessions, "scheduled_date", "pre_systolic_bp", 0)),
        ("Post systolic BP", "mmHg", _points(sessions, "scheduled_date", "post_systolic_bp", 0)),
        ("Peritoneal UF", "mL", _points(pd_rows, "session_date", "total_uf_ml", 0)),
    ]
    series = [{"label": label, "unit": unit, "points": pts}
              for label, unit, pts in candidates if len(pts) >= 2]

    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "therapy", "label": "Therapy"},
                 {"key": "name", "label": "Detail"}, {"key": "session", "label": "Session"},
                 {"key": "status", "label": "Status"}],
        rows=rows,
    )


# ── Symptoms ─────────────────────────────────────────────────────────────

async def _symptoms_summary(db: AsyncSession, uid: int) -> Summary:
    rows = (await db.execute(
        select(SymptomLog).where(SymptomLog.user_id == uid)
        .order_by(SymptomLog.log_date.desc()).limit(6)
    )).scalars().all()
    if not rows:
        return Summary(empty_reason="No symptoms logged.")
    total = (await db.execute(
        select(func.count(SymptomLog.id)).where(SymptomLog.user_id == uid))).scalar() or 0
    return Summary(
        items=[{"label": r.symptom_name, "value": r.severity,
                "unit": "/10" if r.severity is not None else None,
                "danger": bool(r.severity is not None and r.severity >= 7)} for r in rows],
        count=int(total), last_updated=str(rows[0].log_date),
    )


async def _symptoms_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    rows = (await db.execute(
        select(SymptomLog).where(SymptomLog.user_id == uid, SymptomLog.log_date >= _window(days))
        .order_by(SymptomLog.log_date)
    )).scalars().all()
    by_name: OrderedDict[str, list] = OrderedDict()
    for r in rows:
        if r.severity is not None:
            by_name.setdefault(r.symptom_name, []).append(r)
    series = [{
        "label": name, "unit": "/10",
        "points": [{"date": str(r.log_date), "value": r.severity} for r in rs],
    } for name, rs in by_name.items() if len(rs) >= 2]
    series.sort(key=lambda s: len(s["points"]), reverse=True)

    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "symptom", "label": "Symptom"},
                 {"key": "severity", "label": "Severity"}, {"key": "body_part", "label": "Site"},
                 {"key": "quality", "label": "Quality"}],
        rows=[{"date": str(r.log_date), "symptom": r.symptom_name, "severity": r.severity,
               "body_part": r.body_part, "quality": r.quality,
               "danger": bool(r.severity is not None and r.severity >= 7)}
              for r in reversed(rows)],
    )


# ── Lifestyle ────────────────────────────────────────────────────────────

async def _lifestyle_summary(db: AsyncSession, uid: int) -> Summary:
    row = (await db.execute(
        select(LifestyleEntry).where(LifestyleEntry.user_id == uid)
        .order_by(LifestyleEntry.entry_date.desc()).limit(1)
    )).scalar_one_or_none()
    if row is None:
        return Summary(empty_reason="No lifestyle entries.")
    items = []
    for label, val, unit in (("Weight", row.weight_kg, "kg"), ("BMI", row.bmi, None),
                             ("Resting HR", row.resting_heart_rate, "bpm")):
        if val is not None:
            items.append({"label": label, "value": _round(val), "unit": unit})
    if row.smoking_status:
        items.append({"label": "Smoking", "value": row.smoking_status})
    total = (await db.execute(
        select(func.count(LifestyleEntry.id)).where(LifestyleEntry.user_id == uid))).scalar() or 0
    return Summary(items=items, count=int(total), last_updated=str(row.entry_date))


async def _lifestyle_detail(db: AsyncSession, uid: int, days: int) -> Detail:
    rows = (await db.execute(
        select(LifestyleEntry).where(
            LifestyleEntry.user_id == uid, LifestyleEntry.entry_date >= _window(days))
        .order_by(LifestyleEntry.entry_date)
    )).scalars().all()
    series = []
    for label, attr, unit in (("Weight", "weight_kg", "kg"), ("BMI", "bmi", ""),
                              ("Resting HR", "resting_heart_rate", "bpm")):
        pts = [{"date": str(r.entry_date), "value": _round(getattr(r, attr))}
               for r in rows if getattr(r, attr) is not None]
        if len(pts) >= 2:
            series.append({"label": label, "unit": unit, "points": pts})
    return Detail(
        series=series,
        columns=[{"key": "date", "label": "Date"}, {"key": "weight", "label": "Weight"},
                 {"key": "bmi", "label": "BMI"}, {"key": "hr", "label": "Resting HR"},
                 {"key": "smoking", "label": "Smoking"}],
        rows=[{"date": str(r.entry_date), "weight": _round(r.weight_kg), "bmi": _round(r.bmi),
               "hr": r.resting_heart_rate, "smoking": r.smoking_status}
              for r in reversed(rows)],
    )


# ── Registry ─────────────────────────────────────────────────────────────
# Order here is the order of the board. Score leads because it is the single
# number a clinician orients on before reading anything else.

CATEGORIES: list[Category] = [
    Category("score", "Wellness Score", "gauge", _score_summary, _score_detail),
    Category("vitals", "Vitals", "heart-pulse", _vitals_summary, _vitals_detail),
    Category("labs", "Labs", "flask", _labs_summary, _labs_detail),
    Category("medications", "Medications", "pill", _medications_summary, _medications_detail),
    Category("conditions", "Conditions", "activity", _conditions_summary, _conditions_detail),
    Category("nutrition", "Nutrients", "apple", _nutrition_summary, _nutrition_detail),
    Category("fitness", "Fitness", "dumbbell", _fitness_summary, _fitness_detail),
    Category("elimination", "Elimination", "droplets", _elimination_summary, _elimination_detail),
    Category("mood", "Mood", "brain", _mood_summary, _mood_detail),
    Category("symptoms", "Symptoms", "thermometer", _symptoms_summary, _symptoms_detail),
    Category("dialysis", "Therapies", "cross", _therapies_summary, _therapies_detail),
    Category("lifestyle", "Lifestyle", "heart", _lifestyle_summary, _lifestyle_detail),
    Category("journal", "Journal", "book", _journal_summary, _journal_detail),
    Category("connected_records", "Connected Records", "link",
             _connected_summary, _connected_detail),
]

BY_KEY = {c.key: c for c in CATEGORIES}

# The wellness score is derived from data the patient already shared, so it is
# not a grant type of its own — `all`, or any grant at all, surfaces it.
ALWAYS_VISIBLE = {"score"}
