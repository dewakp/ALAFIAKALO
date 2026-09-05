"""The patient's record, as tools a model can call. No question parsing here.

Earlier attempts at this problem all failed the same way: they tried to
recognise the QUESTION.

  * `_QUERY_SECTION_MAP` — eight keyword lists deciding which sections the
    model could see. "sugar" was in none of them.
  * a trailing-"?" rule, then an interrogative-opener rule, to tell a question
    from a command.
  * `wants_ranking = any(w in q for w in ("contributed", "most", "highest"))`
    and a nutrient alias table, to work out what a question was asking for.

Every one of those is a guess about phrasing, and every one was missing the
word the patient used. The model is better at understanding the question than
any table we can write; what it lacks is the DATA. So this module supplies
data, on request, with structured arguments the model chooses — and contains
no opinion whatsoever about how a question might be worded.

That also answers "why am I purging?" properly. Nobody has to predict that the
question needs eliminations and meals first, and medications and vitals only
if the first pass suggests it. The model asks for eliminations, reads them,
and asks for more if it needs more.

PRIVACY. These return CLINICAL rows only — no name, no email, no date of
birth, no clinician or facility names. Identity is stripped at egress (§3al)
and nothing here reintroduces it. The tool results are also far smaller than
the 40k-character whole-record dump they replace, so a question that needs one
day of meals now sends one day of meals.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: A window nobody asked for is a window that hides data. When a caller gives
#: no dates we answer for a sensible recent span and SAY which span we used,
#: so the model can widen it rather than assume it saw everything.
#:
#: Omitting a date means TODAY, and the tool descriptions say so, because a
#: model does not reliably know what today is. Told "Today is 2026-09-05" in
#: the system prompt, one still called get_meals for 2024-12-19 — its training
#: cutoff — and reported the patient had no meals logged. The server has a
#: clock; the model should never be asked to supply one.
_DEFAULT_DAYS = 7
_MAX_ROWS = 500

#: Column names, declared once so `tests/test_ai_tool_use.py` can assert every
#: one exists on its model. They are NOT decoration: the first version of this
#: module read `systolic_bp`, `heart_rate`, `temperature_c`, `oxygen_saturation`
#: and `blood_glucose` off VitalsLog — five names that do not exist — and
#: `getattr(r, col, None)` turned each into a silent omission. The tool returned
#: a date and a weight, and the model, given a row with no blood pressure in it,
#: correctly reported that none was recorded. §3ag: eleven wrong column names,
#: found by a static check rather than by behaviour.
MEAL_FIELDS = (
    "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g",
    "sodium_mg", "potassium_mg", "phosphorus_mg", "calcium_mg", "iron_mg",
    "magnesium_mg", "cholesterol_mg", "saturated_fat_g",
)
VITALS_FIELDS = (
    "blood_pressure_systolic", "blood_pressure_diastolic", "heart_rate_bpm",
    "weight_kg", "body_temperature_c", "blood_oxygen_pct",
    "blood_glucose_mg_dl", "respiratory_rate", "pain_level",
)
BOWEL_FIELDS = ("bristol_scale", "consistency", "color", "blood_present",
                "urgency", "straining", "notes")
VOMIT_FIELDS = ("volume", "consistency", "color", "contains_blood",
                "contains_bile", "nausea_before", "trigger", "notes")
LAB_FIELDS = ("test_date", "test_name", "value", "unit", "is_abnormal")


def _window(start: str | None, end: str | None) -> tuple[date, date]:
    today = date.today()
    def _p(v, fallback):
        if not v:
            return fallback
        try:
            y, m, d = (int(x) for x in str(v)[:10].split("-"))
            return date(y, m, d)
        except (ValueError, TypeError):
            return fallback
    if not start and not end:
        return today, today          # "no dates" means today, not a window
    e = _p(end, today)
    s = _p(start, e - timedelta(days=_DEFAULT_DAYS - 1))
    return (s, e) if s <= e else (e, s)


async def get_meals(
    db: AsyncSession, user_id: int, *,
    start_date: str | None = None, end_date: str | None = None,
) -> dict[str, Any]:
    """Every logged food item in a date range, with its full nutrient row."""
    from app.models.nutrition import NutritionLog

    s, e = _window(start_date, end_date)
    rows = (await db.execute(
        select(NutritionLog)
        .where(NutritionLog.user_id == user_id,
               NutritionLog.log_date >= s, NutritionLog.log_date <= e)
        .order_by(NutritionLog.log_date, NutritionLog.id)
        .limit(_MAX_ROWS)
    )).scalars().all()

    def _row(r):
        out = {"date": str(r.log_date), "meal": r.meal_type, "food": r.food_name}
        for col in MEAL_FIELDS:
            v = getattr(r, col, None)
            if v is not None:
                out[col] = round(float(v), 2)
        if getattr(r, "nutrient_status", None) not in (None, "done"):
            # A pending estimate is not a zero. Saying so stops the model
            # reporting an absent figure as an absent nutrient.
            out["nutrient_status"] = r.nutrient_status
        return out

    return {"range": {"start": str(s), "end": str(e)},
            "count": len(rows), "meals": [_row(r) for r in rows]}


async def get_eliminations(
    db: AsyncSession, user_id: int, *,
    start_date: str | None = None, end_date: str | None = None,
) -> dict[str, Any]:
    """Bowel movements and vomiting episodes in a date range."""
    from app.models.elimination import BowelMovement, VomitingLog

    s, e = _window(start_date, end_date)
    bm = (await db.execute(
        select(BowelMovement)
        .where(BowelMovement.user_id == user_id,
               BowelMovement.log_date >= s, BowelMovement.log_date <= e)
        .order_by(BowelMovement.log_date).limit(_MAX_ROWS)
    )).scalars().all()
    vo = (await db.execute(
        select(VomitingLog)
        .where(VomitingLog.user_id == user_id,
               VomitingLog.log_date >= s, VomitingLog.log_date <= e)
        .order_by(VomitingLog.log_date).limit(_MAX_ROWS)
    )).scalars().all()

    def _pick(r, cols):
        out = {"date": str(r.log_date)}
        for c in cols:
            v = getattr(r, c, None)
            if v not in (None, ""):
                out[c] = str(v)
        return out

    return {
        "range": {"start": str(s), "end": str(e)},
        "bowel_movements": [_pick(r, BOWEL_FIELDS) for r in bm],
        "vomiting": [_pick(r, VOMIT_FIELDS) for r in vo],
    }


async def get_medications(db: AsyncSession, user_id: int, *,
                          days: int = 30) -> dict[str, Any]:
    """What the patient has actually TAKEN, and what is prescribed.

    Both, labelled — §3aa: prescribed and taken are different facts, and a
    reader given only one of them draws the wrong conclusion.
    """
    # THREE sources, not two. §3aa: a review that checked only prescriptions
    # and dose logs concluded "no ESA prescribed or taken" while the patient
    # had been on one for years — the drugs given DURING dialysis live in
    # therapy_sessions.drugs_administered and are in neither of the others.
    # The `hasattr` guards this once had would have returned empty lists for
    # all three if the names were wrong, which is the same failure in code.
    from app.services import clinical_sources

    since = date.today() - timedelta(days=max(1, days))
    taken = await clinical_sources.medications_taken(db, user_id, since=since)
    administered = await clinical_sources.medications_administered(db, user_id, since=since)
    prescribed = await clinical_sources.medications_prescribed(db, user_id)

    # All three sources return the SAME `MedicationView`, so there is one
    # serialiser rather than three guesses at field names. The guesses were
    # wrong: `medication_name`/`dose_amount`/`dose_unit`/`log_date` exist on
    # none of them, so every taken medication serialised to `{}` and the model
    # — handed four empty objects — reported that nothing had been taken, on a
    # patient with four dose-logged drugs. The data was there; the tool threw
    # it away and the answer read like a clinical finding.
    def _view(v) -> dict[str, Any]:
        out: dict[str, Any] = {"name": v.name, "active": bool(v.active)}
        if v.detail:
            out["detail"] = v.detail
        if v.last:
            out["last_taken"] = str(v.last)
        if v.doses:
            out["dose_count"] = v.doses
        return out

    return {
        "since": str(since),
        "taken_by_patient": [_view(d) for d in taken][:_MAX_ROWS],
        "administered_during_dialysis": [_view(d) for d in administered][:_MAX_ROWS],
        "prescribed": [_view(m) for m in prescribed][:_MAX_ROWS],
    }


async def get_vitals(
    db: AsyncSession, user_id: int, *,
    start_date: str | None = None, end_date: str | None = None,
) -> dict[str, Any]:
    """Recorded vitals in a date range."""
    from app.models.vitals import VitalsLog

    s, e = _window(start_date, end_date)
    rows = (await db.execute(
        select(VitalsLog)
        .where(VitalsLog.user_id == user_id,
               VitalsLog.log_date >= s, VitalsLog.log_date <= e)
        .order_by(VitalsLog.log_date).limit(_MAX_ROWS)
    )).scalars().all()

    def _row(r):
        out = {"date": str(r.log_date)}
        for c in VITALS_FIELDS:
            v = getattr(r, c, None)
            if v is not None:
                out[c] = v
        return out

    return {"range": {"start": str(s), "end": str(e)},
            "count": len(rows), "vitals": [_row(r) for r in rows]}


async def get_labs(db: AsyncSession, user_id: int, *,
                   since_days: int = 365, limit: int = 60) -> dict[str, Any]:
    """Lab results, most recent first, with their dates.

    Dates matter more than values here: a result months old is history, and
    the model must be able to see that rather than treat it as current.
    """
    from app.models.labs import LabResult

    since = date.today() - timedelta(days=max(1, since_days))
    rows = (await db.execute(
        select(LabResult)
        .where(LabResult.user_id == user_id, LabResult.test_date >= since)
        .order_by(LabResult.test_date.desc())
        .limit(min(limit, _MAX_ROWS))
    )).scalars().all()
    return {"since": str(since), "count": len(rows), "labs": [
        {"date": str(r.test_date), "test": r.test_name, "value": r.value,
         "unit": r.unit, "abnormal": r.is_abnormal} for r in rows]}


#: The tool surface, in Anthropic's schema. Descriptions are written for the
#: MODEL to choose between them — they describe the data, never the phrasing of
#: any question.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_meals",
        "description": "Food the patient logged, with the full nutrient breakdown "
                       "of each item (sugar, sodium, potassium, phosphorus, protein, "
                       "calories and more). Use for anything about what they ate or "
                       "how much of a nutrient they consumed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description":
                    "YYYY-MM-DD, inclusive. OMIT to mean today — do not guess a "
                    "date. The server knows the current date; you do not."},
                "end_date": {"type": "string", "description":
                    "YYYY-MM-DD, inclusive. OMIT to mean today."},
            },
        },
    },
    {
        "name": "get_eliminations",
        "description": "Bowel movements and vomiting episodes, with Bristol scale, "
                       "consistency, blood, severity and notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"}, "end_date": {"type": "string"},
            },
        },
    },
    {
        "name": "get_medications",
        "description": "Medications the patient has TAKEN (dose logs) and those "
                       "PRESCRIBED, and those ADMINISTERED during dialysis by the "
                       "unit. All three differ and all three are returned, labelled — "
                       "a drug given at dialysis appears in no dose log.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "look-back, default 30"}},
        },
    },
    {
        "name": "get_vitals",
        "description": "Blood pressure, heart rate, weight, temperature, oxygen "
                       "saturation and glucose readings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"}, "end_date": {"type": "string"},
            },
        },
    },
    {
        "name": "get_labs",
        "description": "Laboratory results with their dates. Check the date before "
                       "treating any value as current.",
        "input_schema": {
            "type": "object",
            "properties": {
                "since_days": {"type": "integer"}, "limit": {"type": "integer"},
            },
        },
    },
]

TOOLS = {
    "get_meals": get_meals,
    "get_eliminations": get_eliminations,
    "get_medications": get_medications,
    "get_vitals": get_vitals,
    "get_labs": get_labs,
}


async def run_tool(db: AsyncSession, user_id: int, name: str,
                   arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute one tool call. Errors are returned, never raised.

    A tool that raises would abort the whole answer; a tool that reports its
    failure lets the model say what it could not check.
    """
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"no such tool: {name}"}
    try:
        return await fn(db, user_id, **(arguments or {}))
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("tool %s failed", name, exc_info=True)
        return {"error": f"{name} failed: {type(exc).__name__}"}
