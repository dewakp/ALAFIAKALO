# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The record answers back: new data is judged the moment it is written.

Every mechanism needed for this already existed and almost none of it fired.
Measured on production 2026-10-02, before this module:

    notifications                21 rows, 4 users, 19 of them unread
      nutrition_alert             8 rows, ONE user, every one on 2026-06-26
      system                      8 rows
      record_access               3 rows
      lab_anomaly                 2 rows, one day
    10 of the 14 categories had NEVER fired, `treatment_anomaly` included

Against, on the same database: 1,056 nutrition logs, 1,022 medication dose
logs, 9,791 lab results. Eleven `notify_*` producers exist and are wired into
eight routers. The engine was not missing. What was missing is that nothing
compared a new row to what the record already knew about the patient.

WHY THE NUTRITION ALERT FIRED ON ONE DAY IN JUNE AND NEVER AGAIN
===============================================================
Two independent faults, each sufficient on its own:

1. **It read the row before the numbers existed.** §3c: a meal is persisted and
   returned immediately, and nutrients are filled in afterwards by a background
   task. The check sat inline in the endpoint, so for any meal needing
   estimation every value it read was None — and `nutrient_enrichment.py`, which
   later writes the real figures, contained no notification call at all. The
   measurement that proves it: `nutrient_status='pending'` is 0 and `sugar_g` is
   populated on 1,031 of 1,056 rows. The values arrive. Nobody is told.

2. **The thresholds were population constants, and looser than this patient's
   own limits.** The dict, hand-typed and duplicated at both call sites:

       sodium 2300 / potassium 4700 / phosphorus 1000 / sugar 50

   `nutrient_goals_service.compute_goals` already computes a limit per patient.
   For the reference record — Diabetes, ESRD, Chronic Anaemia, 55 kg — it says
   potassium **2200 mg** (40 mg/kg, floored at 2000) where the dict said 4700,
   and sugar at 5% of energy where the dict said 50 g. 4,700 mg is the generic
   adult RDA that §3am names as precisely the wrong figure to hand a renal
   patient. So the alert could only fire at an intake roughly twice the one that
   actually endangers them: the patient the user's own example names — a
   diabetic exceeding a sugar quota — was the patient it could not warn.

`tests/test_renal_limits_are_personal.py` already made this argument about the
clinician board, and `tests/test_no_hardcoded_thresholds.py` states the canon
outright: *no hardcoded data, no exception*. Neither reached these two dicts.

WHAT THIS MODULE WILL NOT DO
============================
**It never notifies retroactively.** Operator instruction, 2026-10-02: *"do not
notify retroactively. Notify from when this update lands onward."* That is
honoured structurally rather than by configuration — every entry point here
takes a row that the calling request has just written, and nothing in this file
queries history for rows to judge. There is no sweep, no catch-up job and no
cutoff timestamp, so there is no switch to leave in the wrong position and no
constant to go stale on redeploy. A notification about a 2018 meal cannot be
produced because no code path can reach one.

**It invents no clinical number.** Every threshold is resolved from an authority
that already exists for this patient, and where none exists the observation
passes in silence. That is the ordering `reference_ranges` and
`clinical_thresholds` were built for: the patient's own reported range, then the
population's, then a recorded guideline, then *nothing* — never a constant.

**It never breaks a clinical save.** Every entry point is best-effort and
swallows its own failure, for the reason §3ah gives: the row is the record, and
losing an alert is incomparably better than losing the meal the patient typed.

**It does not shout twice.** `notify_record_accessed` already learned this — a
board load fans out across several routes and without a window the patient gets
five alerts for one visit and learns to ignore all five. A daily nutrient quota
is the same shape: cross the sugar limit at lunch and every later meal that day
re-crosses it. One finding is one notification, keyed and deduplicated.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notification_engine import create_notification
from app.models.notifications import (
    Notification,
    NotificationCategory,
    NotificationPriority,
)

logger = logging.getLogger(__name__)

#: How far back to look for an identical finding before writing another. The
#: keys below all carry a date, so this only ever suppresses a genuine repeat;
#: it is generous because the cost of a duplicate alert is a patient who stops
#: reading them, and the cost of looking is a few rows (21 on all of production).
DEDUPE_LOOKBACK_DAYS = 8


@dataclass(frozen=True)
class Finding:
    """One thing worth telling the patient, with where the judgement came from.

    `authority` is not decoration. A figure shown to a patient has to be
    traceable to the thing that set it — their own lab, their own computed
    limit, their own declared allergy — or the next person cannot review it and
    §3aj's "a guard that cannot explain itself gets blamed for the thing it did
    not do" applies.
    """

    category: NotificationCategory
    priority: NotificationPriority
    title: str
    message: str
    dedupe_key: str
    action_url: str | None = None
    authority: str = ""
    extra: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        out = {"dedupe_key": self.dedupe_key, "authority": self.authority}
        if self.extra:
            out.update(self.extra)
        return out


# ── Emission ──────────────────────────────────────────────────────────────


async def _already_sent(db: AsyncSession, user_id: int, finding: Finding) -> bool:
    """Has this exact finding already been written recently?

    The key is compared after parsing, not with a LIKE against the JSON text: a
    substring match on serialised JSON is the kind of thing that works until a
    key is a prefix of another one.
    """
    since = datetime.now(timezone.utc) - timedelta(days=DEDUPE_LOOKBACK_DAYS)
    rows = (await db.execute(
        select(Notification.extra_data).where(
            Notification.user_id == user_id,
            Notification.category == finding.category,
            Notification.created_at >= since,
        )
    )).scalars().all()
    for raw in rows:
        if not raw:
            continue
        try:
            if json.loads(raw).get("dedupe_key") == finding.dedupe_key:
                return True
        except (ValueError, TypeError):
            continue
    return False


async def emit(db: AsyncSession, user_id: int, findings: Iterable[Finding]) -> int:
    """Write each finding once. Returns how many notifications were created."""
    written = 0
    for f in findings:
        try:
            if await _already_sent(db, user_id, f):
                continue
            note = await create_notification(
                db,
                user_id=user_id,
                category=f.category,
                priority=f.priority,
                title=f.title,
                message=f.message,
                action_url=f.action_url,
                metadata_dict=f.payload(),
            )
            # `create_notification` returns None when the user has switched the
            # category off. That is a real answer, not a failure — but it is
            # silent, so it is logged rather than counted (§3aa: an error is not
            # an empty state, and neither is a preference).
            if note is None:
                logger.info("active_response: %s suppressed by preference for user %s",
                            f.category.value, user_id)
                continue
            written += 1
        except Exception:
            logger.exception("active_response: could not write finding %r", f.dedupe_key)
    return written


# ── What the patient's own record says the limits are ─────────────────────


async def _personal_nutrient_limits(db: AsyncSession, user: Any) -> list[dict]:
    """This patient's CAPPED nutrients, from `compute_goals`.

    Only `kind == "limit"` goals. A shortfall against a target is a different
    conversation with a different tone, and mixing the two into one alert
    channel is how a feed becomes noise — §3am measured that cost: 63% of a
    folate target was reported as "Excellent" to an anaemic patient because
    nobody had agreed the wording.
    """
    from app.services import clinical_sources as sources
    from app.services.food_safety import profile_list
    from app.services.nutrient_goals_service import compute_goals

    conditions = list(await sources.conditions(db, user.id, active_only=True))
    payload = compute_goals(
        date_of_birth=str(user.date_of_birth) if user.date_of_birth else None,
        sex=getattr(user, "gender_at_birth", None) or getattr(user, "gender", None),
        height_cm=user.height_cm,
        current_weight_kg=user.current_weight_kg,
        target_weight_kg=getattr(user, "target_weight_kg", None),
        activity_level=getattr(user, "activity_level", None),
        conditions=conditions,
        fitness_goals=profile_list(getattr(user, "fitness_goals", None)),
        dietary_preferences=profile_list(getattr(user, "dietary_preferences", None)),
        dietary_restrictions=profile_list(getattr(user, "dietary_restrictions", None)),
        allergies=profile_list(getattr(user, "allergies", None)),
    )
    return [g for g in (payload.get("goals") or []) if g.get("kind") == "limit"]


async def _guidance_for(db: AsyncSession, user: Any) -> Any:
    """Everything this patient must not be offered, and why.

    `resolve_missing=False` is load-bearing: `facts_for_conditions` will
    otherwise ask a model to resolve a condition it has not seen, and this runs
    on a write path. §3ae's whole lesson is about an LLM call sitting where a
    request waits — `get_goal_progress` makes the same choice for the same
    reason and says so ("STORED effects only, never a resolution").
    """
    from app.services import allergy_resolution
    from app.services import condition_nutrition_service as cns
    from app.services import clinical_sources as sources
    from app.services import food_safety

    conditions = list(await sources.conditions(db, user.id, active_only=True))
    facts = await cns.facts_for_conditions(db, conditions, resolve_missing=False)
    capped = [(g.get("name") or g.get("key") or "")
              for g in await _personal_nutrient_limits(db, user)]
    # Stored spelling resolutions only — one indexed SELECT, no network. This
    # is what makes a profile reading `Penicilin` catch a dose logged as
    # `Penicillin`; asking RxNorm here would put a third-party round trip on a
    # clinical write path, which is §3ae's timeout failure by construction.
    aliases = await allergy_resolution.aliases_for_user(db, user)
    return food_safety.build_guidance(user, facts, nutrient_limits=capped,
                                      aliases=aliases)


# ── Food ──────────────────────────────────────────────────────────────────


async def evaluate_nutrition_log(db: AsyncSession, log: Any, user: Any) -> int:
    """Judge a meal that has just been written (or just been enriched).

    Two independent questions, because they fail independently:

    * does the DAY now exceed one of this patient's own limits, and
    * does this meal contain something they must not eat at all

    The day's total is the right unit for a quota — a limit is a daily figure,
    and a single meal under it says nothing — so the aggregate is read through
    `_aggregate_daily_nutrients`, the same function the Nutrition screen and
    the goal-progress endpoint use. §3ai: two computations of one quantity must
    not disagree, and a second aggregate maintained here would drift from the
    one the patient can see on their own screen.
    """
    findings: list[Finding] = []
    try:
        findings += await _nutrient_limit_findings(db, log, user)
    except Exception:
        logger.exception("active_response: nutrient limits failed for log %s",
                         getattr(log, "id", None))
    try:
        findings += await _restriction_findings(db, log, user)
    except Exception:
        logger.exception("active_response: restriction check failed for log %s",
                         getattr(log, "id", None))
    if not findings:
        return 0
    return await emit(db, user.id, findings)


async def _nutrient_limit_findings(db: AsyncSession, log: Any, user: Any) -> list[Finding]:
    from app.api.nutrition import _aggregate_daily_nutrients

    limits = await _personal_nutrient_limits(db, user)
    if not limits:
        return []

    totals, _, _ = await _aggregate_daily_nutrients(db, user.id, log.log_date)
    out: list[Finding] = []
    for goal in limits:
        key = str(goal.get("key") or "")
        cap = goal.get("goal")
        got = totals.get(key)
        if not key or cap is None or got is None or got <= cap:
            continue
        name = goal.get("name") or key
        unit = goal.get("unit") or ""
        over = got - cap
        rationale = (goal.get("rationale") or "").strip()
        out.append(Finding(
            category=NotificationCategory.NUTRITION_ALERT,
            priority=(NotificationPriority.HIGH if goal.get("priority", 99) <= 5
                      else NotificationPriority.MEDIUM),
            title=f"{name} above your daily limit",
            message=(
                f"Today's {name.lower()} is {got:.0f} {unit} against your limit of "
                f"{cap:.0f} {unit} — {over:.0f} {unit} over."
                + (f" {rationale}" if rationale else "")
            ),
            # One finding per nutrient per DAY. Without the date in the key a
            # correction tomorrow would be silently suppressed; without the
            # nutrient, sodium would mask potassium.
            dedupe_key=f"nutrient_limit:{key}:{log.log_date.isoformat()}",
            action_url="/nutrition",
            authority="compute_goals (this patient's own limit)",
            extra={"nutrient": key, "total": round(float(got), 1),
                   "limit": round(float(cap), 1), "unit": unit,
                   "date": log.log_date.isoformat()},
        ))
    return out


def _meal_text(log: Any) -> str:
    """Everything the patient wrote about this meal.

    The name alone is not enough — a serving description or a note is where
    "with peanut sauce" lives, and §3aw's warning applies in reverse: the
    matcher reads English food names, so it must at least be given every
    English word the patient supplied.
    """
    parts = [getattr(log, "food_name", None), getattr(log, "serving_size", None),
             getattr(log, "notes", None)]
    return " ".join(str(p) for p in parts if p)


async def _restriction_findings(db: AsyncSession, log: Any, user: Any) -> list[Finding]:
    from app.services import food_safety

    text = _meal_text(log)
    if not text:
        return []
    guidance = await _guidance_for(db, user)
    hits = food_safety.violations(text, guidance.avoid)
    out: list[Finding] = []
    for r in hits:
        # An allergy and a condition trigger are enforced alike and must be
        # EXPLAINED differently (§3an): one is immune-mediated and the patient
        # told us, the other is a consequence of a diagnosis we resolved.
        urgent = r.kind == food_safety.ALLERGY
        out.append(Finding(
            category=NotificationCategory.NUTRITION_ALERT,
            priority=(NotificationPriority.URGENT if urgent
                      else NotificationPriority.HIGH),
            title=(f"{r.label} is on your allergy list" if urgent
                   else f"{r.label} may not suit you"),
            message=(f"The meal you logged mentions {r.label}. {r.reason}."
                     + (f" {r.mechanism}." if r.mechanism else "")),
            dedupe_key=f"restriction:{r.term}:nutrition:{log.id}",
            action_url=f"/nutrition/{log.id}",
            authority=f"{r.kind}: {r.label}",
            extra={"term": r.term, "kind": r.kind, "log_id": log.id},
        ))
    return out


# ── Medication ────────────────────────────────────────────────────────────


async def evaluate_medication_dose(db: AsyncSession, dose: Any, user: Any) -> int:
    """Judge a dose that has just been logged against what the patient declared.

    This is the half of the operator's instruction that had no implementation at
    all: *"notify when allergens exist in food or medication logged."* Nothing
    in `api/medications.py` or `services/med_dose_validation.py` referenced
    allergies — the dose guard checks whether a dose is physically possible
    (§3aj) and never whether this patient may take the drug.

    It matters on the reference record specifically: that profile's declared
    allergies are `Penicilin, Latex, Heparine, Raw Apples, Raw Berries` — three
    of the five are medications or materials, not food, and they were being
    consulted only by the meal planner.

    > ⚠️ **A misspelled allergy does not match the correctly-spelled drug.**
    > That profile says `Penicilin`; a dose logged as `Penicillin` does not hit,
    > because the matcher compares words and neither spelling is a prefix of the
    > other. The spelling is NOT silently corrected here — rewriting what a
    > patient declared about their own body is inventing a clinical fact, and
    > §3aj already settled that string similarity is the wrong instrument for
    > drug names ("calcium calcitriol" scores 0.63 against "calcium carbonate"
    > and its nearest match is a third drug). RxNorm's `approximateTerm` is the
    > right instrument and it is a network call, so it does not belong on this
    > path. Recorded as a known gap rather than papered over.
    """
    try:
        from app.services import food_safety

        name = getattr(dose, "medication_name", None)
        if not name:
            return 0
        guidance = await _guidance_for(db, user)
        # Only declared allergies and intolerances. A condition's FOOD trigger
        # must not be matched against a drug name: "avoid added sugars" has
        # nothing to say about a tablet, and firing there would be the
        # cry-wolf guard §3ab warns teaches its reader to tick past it.
        personal = [r for r in guidance.avoid
                    if r.kind in (food_safety.ALLERGY, food_safety.INTOLERANCE)]
        hits = food_safety.violations(str(name), personal)
        findings = [
            Finding(
                category=NotificationCategory.MEDICATION_CONFLICT,
                priority=NotificationPriority.URGENT,
                title=f"{r.label} is on your allergy list",
                message=(f"You logged {name}, which matches {r.label} on your "
                         f"profile. {r.reason}."),
                dedupe_key=f"med_allergy:{r.term}:{getattr(dose, 'id', '')}",
                action_url="/medications",
                authority=f"{r.kind}: {r.label}",
                extra={"term": r.term, "kind": r.kind,
                       "medication_name": str(name),
                       "dose_log_id": getattr(dose, "id", None)},
            )
            for r in hits
        ]
        if not findings:
            return 0
        return await emit(db, user.id, findings)
    except Exception:
        logger.exception("active_response: medication check failed for dose %s",
                         getattr(dose, "id", None))
        return 0


# ── Readings judged against the patient's own reported ranges ─────────────


async def evaluate_vitals(db: AsyncSession, entry: Any, user: Any) -> int:
    """Judge a vitals reading — the operator's first example, glucose.

    `api/vitals.py` performed no evaluation whatsoever: it computed a BMI and
    returned. The column has existed all along (`blood_glucose_mg_dl`, with
    `glucose_timing`), and `compute_goals` emits **no glucose target**, so there
    is no per-patient figure to compare against from that direction.

    The authority used instead is the range **this patient's own laboratory
    reported**, via `reference_ranges.resolve()`. On the reference record that
    is `Glucose 74–106 mg/dL`, carried on 9 of their 171 glucose results, and
    their most recent draw (2026-09-11) reads 143 — already above it. No number
    is introduced by this module; where the record has never reported a range,
    nothing fires.

    > **Timing decides which bound is usable, and only one of them is
    > unconditional.** A serum glucose range is a fasting range. Applying its
    > UPPER bound to a deliberate post-meal fingerstick would flag ordinary
    > postprandial physiology, and a guard that cries wolf is one its reader
    > learns to tick past (§3ab). The LOWER bound does not depend on whether
    > the patient has eaten — hypoglycaemia is hypoglycaemia — so it is always
    > applied. A post-prandial ceiling needs an authority this system does not
    > hold, and inventing one here is exactly what §0 forbids.
    """
    try:
        value = getattr(entry, "blood_glucose_mg_dl", None)
        if value is None:
            return 0

        from app.services import reference_ranges

        ranges = await reference_ranges.resolve(db, user.id)
        band = None
        for name in ("Glucose", "GLUCOSE", "glucose"):
            if name in ranges:
                band = ranges[name]
                break
        if not band:
            return 0
        low, high = band

        timing = (getattr(entry, "glucose_timing", None) or "").strip().lower()
        fasting_like = timing in ("", "fasting", "pre-meal", "pre_meal", "premeal")
        when = f" ({timing})" if timing else ""
        day = getattr(entry, "log_date", None)
        day_str = day.isoformat() if day else "unknown"

        findings: list[Finding] = []
        if value < low:
            findings.append(Finding(
                category=NotificationCategory.LAB_ANOMALY,
                priority=NotificationPriority.URGENT,
                title="Blood sugar below your reported range",
                message=(f"You logged {value:g} mg/dL{when}, below the low end of "
                         f"your own laboratory's range ({low:g}–{high:g} mg/dL)."),
                dedupe_key=f"glucose_low:{day_str}:{value:g}",
                action_url="/vitals",
                authority=f"this patient's reported Glucose range {low:g}-{high:g}",
                extra={"value": float(value), "low": low, "high": high,
                       "timing": timing, "date": day_str},
            ))
        elif value > high and fasting_like:
            findings.append(Finding(
                category=NotificationCategory.LAB_ANOMALY,
                priority=NotificationPriority.HIGH,
                title="Blood sugar above your reported range",
                message=(f"You logged {value:g} mg/dL{when}, above the high end of "
                         f"your own laboratory's range ({low:g}–{high:g} mg/dL)."),
                dedupe_key=f"glucose_high:{day_str}:{value:g}",
                action_url="/vitals",
                authority=f"this patient's reported Glucose range {low:g}-{high:g}",
                extra={"value": float(value), "low": low, "high": high,
                       "timing": timing, "date": day_str},
            ))
        if not findings:
            return 0
        return await emit(db, user.id, findings)
    except Exception:
        logger.exception("active_response: vitals check failed for entry %s",
                         getattr(entry, "id", None))
        return 0


async def resolved_range_for(db: AsyncSession, user_id: int, test_name: str
                             ) -> tuple[float, float] | None:
    """The range to judge `test_name` by, for a result that printed none.

    `api/labs.py` can only call a result anomalous when the row itself carries a
    reference range or a flag. Measured on production: of 9,791 results **9,091
    have `is_abnormal` NULL and only 680 carry a range** — so that gate is
    structurally unable to judge the overwhelming majority, which is why two
    lab notifications exist for nearly ten thousand results. §3aa already
    recorded the consequence of the same gap on the display side: 137 stored
    results numerically contradict their own printed range, including a
    potassium of 6.7 against 3.5–5.5.

    `reference_ranges.resolve()` is the ordering built for exactly this and it
    never invents a band: the patient's own most recent reported range, then the
    population mode, then a recorded guideline in `clinical_thresholds`, then a
    range learned from the central 95% of observed values — and then nothing.
    """
    try:
        from app.services import reference_ranges
        from app.services.docparse import dictionaries

        ranges = await reference_ranges.resolve(db, user_id)
        if test_name in ranges:
            return ranges[test_name]
        # §3ax: one analyte, many spellings — "ALP" and "Alk Phos" are the same
        # thing, and comparing stored wording is how half a series goes missing.
        try:
            want = dictionaries.analyte_key(test_name)
        except Exception:
            return None
        for name, band in ranges.items():
            try:
                if dictionaries.analyte_key(name) == want:
                    return band
            except Exception:
                continue
        return None
    except Exception:
        logger.exception("active_response: could not resolve a range for %r", test_name)
        return None
