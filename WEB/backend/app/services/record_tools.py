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

import json
import logging
import re
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

#: Kept under the loop's own 24k cut-off, which slices mid-JSON and hands the
#: model a mangled object. A tool that knows its own shape can shed detail in a
#: sensible order and SAY what it dropped; a blind character cut cannot.
_RESULT_BUDGET = 20_000

#: Column names, declared once so `tests/test_ai_tool_use.py` can assert every
#: one exists on its model. They are NOT decoration: the first version of this
#: module read `systolic_bp`, `heart_rate`, `temperature_c`, `oxygen_saturation`
#: and `blood_glucose` off VitalsLog — five names that do not exist — and
#: `getattr(r, col, None)` turned each into a silent omission. The tool returned
#: a date and a weight, and the model, given a row with no blood pressure in it,
#: correctly reported that none was recorded. §3ag: eleven wrong column names,
#: found by a static check rather than by behaviour.
#: The columns that are NOT nutrients. Everything else on the row IS one, so
#: this is the list that stays small and stable while the nutrient panel grows.
#:
#: The first version of this module did the opposite — a hand-written allowlist
#: of fourteen "important" nutrients. NutritionLog has 58 columns, so it dropped
#: forty-four of them before the model ever saw them, INCLUDING
#: `vitamin_b9_folate_mcg`, which is populated on 1,215 of 1,286 rows. Asked
#: whether she had met her folate target, the assistant answered "the nutrient
#: breakdown provided does not include folic acid data" — on a patient with
#: chronic anaemia, for whom folate is exactly the nutrient that matters. The
#: figure was in the row; the tool discarded it and the model reported the gap
#: honestly. A curated list is a decision about which nutrients matter, taken
#: months earlier by someone who could not know the question.
_NON_NUTRIENT_COLUMNS = frozenset({
    "id", "user_id", "log_date", "meal_type", "food_name", "notes",
    "created_at", "start_time", "end_time", "serving_size", "fdc_id",
    "recipe_url", "food_image_uris", "nutrient_status",
    "pre_meal_weight_kg", "post_meal_weight_kg",
    "extended_nutrients",  # merged in separately — it is a nested panel
})


def _nutrient_columns(model) -> tuple[str, ...]:
    """Every nutrient column on a model, read from the schema.

    Derived rather than listed so a nutrient added to the table is available to
    the assistant the day it lands, with no second edit here to forget.
    """
    return tuple(c.key for c in model.__table__.columns
                 if c.key not in _NON_NUTRIENT_COLUMNS)
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


def _parse_day(value: str, today: date) -> date | None:
    """A date the model actually wrote, or None if it is not a date at all.

    Models say "yesterday" — Claude did, on the first real question asked of
    this tool — so the words are accepted. What must NEVER happen is the silent
    fallback this replaced: an unreadable value fell through to a default and
    quietly produced a SEVEN-DAY window, whose potassium total the model then
    reported as one day's intake (7,699 mg). A bad argument became a wrong
    clinical number, which is worse than an error (§3aa).
    """
    text = str(value).strip().lower()
    if text in ("today", "now"):
        return today
    if text == "yesterday":
        return today - timedelta(days=1)
    if text in ("tomorrow",):
        return today + timedelta(days=1)
    match = re.fullmatch(r"(\d+)\s*days?\s*ago", text)
    if match:
        return today - timedelta(days=int(match.group(1)))
    try:
        y, m, d = (int(x) for x in text[:10].split("-"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def _window(start: str | None, end: str | None,
            today: date | None = None) -> tuple[date, date]:
    """Resolve the requested range. Raises ValueError on an unreadable date."""
    # The patient's today, not the server's. The containers run UTC, so
    # `date.today()` is already tomorrow for anyone west of Greenwich by early
    # evening — and "what did I eat today?" then queries a day with no rows
    # (app/core/patient_time.py).
    today = today or date.today()
    if not start and not end:
        return today, today          # "no dates" means today, not a window

    parsed = {}
    for label, raw in (("start_date", start), ("end_date", end)):
        if not raw:
            continue
        day = _parse_day(raw, today)
        if day is None:
            raise ValueError(
                f"{label}={raw!r} is not a date I can read. Use YYYY-MM-DD, or "
                f"'today' / 'yesterday' / 'N days ago'.")
        parsed[label] = day

    e = parsed.get("end_date", parsed.get("start_date", today))
    s = parsed.get("start_date", e - timedelta(days=_DEFAULT_DAYS - 1))
    return (s, e) if s <= e else (e, s)


def _period_block(dates: list, s: date, e: date, label: str) -> dict[str, Any]:
    """Days in range vs days that actually hold entries.

    Every count over a range invites the same error a nutrient total did:
    compared against a per-day expectation it is wrong by a factor of the
    window. Stating both denominators is what makes the comparison decidable
    without the model inferring a number of days.
    """
    days_in_range = (e - s).days + 1
    days_with = len(set(dates))
    return {
        "days_in_range": days_in_range,
        f"days_with_{label}": days_with,
        f"{label}_total": len(dates),
        f"{label}_per_day": round(len(dates) / days_in_range, 2),
    }


def _normalise(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


#: What a meal carries when no nutrient is named — enough to answer "what did I
#: eat" and the renal questions this app exists for, without hauling back 101
#: fields per meal. Anything else is one named request away.
_CORE_MEAL_FIELDS = (
    "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g",
    "sodium_mg", "potassium_mg", "phosphorus_mg", "calcium_mg",
)


def _match_nutrients(requested: list[str]) -> tuple[set[str], list[str], dict[str, Any]]:
    """Resolve loosely-worded nutrient names against the FDA/USDA catalog.

    `app/core/nutrition_data.py` is the one list — 116 nutrients, each with its
    USDA FoodData Central id, human name, unit and RDA. Matching against it
    rather than against raw column names means "folic acid" finds `folic_acid_mcg`
    by its NAME, and it means a nutrient we track but have no value for is a
    different answer from one we do not track at all.

    Returns (field keys, unmatched terms, reference) where reference carries the
    name, unit and RDA — so the model can say what the target IS instead of
    "your daily aim for folate is not specified in your current targets".
    """
    from app.core.nutrition_data import get_nutrient_catalog

    catalog = get_nutrient_catalog()
    hits: set[str] = set()
    misses: list[str] = []
    reference: dict[str, Any] = {}
    family_of: dict[str, str] = {}
    for want in requested:
        term = _normalise(want)
        if not term:
            continue
        found = [n for n in catalog
                 if term in _normalise(n["key"]) or term in _normalise(n.get("name", ""))]
        if not found:
            misses.append(str(want))
            continue
        # Expand to the whole measurement family. USDA reports folate four
        # ways and the RDA sits on only two of them, so a request for "folic
        # acid" that returned `folic_acid_mcg` alone would answer 7 µg against
        # a 400 µg target while total folate was 108 µg. The grouping is data
        # in the catalog, not a table here.
        families = {n["family"] for n in found if n.get("family")}
        if families:
            found = found + [n for n in catalog
                             if n.get("family") in families and n not in found]
        for n in found:
            hits.add(n["key"])
            if n.get("family"):
                family_of[n["key"]] = n["family"]
            entry = {"name": n.get("name"), "unit": n.get("unit")}
            if n.get("rda") is not None:
                # NOT called "rda". This is the general adult figure from the
                # USDA catalog, and for a renal patient it is the WRONG number:
                # potassium's RDA is 4,700 mg while this patient's computed
                # limit is 2,800 mg max. Naming it plainly stops it being read
                # as the patient's own target — the DAILY NUTRIENT TARGETS
                # section is where that lives, and it wins.
                entry["general_adult_reference_per_day"] = n["rda"]
            reference[n["key"]] = entry
    return hits, misses, reference, family_of


async def get_meals(
    db: AsyncSession, user_id: int, *,
    start_date: str | None = None, end_date: str | None = None,
    nutrients: list[str] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Logged food, with the nutrients asked for — or a sensible core set.

    Every nutrient the record holds is reachable here: the ~40 columns on the
    row plus the extended JSON panel (amino acids, carotenoids, the folate
    breakdown, fatty-acid fractions). The tool used to return a hand-written
    fourteen, so folate — populated on 1,215 of 1,286 rows — never reached the
    model, and it correctly reported that it had no folic acid data for a
    patient with chronic anaemia.

    Returning ALL of them on every call is the other extreme: 101 fields a meal,
    ~48k characters for a week, cut mid-JSON by the loop's cap. A question about
    folate should fetch folate.
    """
    from app.models.nutrition import NutritionLog

    s, e = _window(start_date, end_date, today)
    rows = (await db.execute(
        select(NutritionLog)
        .where(NutritionLog.user_id == user_id,
               NutritionLog.log_date >= s, NutritionLog.log_date <= e)
        .order_by(NutritionLog.log_date, NutritionLog.id)
        .limit(_MAX_ROWS)
    )).scalars().all()

    panels = [r.extended_nutrients if isinstance(r.extended_nutrients, dict) else {}
              for r in rows]

    misses: list[str] = []
    reference: dict[str, Any] = {}
    family_of: dict[str, str] = {}
    if nutrients:
        wanted, misses, reference, family_of = _match_nutrients(nutrients)
        wanted |= {"calories"}
    else:
        wanted = set(_CORE_MEAL_FIELDS)

    def _row(r, panel):
        out = {"date": str(r.log_date), "meal": r.meal_type, "food": r.food_name}
        for field in sorted(wanted):
            v = getattr(r, field, None)
            if v is None:
                v = panel.get(field)
            if v is None:
                continue
            try:
                out[field] = round(float(v), 2)
            except (TypeError, ValueError):
                out[field] = v
        if getattr(r, "nutrient_status", None) not in (None, "done"):
            # A pending estimate is not a zero.
            out["nutrient_status"] = r.nutrient_status
        return out

    out: dict[str, Any] = {
        "range": {"start": str(s), "end": str(e)},
        "count": len(rows),
        "meals": [_row(r, p) for r, p in zip(rows, panels)],
    }
    # ── Period arithmetic belongs to the server ────────────────────────
    #
    # Asked "how have I done with Vit Bs over the last 7 days?", the model
    # summed 7 days of meals and compared the TOTAL to a per-DAY reference:
    # 576 mcg of folate against a 400 mcg target, reported as "Excellent,
    # well above". The daily average was 82 mcg — 21% of target — on a patient
    # with chronic anaemia. The clinical conclusion inverted completely.
    #
    # Nothing in the payload was false; the shape invited the error. So the
    # comparison-ready quantity is computed here, next to the reference that
    # names its own period, and the model never has to divide by a number of
    # days it has to infer.
    days_in_range = (e - s).days + 1
    days_with_meals = len({m["date"] for m in out["meals"]})
    measured = sorted({k for m in out["meals"] for k in m
                       if k not in ("date", "meal", "food", "nutrient_status")})
    # Counted by ABSENCE OF VALUES, not by `nutrient_status`. Status "skipped"
    # carries real figures on 902 of 960 production rows — flagging on it would
    # have declared nearly every total an undercount and taught the model to
    # distrust good data. Only a meal with no value at all is a gap.
    unestimated = sum(1 for m in out["meals"]
                      if not any(isinstance(m.get(f), (int, float)) for f in measured))
    period: dict[str, Any] = {
        "days_in_range": days_in_range,
        "days_with_meals": days_with_meals,
        "meals": len(out["meals"]),
    }
    if unestimated:
        # These contribute nothing to a sum, so the total is an UNDERCOUNT —
        # not a low intake (§3c: a pending estimate is not a zero).
        period["meals_with_no_nutrient_values"] = unestimated
        period["totals_are_undercounts"] = True
    out["period"] = period
    if measured:
        totals: dict[str, Any] = {}
        for field in measured:
            values = [m[field] for m in out["meals"] if isinstance(m.get(field), (int, float))]
            if not values:
                continue
            total = round(sum(values), 2)
            per_day = round(total / days_in_range, 2)
            entry: dict[str, Any] = {
                "total_over_range": total,
                "per_day": per_day,
                "per_day_logged": (round(total / days_with_meals, 2)
                                   if days_with_meals else None),
            }
            ref = (reference.get(field) or {}).get("general_adult_reference_per_day")
            if ref:
                # Computed here so the judgement cannot drift from the figure.
                # The model called 63% of the folate target "Excellent" on a
                # patient with chronic anaemia; a percentage with no agreed
                # wording gets whatever adjective the model reaches for.
                pct = round(100 * per_day / ref)
                entry["percent_of_reference_per_day"] = pct
                entry["status"] = (
                    "at_or_above_reference" if pct >= 100
                    else "slightly_below" if pct >= 90
                    else "below" if pct >= 70
                    else "well_below" if pct >= 40
                    else "very_low")
            totals[field] = entry
        if totals:
            out["totals"] = totals
            out["how_to_compare"] = (
                "Compare `per_day` with `general_adult_reference_per_day` and "
                "with the patient's own DAILY targets. NEVER compare "
                "`total_over_range` to a per-day figure — over "
                f"{days_in_range} days that overstates intake by up to "
                f"{days_in_range}x. `per_day` divides by every day in the "
                f"range ({days_in_range}); `per_day_logged` divides only by "
                f"days with meals ({days_with_meals}) — say which you used. "
                "Use the `status` word as given: anything below 100% of the "
                "reference is a shortfall, not a success. Do not call a "
                "`below` or `well_below` result good, strong or excellent.")

    if reference:
        # Name, unit and a general reference travel with the values, so the
        # answer can state a target rather than "your daily aim is not
        # specified" — which is what a patient with chronic anaemia was told
        # about folate.
        out["nutrient_reference"] = reference
        out["reference_note"] = (
            "`general_adult_reference_per_day` is the USDA figure for a "
            "healthy adult, PER DAY. "
            "Where this patient has their own target (see DAILY NUTRIENT "
            "TARGETS), THAT figure governs and this one must not be quoted "
            "instead — their potassium limit is far below the adult RDA. Where "
            "the patient has NO target for a nutrient, use this reference and "
            "say it is the general adult figure. Do not answer that no target "
            "exists and stop there.")
        # Reported per FAMILY, not per field. Asking for "folate" returns four
        # USDA measurements and three are usually NULL, so listing them
        # individually put "tracked_but_no_value: 3" in front of the model
        # beside a perfectly good folate figure — and it answered "there is no
        # folic-acid target recorded". A family with ANY value is not missing.
        has_value = {k for k in reference if any(k in m for m in out["meals"])}
        families_with_value = {family_of[k] for k in has_value if k in family_of}
        empty = sorted(
            k for k in reference
            if k not in has_value
            and family_of.get(k) not in families_with_value
        )
        if empty:
            out["tracked_but_no_value"] = empty
    if misses:
        out["not_tracked"] = misses
    if not nutrients:
        out["more_nutrients_available"] = (
            "Only core nutrients are shown. Call again with `nutrients` to get "
            "any other the record holds (e.g. folate, vitamin D, zinc, "
            "selenium, omega-3, individual amino acids).")

    # Safety net for a wide range even at this width.
    while (len(json.dumps(out, default=str)) > _RESULT_BUDGET
           and len(out["meals"]) > 1):
        out["meals"] = out["meals"][1:]
    dropped = len(rows) - len(out["meals"])
    if dropped:
        out["omitted_oldest"] = dropped

    return out


async def get_eliminations(
    db: AsyncSession, user_id: int, *,
    start_date: str | None = None, end_date: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Bowel movements and vomiting episodes in a date range."""
    from app.models.elimination import BowelMovement, VomitingLog

    s, e = _window(start_date, end_date, today)
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
        "period": {
            **_period_block([r.log_date for r in bm], s, e, "bowel_movements"),
            **_period_block([r.log_date for r in vo], s, e, "vomiting"),
        },
    }


async def get_medications(db: AsyncSession, user_id: int, *,
                          days: int = 30,
                          today: date | None = None) -> dict[str, Any]:
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

    since = (today or date.today()) - timedelta(days=max(1, days))
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

    window_days = max(1, days)

    def _with_rate(v) -> dict[str, Any]:
        out = _view(v)
        if v.doses:
            # An AGGREGATE over the window, not a daily dose. "489 doses" reads
            # as a regimen unless the period is stated beside it: over 30 days
            # that is roughly twice a day, and over 365 it is not.
            out["doses_in_window"] = v.doses
            out["doses_per_day"] = round(v.doses / window_days, 2)
            out.pop("dose_count", None)
        return out

    return {
        "since": str(since),
        "window_days": window_days,
        "taken_by_patient": [_with_rate(d) for d in taken][:_MAX_ROWS],
        "administered_during_dialysis": [_with_rate(d) for d in administered][:_MAX_ROWS],
        "prescribed": [_view(m) for m in prescribed][:_MAX_ROWS],
        "how_to_read": (
            f"`doses_in_window` counts the whole {window_days}-day window; "
            "`doses_per_day` is the rate. Neither is a prescribed dose — "
            "`prescribed` carries that, and prescribed is not the same fact as "
            "taken. Drugs under `administered_during_dialysis` are given by the "
            "unit and appear in no dose log the patient fills in."),
    }


async def get_vitals(
    db: AsyncSession, user_id: int, *,
    start_date: str | None = None, end_date: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Readings from THREE distinct sources, kept apart.

    A blood pressure is only interpretable with its context. This tool used to
    read `vitals_logs` alone — 41 rows on a patient who also has 2,013 dialysis
    sessions carrying pre/post pairs and 16,236 readings taken DURING treatment.
    §3aa in a new table: reading one source and calling it the answer.

    The three are never merged, because they answer different questions:

      self_recorded   what the patient measured at home
      pre_dialysis    before the session — the volume-loaded end of the day
      post_dialysis   after fluid removal — routinely 20-40 mmHg lower
      intradialytic   during treatment, where the NADIR matters: a mean hides
                      the intradialytic hypotension that a session ending below
                      90 systolic actually represents

    Averaging across them produces a number describing no clinical state at
    all — the same error as printing pre-systolic over post-systolic and
    calling it "91/83" (§3an).
    """
    from app.models.chronic_conditions import IntradialyticReading, TherapySession
    from app.models.vitals import VitalsLog

    s, e = _window(start_date, end_date, today)

    logs = (await db.execute(
        select(VitalsLog)
        .where(VitalsLog.user_id == user_id,
               VitalsLog.log_date >= s, VitalsLog.log_date <= e)
        .order_by(VitalsLog.log_date).limit(_MAX_ROWS)
    )).scalars().all()

    def _self(r):
        out = {"date": str(r.log_date)}
        for c in VITALS_FIELDS:
            v = getattr(r, c, None)
            if v is not None:
                out[c] = v
        return out

    # Dialysis measured from actual_end_time where present: scheduled_date is
    # stored at midnight, so measuring from it invents up to a day of error on
    # the one number that decides recency (§3an).
    sessions = (await db.execute(
        select(TherapySession)
        .where(TherapySession.user_id == user_id,
               TherapySession.scheduled_date >= s,
               TherapySession.scheduled_date <= e)
        .order_by(TherapySession.scheduled_date).limit(_MAX_ROWS)
    )).scalars().all()

    readings_by_session: dict[Any, list] = {}
    if sessions:
        ids = [t.id for t in sessions]
        for r in (await db.execute(
            select(IntradialyticReading)
            .where(IntradialyticReading.session_id.in_(ids))
        )).scalars().all():
            readings_by_session.setdefault(r.session_id, []).append(r)

    def _bp(obj, prefix):
        out = {}
        for label, col in (("systolic", f"{prefix}systolic_bp"),
                           ("diastolic", f"{prefix}diastolic_bp"),
                           ("heart_rate", f"{prefix}heart_rate")):
            v = getattr(obj, col, None)
            if v is not None:
                out[label] = v
        return out

    def _summarise_intra(rows):
        """Per-session summary. 16,236 raw readings cannot travel, and the mean
        alone hides the nadir that defines intradialytic hypotension."""
        sys_v = [r.systolic_bp for r in rows if r.systolic_bp is not None]
        dia_v = [r.diastolic_bp for r in rows if r.diastolic_bp is not None]
        pulse = [r.pulse for r in rows if r.pulse is not None]
        if not (sys_v or dia_v or pulse):
            return None
        out: dict[str, Any] = {"readings": len(rows)}
        if sys_v:
            out["systolic_lowest"] = min(sys_v)
            out["systolic_mean"] = round(sum(sys_v) / len(sys_v), 1)
            out["systolic_highest"] = max(sys_v)
            below_90 = sum(1 for v in sys_v if v < 90)
            if below_90:
                out["readings_below_90_systolic"] = below_90
        if dia_v:
            out["diastolic_lowest"] = min(dia_v)
            out["diastolic_mean"] = round(sum(dia_v) / len(dia_v), 1)
        if pulse:
            out["pulse_mean"] = round(sum(pulse) / len(pulse), 1)
        return out

    dialysis = []
    for t in sessions:
        entry: dict[str, Any] = {"date": str(t.scheduled_date)[:10]}
        for label, prefix in (("pre_dialysis", "pre_"), ("post_dialysis", "post_"),
                              ("pre_standing", "pre_standing_"),
                              ("post_standing", "post_standing_")):
            bp = _bp(t, prefix)
            if bp:
                entry[label] = bp
        intra = _summarise_intra(readings_by_session.get(t.id, []))
        if intra:
            entry["intradialytic"] = intra
        if len(entry) > 1:
            dialysis.append(entry)

    out: dict[str, Any] = {
        "range": {"start": str(s), "end": str(e)},
        "self_recorded": [_self(r) for r in logs],
        "dialysis": dialysis,
        "period": {
            **_period_block([r.log_date for r in logs], s, e, "self_recorded"),
            "dialysis_sessions": len(dialysis),
        },
    }
    if dialysis or logs:
        out["how_to_compare"] = (
            "pre_dialysis, post_dialysis, intradialytic and self_recorded are "
            "DIFFERENT measurements — never average them together or quote one "
            "as the patient's blood pressure. Post-dialysis runs well below "
            "pre-dialysis by design. State each separately as systolic/"
            "diastolic; do not pair a pre-systolic with a post-systolic. For "
            "intradialytic, the LOWEST reading matters more than the mean.")
    return out


async def get_labs(db: AsyncSession, user_id: int, *,
                   since_days: int = 365, limit: int = 60,
                   today: date | None = None) -> dict[str, Any]:
    """Lab results, most recent first, with their dates.

    Dates matter more than values here: a result months old is history, and
    the model must be able to see that rather than treat it as current.
    """
    from app.models.labs import LabResult

    since = (today or date.today()) - timedelta(days=max(1, since_days))
    rows = (await db.execute(
        select(LabResult)
        .where(LabResult.user_id == user_id, LabResult.test_date >= since)
        .order_by(LabResult.test_date.desc())
        .limit(min(limit, _MAX_ROWS))
    )).scalars().all()
    # The recency rule is already defined for this codebase — 14 days fresh,
    # 30 days stale (dialysis_day_adjustment, scaled to a monthly draw cadence).
    # Returning a 147-day-old draw beside a fresh one with nothing to tell them
    # apart is how advice gets built on a number nobody has checked in five
    # months (§3an). Imported here rather than re-declared, so one definition
    # governs both.
    from app.services.dialysis_day_adjustment import FRESH_DAYS, STALE_DAYS

    reference = today or date.today()

    def _row(r):
        age = (reference - r.test_date).days if r.test_date else None
        out = {"date": str(r.test_date), "test": r.test_name, "value": r.value,
               "unit": r.unit, "abnormal": r.is_abnormal}
        if age is not None:
            out["age_days"] = age
            out["recency"] = ("current" if age <= FRESH_DAYS
                              else "ageing" if age < STALE_DAYS
                              else "out_of_date")
        return out

    labs = [_row(r) for r in rows]
    out: dict[str, Any] = {"since": str(since), "count": len(labs), "labs": labs}
    if labs and all(l.get("recency") == "out_of_date" for l in labs):
        # Every value is older than the staleness window. That is a finding —
        # "no current labs" — not a set of current results.
        out["no_current_labs"] = True
        out["recency_note"] = (
            f"Every result here is more than {STALE_DAYS} days old. Report them "
            "as historical and say when they were drawn; do not present them as "
            "the patient's current values.")
    return out


#: The tool surface, in Anthropic's schema. Descriptions are written for the
#: MODEL to choose between them — they describe the data, never the phrasing of
#: any question.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_meals",
        "description": "Food the patient logged. Returns calories and the core "
                       "nutrients by default; pass `nutrients` to get ANY other "
                       "the record holds — every vitamin and mineral, the folate "
                       "breakdown, amino acids, carotenoids, fatty-acid "
                       "fractions. If a question is about one nutrient, ASK FOR "
                       "THAT NUTRIENT rather than pulling everything.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description":
                    "YYYY-MM-DD, inclusive. OMIT to mean today — do not guess a "
                    "date. The server knows the current date; you do not."},
                "end_date": {"type": "string", "description":
                    "YYYY-MM-DD, inclusive. OMIT to mean today."},
                "nutrients": {
                    "type": "array", "items": {"type": "string"},
                    "description":
                        "Nutrients to include, named however you like — 'folate', "
                        "'folic acid', 'vitamin D', 'zinc', 'omega 3'. Matched "
                        "loosely against the record, so you do not need the "
                        "column name. Anything not recorded comes back under "
                        "`not_recorded` so you can say so plainly.",
                },
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

#: What to SHOW the patient while each tool runs. The backend owns this text
#: rather than each client, so web, iOS and Android cannot drift apart and a new
#: tool does not need three app releases to get a label.
#:
#: Deliberately NOT a key inside `TOOL_SPECS`: the Anthropic adapter sends those
#: dicts to the provider verbatim, so an extra field there reaches the API as an
#: unknown key. `tests/test_ai_tool_use.py` pins both halves — every tool has a
#: label, and no spec carries a field the wire does not expect.
TOOL_LABELS = {
    "get_meals": "Checking your meals",
    "get_eliminations": "Checking your symptom log",
    "get_medications": "Checking your medications",
    "get_vitals": "Checking your vitals",
    "get_labs": "Checking your lab results",
}

TOOLS = {
    "get_meals": get_meals,
    "get_eliminations": get_eliminations,
    "get_medications": get_medications,
    "get_vitals": get_vitals,
    "get_labs": get_labs,
}


async def run_tool(db: AsyncSession, user_id: int, name: str,
                   arguments: dict[str, Any],
                   today: date | None = None) -> dict[str, Any]:
    """Execute one tool call. Errors are returned, never raised.

    A tool that raises would abort the whole answer; a tool that reports its
    failure lets the model say what it could not check.
    """
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"no such tool: {name}"}
    try:
        # `today` is passed by the loop, never by the model: a model does not
        # know the date and must not be asked to supply one.
        return await fn(db, user_id, today=today, **(arguments or {}))
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    except ValueError as exc:
        # Unreadable date. Returned, never guessed around: the guess produced a
        # week's potassium reported as one day's.
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("tool %s failed", name, exc_info=True)
        return {"error": f"{name} failed: {type(exc).__name__}"}
