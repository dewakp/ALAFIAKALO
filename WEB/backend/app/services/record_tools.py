# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

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
from dataclasses import dataclass, field
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
async def get_surgical_history(db: AsyncSession, user_id: int, *,
                               today: date | None = None) -> dict[str, Any]:
    """Hospital stays, every operation, and what they STILL do to the patient.

    This exists because a patient said they take calcium "after removal of
    parathyroid glands" and the assistant had no way to know: the record could
    not hold the fact, so no retrieval could find it and the answer fell back
    to a generic bone-health figure. `lasting_effects` is reported separately
    and first-class, because that is what a question about calcium, phosphate
    or bone actually needs — the operation list alone does not explain it.

    Not windowed. A parathyroidectomy from 2019 governs this patient's calcium
    today, so a default recency window here would hide the whole point.

    PRIVACY (§3al, and this module's contract): facility names and surgeon
    names are deliberately NOT returned, and neither is the canonical reader's
    `admission` label — that label embeds the hospital's name. Whether a
    procedure happened during an inpatient stay is clinical; WHERE it happened
    is identifying and no clinical question here needs it.
    """
    from app.services import clinical_sources

    stays = await clinical_sources.hospitalizations(db, user_id)
    procedures = await clinical_sources.procedures(db, user_id)
    effects = await clinical_sources.lasting_surgical_effects(db, user_id)

    def _procedure(p) -> dict[str, Any]:
        out: dict[str, Any] = {"name": p.name,
                               "during_hospital_stay": p.admission is not None}
        if p.performed:
            out["performed"] = p.performed
        if p.code:
            # The code travels WITH its system or it is unusable — ICD-10-PCS,
            # CPT, SNOMED and ICHI are different vocabularies (§3ad).
            out["code"] = p.code
            out["code_system"] = p.code_system
        if p.body_site:
            out["body_site"] = p.body_site
        if p.outcome:
            out["outcome"] = p.outcome
        if p.ongoing_effects:
            out["ongoing_effects"] = p.ongoing_effects
        return out

    def _stay(s) -> dict[str, Any]:
        out: dict[str, Any] = {"admitted": s.admitted}
        if s.discharged:
            out["discharged"] = s.discharged
        # `nights` is None whenever EITHER end is unknown, so it is reported
        # only when it exists and never turned into "still an inpatient" —
        # `status` is what states that, and inferring it from a missing
        # discharge date would invent a fact (§0).
        if s.nights is not None:
            out["nights"] = s.nights
        if s.status:
            out["status"] = s.status
        if s.admission_type:
            out["admission_type"] = s.admission_type
        if s.reason:
            out["reason"] = s.reason
        if s.diagnosis:
            out["diagnosis"] = s.diagnosis
        if s.procedures:
            out["procedures"] = [_procedure(p) for p in s.procedures]
        return out

    return {
        "hospital_stays": [_stay(s) for s in stays][:_MAX_ROWS],
        # EVERY procedure, including those with no admission. A caller walking
        # stays→procedures loses the day-case and historical operations, which
        # is the half that matters most here.
        "procedures": [_procedure(p) for p in procedures][:_MAX_ROWS],
        "lasting_effects": effects[:_MAX_ROWS],
        "how_to_read": (
            "`lasting_effects` is what past surgery still does to this patient "
            "and is stated in the record, never inferred from a procedure name "
            "— if an operation has a lasting consequence that is not listed "
            "here, the record does not state one, so do not assume it. "
            "`procedures` includes operations with no hospital stay attached. "
            "Facility and surgeon names are not returned."),
    }




# ── the four domains that could be WRITTEN and not READ ────────────────────
#
# Found by the live verification, not by reading the code: asked "how much did
# I sleep last night?", the model called `log_sleep` — because it was the only
# sleep-shaped tool that existed. The write guard refused it ("no sleep detail
# given — nothing was logged") so no row landed and the answer was correct, but
# the cause is the asymmetry: five domains gained a writer and four of them had
# no reader at all.
#
# An assistant that can record a patient's sleep and cannot tell them what it
# recorded is §3am's failure in a new place — the model does not lack
# understanding, it lacks DATA, and given only a write tool it will reach for
# the write tool.

#: What each reader returns, per row. Columns, not prose — a curated subset is
#: a decision about which facts matter taken by someone who cannot know the
#: question (§3am, measured on the 14-nutrient allowlist that hid folate).
SLEEP_FIELDS = ("total_hours", "quality_score", "bedtime", "wake_time",
                "times_awakened", "time_to_fall_asleep_min", "morning_alertness",
                "morning_mood", "notes")
MOOD_FIELDS = ("mood_score", "energy_level", "stress_level", "anxiety_level",
               "sleep_quality", "sleep_hours", "emotions", "triggers",
               "coping_strategies", "journal_entry", "notes")
SYMPTOM_FIELDS = ("symptom_name", "severity", "body_part", "location_specific",
                  "duration_hours", "symptom_type", "quality", "onset",
                  "pattern", "triggers", "relievers", "affects_function",
                  "interferes_sleep", "interferes_work", "self_treatment",
                  "treatment_effective", "sought_medical_care", "notes")
FITNESS_FIELDS = ("activity_type", "duration_minutes", "distance_km",
                  "calories_burned", "heart_rate_avg", "heart_rate_max",
                  "steps", "sets", "reps", "weight_kg", "intensity", "notes")


def _rows(records, date_attr: str, fields: tuple[str, ...]) -> list[dict]:
    """Rows as the record holds them. An absent value is OMITTED, never zeroed:
    §3aa — unmeasured and zero are different facts, and a model handed
    `quality_score: 0` would report a terrible night nobody recorded."""
    out = []
    for r in records:
        row = {"date": str(getattr(r, date_attr))}
        for f in fields:
            v = getattr(r, f, None)
            if v not in (None, ""):
                row[f] = str(v)
        out.append(row)
    return out


async def _simple_history(db: AsyncSession, user_id: int, model, date_attr: str,
                          fields: tuple[str, ...], label: str, *,
                          start_date, end_date, today) -> dict[str, Any]:
    """One windowed read. Shared so four readers cannot drift apart."""
    s, e = _window(start_date, end_date, today)
    col = getattr(model, date_attr)
    rows = (await db.execute(
        select(model)
        .where(model.user_id == user_id, col >= s, col <= e)
        .order_by(col).limit(_MAX_ROWS)
    )).scalars().all()
    return {
        "range": {"start": str(s), "end": str(e)},
        label: _rows(rows, date_attr, fields),
        "period": _period_block([getattr(r, date_attr) for r in rows], s, e, label),
    }


async def get_sleep(db: AsyncSession, user_id: int, *,
                    start_date: str | None = None, end_date: str | None = None,
                    today: date | None = None) -> dict[str, Any]:
    """Nights of sleep on record."""
    from app.models.sleep import SleepLog
    return await _simple_history(db, user_id, SleepLog, "sleep_date",
                                 SLEEP_FIELDS, "sleep",
                                 start_date=start_date, end_date=end_date,
                                 today=today)


async def get_mood(db: AsyncSession, user_id: int, *,
                   start_date: str | None = None, end_date: str | None = None,
                   today: date | None = None) -> dict[str, Any]:
    """Mood entries on record."""
    from app.models.mood import MoodEntry
    return await _simple_history(db, user_id, MoodEntry, "entry_date",
                                 MOOD_FIELDS, "mood",
                                 start_date=start_date, end_date=end_date,
                                 today=today)


async def get_symptoms(db: AsyncSession, user_id: int, *,
                       start_date: str | None = None, end_date: str | None = None,
                       today: date | None = None) -> dict[str, Any]:
    """Symptoms the patient has reported.

    §3am records that symptoms described to the AI used to leave no trace at
    all — *"dizzy, weak" informed one answer and left no trace* — on a patient
    whose dizziness is exactly what a clinician would want a history of. They
    are written now, and this is what makes that history answerable.
    """
    from app.models.conditions import SymptomLog
    return await _simple_history(db, user_id, SymptomLog, "log_date",
                                 SYMPTOM_FIELDS, "symptoms",
                                 start_date=start_date, end_date=end_date,
                                 today=today)


async def get_fitness(db: AsyncSession, user_id: int, *,
                      start_date: str | None = None, end_date: str | None = None,
                      today: date | None = None) -> dict[str, Any]:
    """Activity on record."""
    from app.models.fitness import FitnessLog
    return await _simple_history(db, user_id, FitnessLog, "log_date",
                                 FITNESS_FIELDS, "activity",
                                 start_date=start_date, end_date=end_date,
                                 today=today)


# ═══════════════════════════════════════════════════════════════════════════
# The gated write tools
# ═══════════════════════════════════════════════════════════════════════════
#
# Operator, 2026-10-14, on the five domains that had no write tool at all:
# *"a gated, secure set of write tools."*
#
# Gated means six things, and each one is enforced here rather than hoped for:
#
#   1. CAPABILITY   `run_tool(..., allow_writes=False)` by default. A caller
#                   has to ask. The gate fails CLOSED, so forgetting it makes
#                   the assistant read-only rather than silently able to write.
#   2. CONTRACT     every tool declares the exact columns it may set
#                   (`_WriteSpec.fields`). Nothing reaches a model object that
#                   the spec does not name — no `**kwargs`, no `setattr` loop
#                   over whatever the LLM invented.
#   3. VALIDATION   scales and lengths are checked at the boundary and REFUSED
#                   BY NAME. Never clamped: silently turning a severity of 50
#                   into 10 records a clinical value nobody stated (§3am's
#                   "a bad argument that becomes a wrong clinical number is
#                   worse than an error").
#   4. IDEMPOTENCE  a tool loop retries. Every write checks for the row it is
#                   about to insert, scoped to this patient and this day.
#   5. SCOPE        `user_id` comes from the authenticated session and is
#                   never an argument the model can supply.
#   6. CLOSED SET   vitals and labs stay unwritable, by declaration, with the
#                   reason (`NEVER_WRITABLE`).
#
# And one thing it deliberately does NOT do: interpret. The tool stores the
# patient's own words; the readers that already exist interpret them. Writing
# `blood_present=True` because the patient said "bloody" would put a second
# interpreter beside `elimination_text` (§3ba), and §3ai's rule is that two
# computations of one quantity must not disagree. A value is written only
# where the patient STATED one.


@dataclass(frozen=True)
class _WriteSpec:
    """What one write tool is allowed to touch.

    The model's arguments are matched against this and nothing else, so a tool
    cannot be talked into setting a column its author never considered.
    """
    model: str                      # attribute on app.models
    date_field: str                 # log_date / entry_date / sleep_date
    #: argument -> column, for plain text
    text: dict[str, tuple[str, int]] = field(default_factory=dict)
    #: argument -> (column, low, high), inclusive, refused outside
    scales: dict[str, tuple[str, int, int]] = field(default_factory=dict)
    #: argument -> column, parsed by `_parse_clock`
    clocks: dict[str, str] = field(default_factory=dict)
    #: argument -> (column, low, high) for a real quantity
    numbers: dict[str, tuple[str, float, float]] = field(default_factory=dict)
    #: columns identifying "the same event", for the idempotency check
    identity: tuple[str, ...] = ()


def _apply_spec(spec: _WriteSpec, args: dict[str, Any]) -> tuple[dict, list[str]]:
    """Arguments -> column values, or a list of refusals naming each problem.

    A refusal is a sentence the model can read back to the patient. §3aj: a
    guard that cannot explain itself gets blamed for the thing it did not do.
    """
    values: dict[str, Any] = {}
    refusals: list[str] = []

    for arg, (column, limit) in spec.text.items():
        raw = args.get(arg)
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if len(text) > limit:
            # Truncating would store a clinical sentence with its end cut off,
            # which reads as a complete statement. Refuse and say the limit.
            refusals.append(
                f"{arg} is {len(text)} characters and the record holds "
                f"{limit}; shorten it and try again")
            continue
        values[column] = text

    for arg, (column, low, high) in spec.scales.items():
        raw = args.get(arg)
        if raw is None:
            continue
        try:
            n = int(float(raw))
        except (TypeError, ValueError):
            refusals.append(f"{arg}={raw!r} is not a number from {low} to {high}")
            continue
        if not (low <= n <= high):
            refusals.append(
                f"{arg}={raw} is outside the {low}-{high} scale this record "
                f"uses; ask the patient for a value in that range")
            continue
        values[column] = n

    for arg, (column, low, high) in spec.numbers.items():
        raw = args.get(arg)
        if raw is None:
            continue
        try:
            n = float(raw)
        except (TypeError, ValueError):
            refusals.append(f"{arg}={raw!r} is not a number")
            continue
        if not (low <= n <= high):
            refusals.append(
                f"{arg}={raw} is outside what this field can hold ({low}-{high})")
            continue
        values[column] = n

    for arg, column in spec.clocks.items():
        raw = args.get(arg)
        if raw is None:
            continue
        parsed = _parse_clock(str(raw))
        if parsed is None:
            # §3av: a value that cannot be read is refused, never dropped. The
            # web flowsheet silently discarded unparseable times and ate the
            # reading with them.
            refusals.append(f"{arg}={raw!r} is not a time I can read "
                            f"(try \"20:45\" or \"8:45 pm\")")
            continue
        values[column] = parsed

    return values, refusals


async def _write_row(db: AsyncSession, user_id: int, spec: _WriteSpec,
                     when: date, args: dict[str, Any], *,
                     label: str, confirm: str) -> dict[str, Any]:
    """The one path every gated write takes."""
    from app import models

    model = getattr(models, spec.model)
    values, refusals = _apply_spec(spec, args)
    if refusals:
        return {"error": "nothing was written", "refused": True,
                "problems": refusals,
                "tell_the_patient":
                    "Say what could not be recorded and why, and ask for the "
                    "value again. Nothing was saved."}

    # Idempotency, scoped to this patient and this day. A tool loop retries —
    # a provider hiccup, a round that re-reads the request — and a duplicated
    # clinical row is indistinguishable from a second real event.
    where = [model.user_id == user_id, getattr(model, spec.date_field) == when]
    for column in spec.identity:
        where.append(getattr(model, column) == values.get(column))
    existing = (await db.execute(
        select(model).where(*where).limit(1))).scalars().first()
    if existing is not None:
        return {"already_logged": True, "id": existing.id, "date": str(when),
                "what": label,
                "note": "This is already on the record for that day; nothing "
                        "was added. Tell the patient it was already there."}

    row = model(user_id=user_id, **{spec.date_field: when}, **values)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    await db.commit()

    logger.info("ai wrote %s %s for user %s", spec.model, row.id, user_id)
    return {"logged": True, "id": row.id, "date": str(when), "what": label,
            "recorded": {k: str(v) for k, v in values.items()},
            "confirm_to_patient": confirm}


def _resolve_day(log_date_str: str | None, today: date | None) -> tuple[date | None, str | None]:
    """The PATIENT's day, never the server's (§3am).

    The containers run UTC, so `date.today()` is already tomorrow for a patient
    in the Americas from early evening — which once told someone with six
    logged meals that they had eaten nothing.
    """
    base = today or date.today()
    if not log_date_str:
        return base, None
    when = _parse_day(log_date_str, base)
    if when is None:
        return None, f"log_date_str={log_date_str!r} is not a date I can read"
    return when, None


# ── elimination ────────────────────────────────────────────────────────────

_ELIMINATION_SPECS = {
    "bowel": _WriteSpec(
        model="BowelMovement", date_field="log_date",
        text={"description": ("notes", 2000)},
        clocks={"time": "log_time"},
        scales={"bristol_scale": ("bristol_scale", 1, 7),
                "pain_level": ("pain_level", 0, 10)},
        identity=("log_time",),
    ),
    "vomiting": _WriteSpec(
        model="VomitingLog", date_field="log_date",
        text={"description": ("notes", 2000)},
        clocks={"time": "log_time"},
        identity=("log_time",),
    ),
}


async def log_elimination(
    db: AsyncSession, user_id: int, *,
    kind: str = "bowel",
    description: str | None = None,
    time: str | None = None,
    bristol_scale: Any = None,
    pain_level: Any = None,
    log_date_str: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Record a bowel movement or a vomiting episode the patient describes.

    ⚠️ **The patient's WORDS go in; no finding is derived from them here.**
    `blood_present` is not set even when the description says "bloody", and
    that is deliberate: `services/elimination_text.py` already reads those
    words for every consumer, and §3ba's rule is that a SET column wins while
    only NULL falls through to the text. Writing the boolean too would put a
    second interpreter beside the first, which §3ai forbids — two computations
    of one quantity must not disagree.
    """
    spec = _ELIMINATION_SPECS.get((kind or "bowel").strip().lower())
    if spec is None:
        return {"error": f"kind={kind!r} is not something this can record; "
                         f"use 'bowel' or 'vomiting'"}
    when, bad = _resolve_day(log_date_str, today)
    if bad:
        return {"error": bad}
    if not (description or "").strip() and time is None:
        return {"error": "nothing was described — nothing was logged"}

    return await _write_row(
        db, user_id, spec, when,
        {"description": description, "time": time,
         "bristol_scale": bristol_scale, "pain_level": pain_level},
        label=f"{kind} event",
        confirm=("Say exactly what was saved, with the date and time, so they "
                 "can correct it. Do not add detail they did not give."))


# ── mood ───────────────────────────────────────────────────────────────────

_MOOD_SPEC = _WriteSpec(
    model="MoodEntry", date_field="entry_date",
    text={"note": ("journal_entry", 4000), "triggers": ("triggers", 2000)},
    scales={"mood_score": ("mood_score", 1, 10),
            "energy_level": ("energy_level", 1, 10),
            "stress_level": ("stress_level", 1, 10),
            "anxiety_level": ("anxiety_level", 1, 10)},
)


async def log_mood(
    db: AsyncSession, user_id: int, *,
    mood_score: Any = None,
    energy_level: Any = None,
    stress_level: Any = None,
    anxiety_level: Any = None,
    note: str | None = None,
    triggers: str | None = None,
    log_date_str: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Record how the patient says they feel.

    `mood_score` is NOT NULL on the model, so a number is required — and it is
    required FROM THE PATIENT. Inferring "they sound low, call it 3" would be
    the assistant entering a clinical score nobody gave, which §3am's
    "inference proposes; it never writes" forbids on a far less subjective
    field than this one.
    """
    when, bad = _resolve_day(log_date_str, today)
    if bad:
        return {"error": bad}
    if mood_score is None:
        return {"error": "no mood score given — nothing was logged",
                "ask_the_patient":
                    "How would they rate their mood from 1 to 10? Do not pick "
                    "a number for them."}

    return await _write_row(
        db, user_id, _MOOD_SPEC, when,
        {"mood_score": mood_score, "energy_level": energy_level,
         "stress_level": stress_level, "anxiety_level": anxiety_level,
         "note": note, "triggers": triggers},
        label="mood entry",
        confirm="Repeat the score and anything else saved, so they can correct it.")


# ── sleep ──────────────────────────────────────────────────────────────────

_SLEEP_SPEC = _WriteSpec(
    model="SleepLog", date_field="sleep_date",
    text={"note": ("notes", 2000)},
    clocks={"bedtime": "bedtime", "wake_time": "wake_time"},
    scales={"quality_score": ("quality_score", 1, 10),
            "times_awakened": ("times_awakened", 0, 50)},
    # 24 is the ceiling a day can hold; anything above it is a transcription
    # error, not a long night.
    numbers={"total_hours": ("total_hours", 0.0, 24.0)},
)


async def log_sleep(
    db: AsyncSession, user_id: int, *,
    total_hours: Any = None,
    quality_score: Any = None,
    bedtime: str | None = None,
    wake_time: str | None = None,
    times_awakened: Any = None,
    note: str | None = None,
    log_date_str: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Record a night's sleep.

    ⚠️ **`total_hours` is not computed from bedtime and wake time here.** A
    night crossing midnight is exactly the §3av case where every client rolled
    over for DISPLAY and none for STORAGE, and four production dialysis
    sessions stored a negative duration as a result. The patient's own figure
    is recorded when they give one; the two clocks are recorded as given; and
    nothing derives one from the other in this module.
    """
    when, bad = _resolve_day(log_date_str, today)
    if bad:
        return {"error": bad}
    if total_hours is None and bedtime is None and wake_time is None:
        return {"error": "no sleep detail given — nothing was logged"}

    return await _write_row(
        db, user_id, _SLEEP_SPEC, when,
        {"total_hours": total_hours, "quality_score": quality_score,
         "bedtime": bedtime, "wake_time": wake_time,
         "times_awakened": times_awakened, "note": note},
        label="sleep record",
        confirm="Repeat what was saved for that night so they can correct it.")


# ── symptoms ───────────────────────────────────────────────────────────────

_SYMPTOM_SPEC = _WriteSpec(
    model="SymptomLog", date_field="log_date",
    text={"symptom": ("symptom_name", 255), "body_part": ("body_part", 100),
          "note": ("notes", 4000)},
    scales={"severity": ("severity", 1, 10)},
    numbers={"duration_hours": ("duration_hours", 0.0, 8760.0)},
    identity=("symptom_name",),
)


async def log_symptom(
    db: AsyncSession, user_id: int, *,
    symptom: str | None = None,
    severity: Any = None,
    body_part: str | None = None,
    duration_hours: Any = None,
    note: str | None = None,
    log_date_str: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Record a symptom the patient reports.

    §3am already records symptoms described to `/personalization/analyze-symptoms`
    — *"dizzy, weak" informed one answer and left no trace* — and this is the
    same fact arriving through the chat. The symptom is stored WHOLE as the
    patient said it: that section's own lesson is that splitting on a
    vocabulary of symptom words invented two symptoms from one sentence.
    """
    when, bad = _resolve_day(log_date_str, today)
    if bad:
        return {"error": bad}
    name = (symptom or "").strip()
    if not name:
        return {"error": "no symptom named — nothing was logged"}

    return await _write_row(
        db, user_id, _SYMPTOM_SPEC, when,
        {"symptom": name, "severity": severity, "body_part": body_part,
         "duration_hours": duration_hours, "note": note},
        label=f"symptom: {name}",
        confirm=("Repeat the symptom and severity saved. If it sounds urgent, "
                 "say so plainly and tell them to contact their care team — "
                 "recording it is not treating it."))


# ── fitness ────────────────────────────────────────────────────────────────

_FITNESS_SPEC = _WriteSpec(
    model="FitnessLog", date_field="log_date",
    text={"activity": ("activity_type", 100), "note": ("notes", 2000),
          "intensity": ("intensity", 20)},
    scales={"duration_minutes": ("duration_minutes", 0, 1440),
            "steps": ("steps", 0, 200000)},
    numbers={"distance_km": ("distance_km", 0.0, 1000.0)},
    identity=("activity_type",),
)


async def log_fitness(
    db: AsyncSession, user_id: int, *,
    activity: str | None = None,
    duration_minutes: Any = None,
    distance_km: Any = None,
    steps: Any = None,
    intensity: str | None = None,
    note: str | None = None,
    log_date_str: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Record activity the patient reports.

    No calories are derived. `calories_burned` is a column this tool does not
    name, because computing it needs weight, heart rate and a formula nobody
    here has cited — and §3az's rule is that a figure with no authority must
    not be presented as the patient's own.
    """
    when, bad = _resolve_day(log_date_str, today)
    if bad:
        return {"error": bad}
    name = (activity or "").strip()
    if not name:
        return {"error": "no activity named — nothing was logged"}

    return await _write_row(
        db, user_id, _FITNESS_SPEC, when,
        {"activity": name, "duration_minutes": duration_minutes,
         "distance_km": distance_km, "steps": steps,
         "intensity": intensity, "note": note},
        label=f"activity: {name}",
        confirm="Repeat what was saved so they can correct it.")


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_surgical_history",
        "description": "Hospital admissions and surgical operations, plus "
                       "what past surgery STILL does to the patient today. "
                       "Call this for any question about an operation, a "
                       "hospital stay, or a requirement it left behind — "
                       "removed organs or glands change what a patient needs "
                       "for the rest of their life, and a nutrient or "
                       "medication question can be unanswerable without it.",
        "input_schema": {"type": "object", "properties": {}},
    },
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
    {
        "name": "get_sleep",
        "description": "Nights of sleep on record — hours, quality, bedtime "
                       "and wake time, how often they woke. Use this for ANY "
                       "question about how the patient slept.",
        "input_schema": {
            "type": "object",
            "properties": {"start_date": {"type": "string", "description": "YYYY-MM-DD. Omit both dates for a sensible recent window."}, "end_date": {"type": "string", "description": "YYYY-MM-DD. Omit both dates for a sensible recent window."}},
            "required": [],
        },
    },
    {
        "name": "get_mood",
        "description": "Mood entries on record — the score the patient gave, "
                       "energy, stress and anxiety, and what they wrote.",
        "input_schema": {
            "type": "object",
            "properties": {"start_date": {"type": "string", "description": "YYYY-MM-DD. Omit both dates for a sensible recent window."}, "end_date": {"type": "string", "description": "YYYY-MM-DD. Omit both dates for a sensible recent window."}},
            "required": [],
        },
    },
    {
        "name": "get_symptoms",
        "description": "Symptoms the patient has reported — what, where, how "
                       "severe, how long, and what they said about it. Use "
                       "this before answering anything about how they have "
                       "been feeling.",
        "input_schema": {
            "type": "object",
            "properties": {"start_date": {"type": "string", "description": "YYYY-MM-DD. Omit both dates for a sensible recent window."}, "end_date": {"type": "string", "description": "YYYY-MM-DD. Omit both dates for a sensible recent window."}},
            "required": [],
        },
    },
    {
        "name": "get_fitness",
        "description": "Activity on record — what they did, for how long, how "
                       "far, and how hard.",
        "input_schema": {
            "type": "object",
            "properties": {"start_date": {"type": "string", "description": "YYYY-MM-DD. Omit both dates for a sensible recent window."}, "end_date": {"type": "string", "description": "YYYY-MM-DD. Omit both dates for a sensible recent window."}},
            "required": [],
        },
    },
    {
        "name": "log_meal",
        "description": "RECORD a meal in the patient's diary. Use this whenever "
                       "they ask you to log, add, save or record something they "
                       "ate or drank — do NOT tell them to go and enter it "
                       "themselves. Save ONLY the foods they actually named; "
                       "never add, guess or complete a meal. Nutrients are "
                       "estimated automatically afterwards, so do not pass any.",
        "input_schema": {
            "type": "object",
            "properties": {
                "food_name": {"type": "string", "description":
                    "The items, as the patient described them, comma separated — "
                    "e.g. '1 slice brioche bread, 2 boiled eggs, 4 green olives'. "
                    "Their words and their quantities, not a tidied version."},
                "meal_type": {"type": "string", "description":
                    "breakfast | lunch | dinner | snack"},
                "log_date_str": {"type": "string", "description":
                    "YYYY-MM-DD, or 'today' / 'yesterday'. OMIT for today."},
                "start_time": {"type": "string", "description": "e.g. '8:45 pm'"},
                "end_time": {"type": "string", "description": "e.g. '9:30 pm'"},
            },
            "required": ["food_name"],
        },
    },
    {
        "name": "log_medication",
        "description": "RECORD medication the patient says they took. Use it "
                       "whenever they report taking something — 'I took my "
                       "calcitriol', 'I took regular dosages of X and Y'. Do "
                       "NOT tell them to open the Medications screen. You do "
                       "not need the dose: 'regular' or 'usual' is resolved "
                       "from their own logging history. Anything that cannot "
                       "be resolved, or that the dose guard objects to, comes "
                       "back under `needs_input` — ask about those, and never "
                       "invent a dose.",
        "input_schema": {
            "type": "object",
            "properties": {
                "medications": {
                    "type": "array", "items": {"type": "string"},
                    "description":
                        "One entry per medication: the DRUG NAME as the patient "
                        "named it, plus a dose ONLY if they stated a specific "
                        "one. 'I took regular dosages of calcitriol and calcium "
                        "carbonate' is ['calcitriol', 'calcium carbonate'] — "
                        "words like regular, usual or my normal are not doses, "
                        "so leave the dose out and the patient's own history "
                        "supplies it. '2 tablets of calcium carbonate' keeps "
                        "the dose. Do not correct or expand the drug name.",
                },
                "log_date_str": {"type": "string", "description":
                    "YYYY-MM-DD, or 'today' / 'yesterday'. OMIT for today."},
                "taken_at": {"type": "string", "description": "e.g. '8:45 am'"},
            },
            "required": ["medications"],
        },
    },
    {
        "name": "log_elimination",
        "description": "RECORD a bowel movement or a vomiting episode the "
                       "patient reports — 'I had a bowel movement at 3', 'I "
                       "threw up this morning'. Do NOT tell them to open the "
                       "Elimination screen. Pass their description in THEIR "
                       "words; do not decide whether there was blood or what "
                       "it means, the record reads the words itself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["bowel", "vomiting"],
                         "description": "Which event. Defaults to bowel."},
                "description": {"type": "string", "description":
                    "What the patient said about it, in their own words."},
                "time": {"type": "string", "description": "e.g. '3 pm', '15:00'"},
                "bristol_scale": {"type": "integer", "description":
                    "1-7, ONLY if the patient gave a Bristol number."},
                "pain_level": {"type": "integer", "description":
                    "0-10, ONLY if the patient gave a number."},
                "log_date_str": {"type": "string", "description":
                    "YYYY-MM-DD, or 'today' / 'yesterday'. OMIT for today."},
            },
            "required": [],
        },
    },
    {
        "name": "log_mood",
        "description": "RECORD how the patient says they feel. Needs a mood "
                       "score from 1 to 10 THAT THEY GAVE — if they have not "
                       "given one, ask; never choose a number for them. Use "
                       "this whenever they report their mood, energy, stress "
                       "or anxiety rather than telling them to open a screen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mood_score": {"type": "integer", "description":
                    "1-10, AS THE PATIENT STATED IT. Required."},
                "energy_level": {"type": "integer", "description": "1-10, if stated"},
                "stress_level": {"type": "integer", "description": "1-10, if stated"},
                "anxiety_level": {"type": "integer", "description": "1-10, if stated"},
                "note": {"type": "string", "description":
                    "What they said about it, in their own words."},
                "triggers": {"type": "string", "description":
                    "What they said brought it on, in their words."},
                "log_date_str": {"type": "string", "description":
                    "YYYY-MM-DD, or 'today' / 'yesterday'. OMIT for today."},
            },
            "required": ["mood_score"],
        },
    },
    {
        "name": "log_sleep",
        "description": "RECORD a night's sleep the patient reports — 'I slept "
                       "about five hours', 'I was awake four times'. Record "
                       "what they said; do NOT work out hours from bedtime "
                       "and wake time yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "total_hours": {"type": "number", "description":
                    "Hours slept, if the patient said how many."},
                "quality_score": {"type": "integer", "description": "1-10, if stated"},
                "bedtime": {"type": "string", "description": "e.g. '11 pm'"},
                "wake_time": {"type": "string", "description": "e.g. '6:30 am'"},
                "times_awakened": {"type": "integer", "description": "if stated"},
                "note": {"type": "string", "description": "Their own words."},
                "log_date_str": {"type": "string", "description":
                    "YYYY-MM-DD, or 'today' / 'yesterday'. OMIT for today."},
            },
            "required": [],
        },
    },
    {
        "name": "log_symptom",
        "description": "RECORD a symptom the patient reports — 'I have been "
                       "dizzy since this morning', 'my left arm aches'. Use it "
                       "whenever they describe something they are feeling. "
                       "Keep the symptom in THEIR words and do not split one "
                       "sentence into several symptoms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom": {"type": "string", "description":
                    "The symptom as the patient named it."},
                "severity": {"type": "integer", "description":
                    "1-10, ONLY if the patient gave a number."},
                "body_part": {"type": "string", "description": "if they said where"},
                "duration_hours": {"type": "number", "description":
                    "How long, in hours, if they said."},
                "note": {"type": "string", "description": "Their own words."},
                "log_date_str": {"type": "string", "description":
                    "YYYY-MM-DD, or 'today' / 'yesterday'. OMIT for today."},
            },
            "required": ["symptom"],
        },
    },
    {
        "name": "log_fitness",
        "description": "RECORD activity the patient reports — 'I walked for "
                       "twenty minutes', 'I did my exercises'. Do not estimate "
                       "calories; the record does not want a figure nobody "
                       "measured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "activity": {"type": "string", "description":
                    "What they did, in their words — walking, cycling, yoga."},
                "duration_minutes": {"type": "integer", "description": "if stated"},
                "distance_km": {"type": "number", "description": "if stated"},
                "steps": {"type": "integer", "description": "if stated"},
                "intensity": {"type": "string", "description":
                    "low / moderate / high, if they said"},
                "note": {"type": "string", "description": "Their own words."},
                "log_date_str": {"type": "string", "description":
                    "YYYY-MM-DD, or 'today' / 'yesterday'. OMIT for today."},
            },
            "required": ["activity"],
        },
    },
]
# ── Writing ────────────────────────────────────────────────────────────
#
# Reading was all this module did, so "log this meal" got "I don't have the
# ability to log meals into your record" followed by a tidy list of what the
# patient should go and type themselves. That is a correct statement about the
# tools and a useless answer to the request: the assistant had the meal, the
# times, and the patient's explicit instruction, and handed the work back.
#
# Writes are deliberately narrower than reads. A meal is patient-authored, easy
# to see in the diary and easy to delete. Medications, vitals and labs are NOT
# writable here: §3aj's guard exists because a dose is a clinical statement, and
# "inference proposes, it never writes" still holds for anything the patient did
# not spell out in the message.


async def log_meal(
    db: AsyncSession, user_id: int, *,
    food_name: str,
    meal_type: str = "snack",
    log_date_str: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Record a meal the patient has asked to log.

    Saves immediately and estimates nutrients afterwards — the same shape as the
    Nutrition screen (§3c), because a 10-item meal's lookup takes longer than
    anyone will wait and a failed lookup must never cost the patient the meal
    they typed.

    ONLY records what the patient stated. The tool cannot check that, so the
    loop instructions carry the rule and the result echoes back exactly what was
    written for the answer to repeat.
    """
    from app.models.nutrition import NutritionLog

    name = (food_name or "").strip()
    if not name:
        return {"error": "no food described — nothing was logged"}

    when = _parse_day(log_date_str, today or date.today()) if log_date_str else (today or date.today())
    if when is None:
        return {"error": f"log_date_str={log_date_str!r} is not a date I can read"}

    meal = (meal_type or "snack").strip().lower()
    if meal not in ("breakfast", "lunch", "dinner", "snack"):
        meal = "snack"

    # Idempotency. A tool loop can repeat a call — a provider retry, a second
    # round that re-reads the request — and a duplicated meal double-counts
    # every nutrient for that day.
    existing = (await db.execute(
        select(NutritionLog).where(
            NutritionLog.user_id == user_id,
            NutritionLog.log_date == when,
            NutritionLog.meal_type == meal,
            NutritionLog.food_name == name,
        ).limit(1)
    )).scalars().first()
    if existing is not None:
        return {"already_logged": True, "id": existing.id, "date": str(when),
                "meal": meal, "food": name,
                "note": "This exact meal is already on the record for that day; "
                        "nothing was added. Tell the patient it was already there."}

    log = NutritionLog(
        user_id=user_id, log_date=when, meal_type=meal, food_name=name,
        start_time=_parse_clock(start_time), end_time=_parse_clock(end_time),
        nutrient_status="pending",
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    await db.commit()

    # Enrichment runs after the write, with its own session, exactly as the API
    # does. Fire-and-forget: the patient gets the confirmation now and the
    # nutrients land within seconds.
    try:
        from app.services.nutrient_enrichment import enrich_log
        import asyncio

        asyncio.ensure_future(enrich_log(log.id, notify=True))
    except Exception:  # noqa: BLE001 — a failed queue must not undo the save
        logger.warning("could not queue enrichment for log %s", log.id, exc_info=True)

    logger.info("ai logged meal %s for user %s: %r", log.id, user_id, name[:60])
    return {
        "logged": True,
        "id": log.id,
        "date": str(when),
        "meal": meal,
        "food": name,
        "start_time": str(log.start_time) if log.start_time else None,
        "end_time": str(log.end_time) if log.end_time else None,
        "nutrients": "being estimated now — they appear in the diary shortly",
        "confirm_to_patient": (
            "Say exactly what was saved, including the date and the items, so "
            "they can correct it. Do not add foods they did not mention."),
    }


def _parse_clock(value: str | None):
    """"8:45 pm" / "20:45" → a time, or None. Never raises."""
    if not value:
        return None
    from datetime import time as _time

    text = str(value).strip().lower().replace(".", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    suffix = m.group(3)
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return _time(hour, minute)


async def log_medication(
    db: AsyncSession, user_id: int, *,
    medications: list[str] | str,
    log_date_str: str | None = None,
    taken_at: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Record medication the patient says they took.

    "I took regular dosages of calcitriol and calcium carbonate" used to reach a
    blank form. The dose is not stated there, and the patient should not have to
    restate what they take every day — "regular" means what their own logs say
    it is.

    NOTHING IS PARSED OR GUESSED HERE. The work is done by the pieces that
    already exist and are already tested:

      `propose_intake`  reads the phrase, supplies a missing dose from THIS
                        patient's own dose-log history (or their prescription),
                        and reports where the figure came from.
      `validate_dose`   the RxNorm guard from §3aj — the one that caught
                        "calcium calcitriol 1000 mg", a ~1000x overdose on a
                        drug measured in micrograms.

    A dose is a clinical statement, so this writes ONLY when the record can
    supply the figure and the guard is satisfied. Where the dose is unknown, or
    the guard objects, it writes nothing and hands back what it found — the
    model then asks, which is §3aj's "inference proposes; it never writes" kept
    intact rather than argued away.
    """
    from app.models.med_nutrient import MedicationDoseLog
    from app.services.med_dose_validation import blocking, validate_dose
    from app.services.med_intake_intent import propose_intake

    phrases = [medications] if isinstance(medications, str) else list(medications or [])
    phrases = [p.strip() for p in phrases if p and p.strip()]
    if not phrases:
        return {"error": "no medication named — nothing was logged"}

    when = _parse_day(log_date_str, today or date.today()) if log_date_str else (today or date.today())
    if when is None:
        return {"error": f"log_date_str={log_date_str!r} is not a date I can read"}
    clock = _parse_clock(taken_at)

    logged: list[dict[str, Any]] = []
    needs_input: list[dict[str, Any]] = []

    for phrase in phrases:
        proposal = await propose_intake(db, user_id, phrase)
        name = (proposal.medication_name or "").strip()
        if not name:
            needs_input.append({"asked_about": phrase, "reason": "could not tell which medication"})
            continue

        if proposal.dose_amount is None or proposal.dose_source == "unknown":
            # No figure in the text, none in their history, none prescribed.
            # Inventing one is exactly what §3aj forbids.
            needs_input.append({
                "medication": name,
                "reason": "no dose stated and none in your history to use",
                "alternatives": proposal.alternatives,
            })
            continue

        findings = blocking(await validate_dose(
            db, name, proposal.dose_amount, proposal.dose_unit or ""))
        if findings:
            needs_input.append({
                "medication": name,
                "reason": "the dose guard objected",
                "findings": [f.as_dict() for f in findings],
            })
            continue

        # Idempotency: a repeated tool call must not double a dose.
        existing = (await db.execute(
            select(MedicationDoseLog).where(
                MedicationDoseLog.user_id == user_id,
                MedicationDoseLog.log_date == when,
                MedicationDoseLog.medication_name == name,
                MedicationDoseLog.dose_amount == proposal.dose_amount,
            ).limit(1)
        )).scalars().first()
        if existing is not None:
            logged.append({"medication": name, "already_logged": True, "id": existing.id,
                           "dose": f"{proposal.dose_amount} {proposal.dose_unit or ''}".strip()})
            continue

        row = MedicationDoseLog(
            user_id=user_id, log_date=when, medication_name=name,
            dose_amount=proposal.dose_amount, dose_unit=proposal.dose_unit or "",
            log_time=clock,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        logged.append({
            "medication": name,
            "id": row.id,
            "dose": f"{proposal.dose_amount} {proposal.dose_unit or ''}".strip(),
            # Where the figure came from, so the answer can say it. A dose the
            # patient never spoke aloud must never look like one they did.
            "dose_source": proposal.dose_source,
            "provenance": proposal.provenance,
        })

    if logged:
        await db.commit()
        logger.info("ai logged %d dose(s) for user %s", len(logged), user_id)

    out: dict[str, Any] = {"date": str(when), "logged": logged}
    if needs_input:
        out["needs_input"] = needs_input
        out["ask_the_patient"] = (
            "Say what was recorded, then ask for the missing dose in one short "
            "question. Do not invent a figure and do not log these.")
    if logged:
        out["confirm_to_patient"] = (
            "State each medication, its dose, and WHERE the dose came from "
            "(their own logs, their prescription, or what they just said), so "
            "they can correct it.")
    return out


#: What to SHOW the patient while each tool runs. The backend owns this text
#: rather than each client, so web, iOS and Android cannot drift apart and a new
#: tool does not need three app releases to get a label.
#:
#: Deliberately NOT a key inside `TOOL_SPECS`: the Anthropic adapter sends those
#: dicts to the provider verbatim, so an extra field there reaches the API as an
#: unknown key. `tests/test_ai_tool_use.py` pins both halves — every tool has a
#: label, and no spec carries a field the wire does not expect.
TOOL_LABELS = {
    "get_surgical_history": "Checking your surgical history",
    "get_meals": "Checking your meals",
    "get_eliminations": "Checking your symptom log",
    "get_medications": "Checking your medications",
    "get_vitals": "Checking your vitals",
    "get_labs": "Checking your lab results",
    "get_sleep": "Checking your sleep",
    "get_mood": "Checking how you have been feeling",
    "get_symptoms": "Checking your symptoms",
    "get_fitness": "Checking your activity",
    "log_meal": "Saving your meal",
    "log_medication": "Recording your medication",
    "log_elimination": "Recording that in your elimination log",
    "log_mood": "Saving how you are feeling",
    "log_sleep": "Saving your sleep",
    "log_symptom": "Recording your symptom",
    "log_fitness": "Saving your activity",
}

#: Tools that CHANGE the record. Declared, not inferred from a description —
#: a keyword test on prose matched `get_meals` because its text mentions "the
#: record". Anything added here is a tool that can write to a patient's chart,
#: which is a decision worth making explicitly.
#:
#: ⚠️ **Until 2026-10-14 this set had NO READER.** It was declared here, tested
#: by one assertion, and consulted by nothing: `run_tool` dispatched `log_meal`
#: for any caller that named it. A set whose whole purpose is to mark which
#: calls can alter a patient's chart, enforcing nothing, is §3ay's
#: never-plugged-in sink on the most consequential switch in the module — and
#: §3ar's dead control, which is worst exactly where it looks most like a
#: safeguard. `run_tool` now refuses these unless the CALLER asks for writes.
WRITE_TOOLS = frozenset({
    "log_meal", "log_medication",
    "log_elimination", "log_mood", "log_sleep", "log_symptom", "log_fitness",
})

#: Deliberately NOT writable, with the reason, so the next person adding a tool
#: does not have to re-derive the decision (§3am):
#:
#:   vitals  a reading comes off a device the patient read. Writing it here
#:           makes the assistant a measurement source, and a transcription
#:           error becomes a clinical observation nobody can trace to a cuff.
#:   labs    a result comes from a laboratory, through the document import or
#:           an EHR feed, and carries a reference range and a provenance this
#:           path cannot supply (§3ab, §3ax).
#:
#: Both remain readable. The asymmetry is the point.
NEVER_WRITABLE = frozenset({"vitals", "labs"})

TOOLS = {
    "get_surgical_history": get_surgical_history,
    "get_meals": get_meals,
    "get_eliminations": get_eliminations,
    "get_medications": get_medications,
    "get_vitals": get_vitals,
    "get_labs": get_labs,
    "get_sleep": get_sleep,
    "get_mood": get_mood,
    "get_symptoms": get_symptoms,
    "get_fitness": get_fitness,
    "log_meal": log_meal,
    "log_medication": log_medication,
    "log_elimination": log_elimination,
    "log_mood": log_mood,
    "log_sleep": log_sleep,
    "log_symptom": log_symptom,
    "log_fitness": log_fitness,
}


async def run_tool(db: AsyncSession, user_id: int, name: str,
                   arguments: dict[str, Any],
                   today: date | None = None, *,
                   allow_writes: bool = False) -> dict[str, Any]:
    """Execute one tool call. Errors are returned, never raised.

    A tool that raises would abort the whole answer; a tool that reports its
    failure lets the model say what it could not check.

    **THE WRITE GATE, and it FAILS CLOSED.** `allow_writes` defaults to False,
    so a caller gets a read-only assistant unless it says otherwise. Every
    consumer of this module — a summariser, a scheduled job, a future report
    builder — therefore cannot alter a chart by accident; it has to ask.

    That default is the whole point. `WRITE_TOOLS` existed for weeks with no
    reader, which meant any caller naming `log_meal` wrote a clinical row
    (§3ar). A gate that must be opted INTO cannot be forgotten into the open
    position — the §3at lesson about which way a default fails, applied to a
    capability rather than a checkbox.
    """
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"no such tool: {name}"}
    if name in WRITE_TOOLS and not allow_writes:
        # Reported, never raised, and SAID OUT LOUD: the model must be able to
        # tell the patient their request was refused rather than silently
        # answering as though it had been done (§3aa — and §3am's rule that an
        # error must never become an answer).
        logger.warning("refused write tool %s for user %s: writes not enabled "
                       "for this caller", name, user_id)
        return {"error": f"{name} cannot write from here",
                "refused": True,
                "tell_the_patient":
                    "Saving to the record is not available in this "
                    "conversation. Nothing was written. They can log it on the "
                    "matching screen."}
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
