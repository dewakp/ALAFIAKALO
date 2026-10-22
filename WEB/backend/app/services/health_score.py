# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Health score computed from measured values against the patient's own targets.

What this replaces, and why each piece was wrong:

- **Nutrition was `(days_tracked / 30) * 100`** — logging frequency, not health.
  Log every day while malnourished and it reads 100%. Adherence is intake
  measured against the patient's own limits and requirements, which
  `nutrient_goals_service.compute_goals` already derives from their biology and
  conditions (KDOQI 2020 for CKD). Scoring against those is the whole fix.

- **Missing data scored 0 and was still weighted.** An untracked domain dragged
  the total down as though the patient had failed at it. Not knowing is not the
  same as doing badly (canon 3aa, in a number). Unknown components are now
  excluded and NAMED, and the weights renormalise over what was actually
  measured.

- **…except where missing data scored full marks.** Mood used
  `(10 - avg_stress)`, and `avg_stress` defaulted to 0 when stress was never
  recorded — awarding 30 of 100 points for the absence of data. A scale that
  reads best when nothing is known is worse than no scale.

- **Vitals was BMI alone**, on dialysis patients, where weight is confounded by
  fluid between sessions.

The score is arithmetic over measured values, deliberately: it must be
reproducible, explainable to a clinician, and identical for the same inputs. No
LLM decides a number here. The AI layer may narrate a score; it does not compute
one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.dialysis_day_adjustment import FRESH_DAYS, STALE_DAYS
from app.services.finding_text import CONTEXT, DEVIATION, HARM, Finding


def median(values: list) -> float | None:
    """The middle value, or None when there is nothing to take one of.

    MEDIAN rather than mean for self-recorded vitals: these are a handful of
    readings taken in whatever circumstances the patient happened to be in —
    one is noted "Just after poop", another "Dizzy" — so a single unusual
    reading must not drag the figure the whole domain is scored on. §3am makes
    the same argument for intradialytic readings from the other direction,
    where the NADIR is the finding and a mean hides it: which statistic is
    honest depends on what the series is, and neither is a default.
    """
    numbers = sorted(float(v) for v in values if v is not None)
    if not numbers:
        return None
    middle = len(numbers) // 2
    if len(numbers) % 2:
        return numbers[middle]
    return (numbers[middle - 1] + numbers[middle]) / 2.0


#: Relative importance of each domain. Applied only over the domains that have
#: data — see `overall_score`.
#:
#: `dialysis`, `symptoms` and `elimination` were added 2026-10-04. A patient
#: with 2,032 dialysis sessions had NO dialysis contribution to their wellness
#: score, and a record holding 1,991 vomiting episodes and a symptom rated 9/10
#: had no way to express either. Three domains that could not be scored are
#: three domains that silently read as perfect.
DEFAULT_WEIGHTS: dict[str, float] = {
    "nutrition": 0.20,
    "vitals": 0.18,
    "dialysis": 0.17,
    "medication_adherence": 0.15,
    "symptoms": 0.08,
    "elimination": 0.07,
    "sleep": 0.06,
    "mood": 0.05,
    "fitness": 0.04,
}

# There is deliberately NO key-translation table here.
#
# `compute_goals` already emits the canonical nutrient keys — `potassium_mg`,
# `phosphorus_mg`, `protein_g` — the same ones `NUTRIENT_CATALOG` and the
# `nutrition_logs` columns use. A hand-written map between them was not merely
# redundant, it was WRONG: it translated "potassium" to "potassium_mg" while
# the goal key already was `potassium_mg`, so the lookup missed and potassium —
# the nutrient that matters most on dialysis — was silently never scored.
#
# The unit tests passed because their fixture invented the short key shape the
# map expected. A fixture that does not match what the producer emits proves
# nothing about the producer.


@dataclass
class Component:
    """One domain's contribution.

    `score is None` means UNKNOWN — no data — and is never treated as zero.
    """
    key: str
    score: float | None
    weight: float
    detail: dict[str, Any] = field(default_factory=dict)
    #: Findings that are dangerous on their own terms. A score is a summary and
    #: a summary can be read past; "35 of 37 treatments dropped below 90 mmHg"
    #: cannot. These travel beside the number so the number is never the whole
    #: message — the same reason `nutrition` names its shortfalls.
    #:
    #: `Finding` objects since 2026-10-11, NOT strings: facts plus a required
    #: deterministic fallback, with ALAFIA writing the sentence at read time
    #: (`finding_text.render`, local-only, verified against the facts).
    #:
    #: ⚠️ This annotation said `list[str]` for a while after the change —
    #: Python does not enforce it, the tests passed, and the only symptom was
    #: that the next reader would be told the wrong thing.
    critical: list[Finding] = field(default_factory=list)


def _limit_score(intake: float, limit: float) -> float:
    """100 while at or under the limit, falling to 0 at 50% over it.

    Asymmetric on purpose: for potassium and phosphorus the harm is in the
    excess, and there is no credit for eating implausibly little of them.
    """
    if limit <= 0:
        return 100.0
    ratio = intake / limit
    if ratio <= 1.0:
        return 100.0
    return max(0.0, 100.0 - ((ratio - 1.0) / 0.5) * 100.0)


def _target_score(intake: float, target: float) -> float:
    """100 on reaching the target, linear below it.

    Exceeding a target is not scored as a failure here — the nutrients carrying
    a hard ceiling are expressed as limits, and those are scored above.
    """
    if target <= 0:
        return 100.0
    return min(100.0, max(0.0, (intake / target) * 100.0))


def nutrition_adherence(intake: dict[str, float | None],
                        goals: list[dict[str, Any]]) -> Component:
    """Score mean daily intake against this patient's own goals.

    Only goals whose nutrient was actually measured contribute, so a meal log
    that never captured phosphorus does not read as perfect phosphorus control.
    Each goal is weighted by its `priority` where the caller supplies one.
    """
    scored: list[tuple[float, float]] = []   # (score, weight)
    per_nutrient: dict[str, Any] = {}

    for goal in goals or []:
        key = str(goal.get("key") or "").strip()
        if not key:
            continue
        value = intake.get(key)
        target = goal.get("goal")
        if value is None or target in (None, 0):
            continue
        kind = goal.get("kind") or "target"
        score = (_limit_score(float(value), float(target)) if kind == "limit"
                 else _target_score(float(value), float(target)))
        weight = float(goal.get("priority") or 1.0)
        scored.append((score, weight))
        per_nutrient[key] = {
            "intake": round(float(value), 1),
            "goal": float(target),
            "kind": kind,
            "unit": goal.get("unit"),
            "score": round(score, 1),
        }

    if not scored:
        return Component("nutrition", None, DEFAULT_WEIGHTS["nutrition"],
                         {"reason": "no nutrient goals could be matched to logged intake"})

    # Weighted GEOMETRIC mean, not arithmetic — the same aggregation HEBCS uses
    # across pathways, and for the same reason: one nutrient in serious deficit
    # must not be averaged away by the others.
    #
    # Staying under a limit is table stakes; it is not an achievement that can
    # pay for a protein deficit. Arithmetically, a patient eating half the
    # protein and half the energy they need still scored 78 because avoiding
    # potassium and phosphorus scored 100 twice. That is "Nutrition 100% while
    # malnourished" wearing a different number.
    total_w = sum(w for _, w in scored)
    # A zero would annihilate the product, so floor each term — a nutrient
    # scoring 0 should dominate the result, not erase it.
    log_sum = sum(w * math.log(max(s, 1.0)) for s, w in scored)
    value = math.exp(log_sum / total_w)

    shortfalls = sorted(
        (k for k, v in per_nutrient.items() if v["score"] < 70),
        key=lambda k: per_nutrient[k]["score"])
    return Component("nutrition", round(value, 1), DEFAULT_WEIGHTS["nutrition"],
                     {"nutrients": per_nutrient,
                      "nutrients_scored": len(scored),
                      # Named so the number is never the whole message.
                      "shortfalls": shortfalls})


def sleep_component(avg_hours: float | None, avg_quality: float | None) -> Component:
    """7–9 h is the band; quality contributes only when it was recorded."""
    if avg_hours is None and avg_quality is None:
        return Component("sleep", None, DEFAULT_WEIGHTS["sleep"], {"reason": "no sleep logged"})

    parts: list[tuple[float, float]] = []
    detail: dict[str, Any] = {}
    if avg_hours is not None:
        if 7 <= avg_hours <= 9:
            hours_score = 100.0
        elif avg_hours < 7:
            hours_score = max(0.0, (avg_hours / 7) * 100.0)
        else:
            hours_score = max(60.0, 100.0 - ((avg_hours - 9) * 20))
        parts.append((hours_score, 0.6))
        detail["avg_hours"] = round(avg_hours, 1)
    if avg_quality is not None:
        parts.append((min(100.0, max(0.0, avg_quality * 10)), 0.4))
        detail["avg_quality"] = round(avg_quality, 1)

    total_w = sum(w for _, w in parts)
    return Component("sleep", round(sum(s * w for s, w in parts) / total_w, 1),
                     DEFAULT_WEIGHTS["sleep"], detail)


def mood_component(avg_mood: float | None, avg_energy: float | None,
                   avg_stress: float | None) -> Component:
    """Only the sub-scales actually recorded contribute.

    The previous form was `(10 - avg_stress) * 10 * 0.3` with `avg_stress`
    defaulting to 0, so never recording stress was worth 30 points. Absence is
    now absence.
    """
    parts: list[tuple[float, float]] = []
    detail: dict[str, Any] = {}
    if avg_mood is not None:
        parts.append((min(100.0, max(0.0, avg_mood * 10)), 0.4))
        detail["avg_mood"] = round(avg_mood, 1)
    if avg_energy is not None:
        parts.append((min(100.0, max(0.0, avg_energy * 10)), 0.3))
        detail["avg_energy"] = round(avg_energy, 1)
    if avg_stress is not None:
        parts.append((min(100.0, max(0.0, (10 - avg_stress) * 10)), 0.3))
        detail["avg_stress"] = round(avg_stress, 1)

    if not parts:
        return Component("mood", None, DEFAULT_WEIGHTS["mood"], {"reason": "no mood entries"})
    total_w = sum(w for _, w in parts)
    return Component("mood", round(sum(s * w for s, w in parts) / total_w, 1),
                     DEFAULT_WEIGHTS["mood"], detail)


def fitness_component(workouts_per_week: float | None) -> Component:
    if workouts_per_week is None:
        return Component("fitness", None, DEFAULT_WEIGHTS["fitness"],
                         {"reason": "no activity logged"})
    if 3 <= workouts_per_week <= 5:
        score = 100.0
    elif workouts_per_week < 3:
        score = (workouts_per_week / 3) * 100.0
    else:
        score = max(60.0, 100.0 - ((workouts_per_week - 5) * 10))
    return Component("fitness", round(score, 1), DEFAULT_WEIGHTS["fitness"],
                     {"workouts_per_week": round(workouts_per_week, 1)})


def band_score(value: float, band: tuple[float | None, float, float, float | None]
               ) -> float:
    """A value against a four-bound band, as 0-100.

    The curve is `hebcs_engine.trapezoidal_score` — imported rather than
    rewritten, because two implementations of one curve is how a correction
    lands on one and misses the other. A band with no critical bound on a side
    applies no penalty on that side, which is the engine's existing meaning.
    """
    from app.services.hebcs_engine import Biomarker, trapezoidal_score

    crit_low, opt_low, opt_high, crit_high = band
    return trapezoidal_score(float(value), Biomarker(
        name="", crit_low=crit_low, opt_low=opt_low,
        opt_high=opt_high, crit_high=crit_high)) * 100.0


def vitals_component(*, bands: dict[str, tuple[float | None, float, float, float | None]] | None = None,
                     bmi: float | None = None,
                     systolic: float | None = None,
                     diastolic: float | None = None,
                     heart_rate: float | None = None,
                     sample_size: int = 0,
                     latest_on=None,
                     age_days: int | None = None,
                     pressure_measured_on=None,
                     post_dialysis_systolics: list[float] | None = None,
                     on_dialysis: bool = False) -> Component:
    """Blood pressure, pulse, and what the treatment itself did to them.

    ⚠️ **`systolic` is a WINDOW's median, not the newest reading, and the
    difference was a real complaint.** This scored the single most recent
    `vitals_logs` row and the finding read *"Resting systolic 81 mmHg is below
    the 90-120 mmHg reference band"* — a true reading from 2026-09-26 07:00,
    **fifteen days old**, stated with no date as though it were this morning's,
    on a patient whose 43 self-recorded readings average 97. Asked "81 mmHg?
    how?", there was no good answer: n=1 is the same error as an all-time mean,
    from the other end (§3an, "windows, not lifetimes").

    It is also no longer called **resting**. Nothing in `vitals_logs` records
    posture or activity — the row that produced the 81 happens to be noted
    "Just woke up after an 8 hr sleep", and the one before it reads "Just after
    poop". Asserting a condition the record does not state is §0 in a sentence
    a clinician reads.

    `age_days` is judged against `dialysis_day_adjustment.FRESH_DAYS` /
    `STALE_DAYS` (14/30) — §3an is explicit that lab recency is already defined
    and a second window must not be invented for it.

    **The band this used to carry was one-sided and written into the source:**

        if systolic < 130 and diastolic < 80:
            bp_score = 100.0

    It penalised only HIGH pressure, so it had no way to express hypotension at
    all. Measured on the reference record 2026-10-04, that is not academic — the
    patient's latest reading is **81/62** and scored **100.0**, and so would
    54/30. Across 90 days **25 of 37 treatments ended below 90 mmHg systolic,
    the lowest at 54**, beside a pulse of 96-109 on every reading. The screen
    showed `Vitals 100/100` throughout.

    Three faults, each independent of the others:

    - **No lower bound.** Hypotension is the finding on this record and the
      scale could not represent it.
    - **Heart rate was never read.** The column has always existed.
    - **Only `vitals_logs` was consulted** — one row, three in the whole
      window — while `therapy_sessions` carries a pre/post pair for every
      treatment. The richest blood-pressure series in the record was invisible
      to the one component whose job is blood pressure.

    Every band now comes from `clinical_thresholds` via
    `reference_ranges.bands()`, with its guideline recorded beside it, because
    `test_no_hardcoded_thresholds.py` already states the canon — *no hardcoded
    data, no exception* — and only ever reached `hebcs_engine`. An input with no
    band is left UNSCORED rather than judged against a number invented here.
    """
    bands = bands or {}
    parts: list[tuple[float, float]] = []
    detail: dict[str, Any] = {}
    critical: list[str] = []

    def _band(name: str):
        return bands.get(name)

    sys_band, dia_band = _band("Blood Pressure Systolic"), _band("Blood Pressure Diastolic")
    if systolic is not None and sys_band:
        s = band_score(systolic, sys_band)
        parts.append((s, 0.35))
        detail["systolic"] = round(float(systolic))
        detail["systolic_band"] = [sys_band[1], sys_band[2]]
        detail["self_recorded_readings"] = sample_size
        if latest_on is not None:
            detail["latest_self_recorded"] = str(latest_on)
        if systolic < sys_band[1]:
            # Says WHAT it is (a median of self-recorded readings), HOW MANY,
            # and WHEN the most recent was — the three things missing when a
            # single fifteen-day-old row was reported as "Resting systolic 81".
            # "Self-recorded" named one of OUR tables, not anything the
            # patient would recognise. Operator: "what is self-recorded?"
            # "readings they took themselves" invited the obvious question —
            # who else would take it? The distinction that matters is not WHO
            # holds the cuff, it is WHERE and WHEN: a pressure away from
            # dialysis is a different measurement from one taken mid-treatment
            # with fluid coming off, which is exactly why §3am forbids
            # averaging the sources together.
            provenance = (
                f"median of {sample_size} readings taken away from dialysis"
                if sample_size > 1 else "one reading taken away from dialysis"
            )
            # §3an: "Print a blood pressure as a blood pressure." Reporting
            # the systolic alone left the finding stating half a measurement —
            # 86 is not a blood pressure, 86/62 is. The diastolic was already
            # SCORED (weight 0.15) and simply never said.
            #
            # And the source is described in plain words rather than named by
            # our table. "Self-recorded" is a distinction between `vitals_logs`
            # and the flowsheet — ours, not the patient's — and it reached the
            # screen raw.
            facts = {
                "measure": "blood pressure",
                "source": "readings taken away from dialysis, logged by the patient",
                "statistic": "median of the window",
                "systolic": round(float(systolic)),
                "unit": "mmHg",
                "systolic_reference_low": sys_band[1],
                "systolic_reference_high": sys_band[2],
                "systolic_below_reference": True,
                "readings_in_window": sample_size,
                "window_days": 30,
            }
            if diastolic is not None:
                facts["diastolic"] = round(float(diastolic))
                if dia_band:
                    facts["diastolic_reference_low"] = dia_band[1]
                    facts["diastolic_reference_high"] = dia_band[2]
                    facts["diastolic_below_reference"] = (
                        float(diastolic) < dia_band[1])
            if latest_on is not None:
                facts["last_self_recorded_on"] = str(latest_on)
            if age_days is not None:
                facts["days_since_self_recorded"] = age_days
            if pressure_measured_on is not None:
                facts["pressure_last_measured_at_treatment_on"] = str(
                    pressure_measured_on)
            reading = (f"{round(float(systolic))}/{round(float(diastolic))}"
                       if diastolic is not None else
                       f"{round(float(systolic))}")
            note = (
                f"Blood pressure {reading} mmHg ({provenance}) has a systolic "
                f"below the {sys_band[1]:g}-{sys_band[2]:g} mmHg reference "
                f"band")
            if age_days is not None and age_days > FRESH_DAYS:
                # §3an: a value nobody has checked recently is reported as
                # stale, never offered as the current one.
                #
                # ⚠️ But the staleness is about SELF-RECORDING, not about the
                # patient's blood pressure, and saying "the most recent was 15
                # days ago" asserted the second. Measured: their pressure was
                # last taken 2026-10-09, at treatment — two days before the
                # card claimed a fortnight's silence, and the SAME card then
                # said "35 of 37 treatments dropped below 90 during dialysis".
                # It contradicted itself two sentences apart, which is §3aa in
                # a sentence: one source read and spoken of as the whole.
                note += (f" — last such reading {age_days} days ago "
                         f"({latest_on})")
                if (pressure_measured_on is not None
                        and latest_on is not None
                        and pressure_measured_on > latest_on):
                    note += (f", though pressure was measured at treatment on "
                             f"{pressure_measured_on}")
                else:
                    note += ", so this may not be current"
            elif latest_on is not None:
                note += f" (most recent {latest_on})"
            # ── HOW MUCH EVIDENCE IS THIS, REALLY ──────────────────────────
            #
            # Operator, 2026-10-22: *"The first sentence references data from
            # more than a month ago as if it's the rubric."* Measured on the
            # reference record that day:
            #
            #     self-recorded BP in the 30-day window    1   (2026-09-26)
            #     self-recorded BP in 90 days              8   (newest the same)
            #     dialysis sessions in 90 days            35
            #     intradialytic readings in 90 days      100
            #
            # So the card LED with a median of ONE reading, 26 days old, ahead
            # of a hundred measured pressures — and this function's own
            # docstring already says "n=1 is the same error as an all-time
            # mean, from the other end". Saying so honestly in the sentence
            # does not stop it being the headline.
            #
            # It is still reported, because 81/62 is a real reading and
            # dropping it would be §3aa's empty state. It is reported LAST.
            # `FRESH_DAYS` is the recency authority §3an already defines, and
            # "a median of one" is a false description of the statistic this
            # finding claims to report — not an invented threshold.
            thin = sample_size <= 1
            stale = age_days is not None and age_days > FRESH_DAYS
            critical.append(Finding(
                kind="blood_pressure_below_reference", domain="vitals",
                facts=facts, fallback=note + ".",
                severity=CONTEXT if (thin or stale) else DEVIATION,
                # The reading and the bound it breaches ARE the finding;
                # counts, dates and the window are context the sentence may
                # leave out.
                # The DIASTOLIC is essential, not context. Left optional, the
                # model wrote "Median systolic blood pressure 86 mmHg" and
                # dropped the 60 — reintroducing the half-a-measurement the
                # operator objected to in the first place.
                essential=("systolic", "diastolic",
                           "systolic_reference_low")))
    if diastolic is not None and dia_band:
        parts.append((band_score(diastolic, dia_band), 0.15))
        detail["diastolic"] = round(float(diastolic))
    if systolic is not None and diastolic is not None:
        detail["blood_pressure"] = f"{round(float(systolic))}/{round(float(diastolic))}"

    hr_band = _band("Heart Rate")
    if heart_rate is not None and hr_band:
        parts.append((band_score(heart_rate, hr_band), 0.20))
        detail["heart_rate"] = round(float(heart_rate))
        if heart_rate > hr_band[2]:
            critical.append(Finding(
                kind="pulse_above_band", domain="vitals",
                # Same self-recorded window as the pressure above, so it
                # carries the same evidence caveat.
                severity=CONTEXT if (sample_size <= 1 or (
                    age_days is not None and age_days > FRESH_DAYS))
                else DEVIATION,
                facts={"measure": "resting pulse",
                       "value": round(float(heart_rate)), "unit": "bpm",
                       "reference_band_low": hr_band[1],
                       "reference_band_high": hr_band[2], "above_band": True},
                fallback=(f"Resting pulse {round(float(heart_rate))} bpm is above the "
                          f"{hr_band[1]:g}-{hr_band[2]:g} bpm reference band.")))

    # ── What the treatment did, judged on its own band ───────────────────
    # A resting systolic of 95 is unremarkable; the same figure at the end of a
    # treatment is intradialytic hypotension. One band cannot express both.
    post_band = _band("Post-Dialysis Systolic BP")
    readings = [float(v) for v in (post_dialysis_systolics or []) if v is not None]
    if readings and post_band:
        floor = post_band[1]
        below = [v for v in readings if v < floor]
        nadir = min(readings)
        # The NADIR is the finding, not the mean — §3am's rule for
        # intradialytic readings, and for the same reason: a mean hides the
        # session that ended at 54.
        parts.append((band_score(nadir, post_band), 0.30))
        detail["post_dialysis_sessions"] = len(readings)
        detail["post_dialysis_nadir"] = round(nadir)
        detail["post_dialysis_below_floor"] = len(below)
        # DELIBERATELY NO FINDING HERE — the score above stays, the sentence
        # moves to `dialysis_component`. Beside that component's own
        # hypotension finding
            # this produced two bullets that read as a contradiction:
            #
            #   "26 of 33 treatments ended below 90 mmHg systolic (lowest 54)."
            #   "35 of 37 treatments (95%) dropped below 90 mmHg systolic
            #    during dialysis (lowest 39); 16 fell below 70."
            #
            # Both true, measuring different things over different
            # denominators — 33 sessions carry a POST reading, 37 carry any
            # pressure at all (the other 4 have intradialytic readings and no
            # post value) — and worded so alike that the only reasonable
            # reading was that one of them was wrong. One clinical story gets
            # one sentence, and it is told where the treatment is scored.

    if bmi is not None and not on_dialysis:
        if 18.5 <= bmi < 25:
            bmi_score = 100.0
        elif 25 <= bmi < 30 or 17 <= bmi < 18.5:
            bmi_score = 75.0
        else:
            bmi_score = 50.0
        parts.append((bmi_score, 0.15))
        detail["bmi"] = round(bmi, 1)
    elif bmi is not None:
        detail["bmi_excluded"] = (
            "BMI is not scored on dialysis — weight varies with fluid between sessions")

    if not parts:
        missing = ("no blood pressure recorded" if not bands
                   else "no vital sign had a band to be judged against")
        return Component("vitals", None, DEFAULT_WEIGHTS["vitals"],
                         {"reason": missing, **detail})

    total_w = sum(w for _, w in parts)
    return Component("vitals", round(sum(s * w for s, w in parts) / total_w, 1),
                     DEFAULT_WEIGHTS["vitals"], detail, critical)


def overall_score(components: list[Component]) -> dict[str, Any]:
    """Weighted mean over the components that HAVE data.

    Renormalising is the point. Previously an unmeasured domain contributed 0 at
    full weight, so a patient tracking three domains well could not exceed the
    combined weight of those three no matter how well they did.

    Returns `overall = None` when nothing was measured — a score of 0 for a
    patient we know nothing about is a statement we cannot support.
    """
    scored = [c for c in components if c.score is not None]
    unknown = [c.key for c in components if c.score is None]

    if not scored:
        return {
            "overall_score": None,
            "grade": None,
            "component_scores": {c.key: None for c in components},
            "components_scored": [],
            "components_unknown": unknown,
            "confidence": 0.0,
            "detail": {c.key: c.detail for c in components},
        }

    total_w = sum(c.weight for c in scored)

    # Weighted GEOMETRIC mean, not arithmetic — the same aggregation
    # `nutrition_adherence` already uses one level down, for the reason stated
    # there: a domain in serious trouble must not be averaged away by the
    # others. It is also the property the HEBCS framework argues for between
    # pathways ("failure in any single pathway cannot be masked").
    #
    # Measured on the reference record: nutrition 37.4, vitals 100.0,
    # medication 57.1 produced an arithmetic 59.6 — a passing number resting on
    # a vitals score of 100 awarded to a patient whose latest reading was
    # 81/62. Under a geometric mean a failing domain pulls the result toward
    # itself instead of being paid for by a domain that happens to read well.
    #
    # Floored at 1.0 per term so a single zero cannot annihilate the product:
    # a domain scoring 0 should dominate the result, not erase it.
    log_sum = sum(c.weight * math.log(max(c.score, 1.0)) for c in scored)
    overall = math.exp(log_sum / total_w)

    # How much of the intended picture was actually available.
    confidence = total_w / sum(c.weight for c in components)

    # Findings that must survive the summary. A number can be read past; a
    # sentence naming 25 treatments that ended below 90 mmHg cannot.
    #
    # ── ORDERED BY WHAT KIND OF CLAIM THEY MAKE, NOT BY COMPONENT ─────────
    #
    # This was `[line for c in scored for line in (c.critical or [])]` — the
    # order the components happen to be listed in by the caller. Operator,
    # 2026-10-22: *"The significance I cannot understand."* On the card that
    # prompted it, a median of ONE 26-day-old blood pressure led, and
    # *"35 of 37 treatments dropped below 90 mmHg systolic (lowest 39); 16
    # fell below 70"*, a 9/10 abdominal pain and blood in the stool all came
    # after it — purely because `vitals_component` sits third in a list.
    #
    # `sorted` is stable, so findings of equal severity keep that component
    # order and the ranking only ever moves a finding past one of a DIFFERENT
    # kind. See `finding_text.Finding.severity` for the three levels and why
    # they are about the kind of claim rather than a clinical threshold.
    critical = sorted(
        (line for c in scored for line in (c.critical or [])),
        key=lambda f: getattr(f, "severity", DEVIATION))

    return {
        "overall_score": round(overall, 1),
        "grade": grade_for(overall),
        "component_scores": {c.key: c.score for c in components},
        "components_scored": [c.key for c in scored],
        "components_unknown": unknown,
        "confidence": round(confidence, 2),
        "critical_findings": critical,
        "detail": {c.key: c.detail for c in components},
    }


def medication_adherence(prescribed_names: list[str],
                         logged_names: list[str]) -> Component:
    """How much of the prescribed regimen shows up in the dose log.

    The previous rule was `80 if the user has any active medication row else
    50` — a placeholder that measured only whether a row existed, labelled
    "adherence" and shown to patients as part of a health score.

    Two things this deliberately does NOT do:

    - It does not report 50 (or anything) when the patient has no active
      prescription. We then do not know what they were meant to take, so
      adherence is UNKNOWN. That case is common and not a failing: an account
      may hold 943 dose logs and zero prescriptions, because prescriptions are
      written by the EHR import while dose logs are what the patient took
      (canon 3aa).
    - It does not count doses against a schedule. Frequency is free text
      ("twice daily", "with meals"), so a denominator parsed from it would be
      invented precision. Presence-in-window per drug is a claim the data
      supports.

    Names are compared case-insensitively — the same drug arrives as both
    "Calcium Carbonate" and "Calcium carbonate".
    """
    prescribed = {str(n).strip().lower() for n in prescribed_names if str(n or "").strip()}
    if not prescribed:
        return Component("medication_adherence", None,
                         DEFAULT_WEIGHTS["medication_adherence"],
                         {"reason": "no active prescription on file, so there is "
                                    "nothing to measure adherence against"})

    logged = {str(n).strip().lower() for n in logged_names if str(n or "").strip()}
    taken = prescribed & logged
    missing = sorted(prescribed - logged)
    score = (len(taken) / len(prescribed)) * 100.0

    return Component("medication_adherence", round(score, 1),
                     DEFAULT_WEIGHTS["medication_adherence"],
                     {"prescribed": len(prescribed),
                      "logged_in_window": len(taken),
                      # Named, because "70%" does not tell a clinician WHICH drug.
                      "not_logged": missing})


#: How many EARLIER treatments must carry a dry weight before their spread is
#: treated as this patient's established variation. A sample-size floor, not a
#: clinical threshold — two points have a spread by arithmetic and not by
#: observation, and the finding states the count so the reader can judge it.
MIN_DRY_WEIGHTS_TO_COMPARE = 5


def _dry_weight_disagreement(
        dry_weights: list[tuple[Any, float]] | None,
        window_days: int) -> tuple[Finding, dict[str, Any]] | None:
    """The dry weight ordered most recently, against every one before it.

    Returns None unless the latest figure sits outside the whole range of the
    others by more than that range's own width — see `dialysis_component`.

    **Only the LATEST order is examined.** It is the one the next treatment's
    ultrafiltration will be computed from. A figure that was off once and has
    since been corrected is in the record and does not need to keep shouting.
    """
    entries = [(d, float(v)) for d, v in (dry_weights or []) if v is not None]
    if len(entries) < MIN_DRY_WEIGHTS_TO_COMPARE + 1:
        return None

    entries.sort(key=lambda row: (row[0] is None, row[0]))
    ordered_on, ordered = entries[-1]
    others = [v for _, v in entries[:-1]]
    lo, hi = min(others), max(others)
    # Rounded before comparing so float noise cannot decide a borderline case.
    spread = round(hi - lo, 2)
    if ordered < lo:
        direction, gap, bound = "below", round(lo - ordered, 2), "usual_lowest"
    elif ordered > hi:
        direction, gap, bound = "above", round(ordered - hi, 2), "usual_highest"
    else:
        return None
    if gap <= spread:
        return None

    facts = {
        "measure": "ordered dry weight",
        "ordered_dry_weight": round(ordered, 1),
        "unit": "kg",
        "direction": direction,
        "difference": gap,
        "usual_lowest": round(lo, 1),
        "usual_highest": round(hi, 1),
        "treatments_compared": len(others),
        "window_days": window_days,
    }
    if ordered_on is not None:
        facts["ordered_on"] = str(ordered_on)[:10]
    when = f" on {facts['ordered_on']}" if ordered_on is not None else ""
    return (
        Finding(
            kind="dry_weight_disagrees_with_record", domain="dialysis",
            severity=DEVIATION,   # a prescription disagreeing with the record
            facts=facts,
            fallback=(
                f"The dry weight ordered{when} is {ordered:g} kg, {gap:g} kg "
                f"{direction} the {'lowest' if direction == 'below' else 'highest'} "
                f"of the {len(others)} recorded over the last {window_days} days "
                f"({lo:g}-{hi:g} kg)."),
            # Both are needed or the sentence states no disagreement: the
            # figure ordered, and the bound of what the record holds.
            essential=("ordered_dry_weight", bound)),
        {"ordered": round(ordered, 1), "usual_range": [round(lo, 1), round(hi, 1)],
         "treatments_compared": len(others), "difference": gap,
         "direction": direction},
    )


def dialysis_component(*, sessions_in_window: int,
                       window_days: int,
                       baseline_per_week: float | None,
                       latest_ktv: float | None = None,
                       ktv_band: tuple[float | None, float, float, float | None] | None = None,
                       sessions_with_pressure: int = 0,
                       sessions_below_floor: int = 0,
                       sessions_severely_below: int = 0,
                       sessions_ended_below_floor: int = 0,
                       sessions_with_post_reading: int = 0,
                       lowest_post: float | None = None,
                       lowest_nadir: float | None = None,
                       hypotension_floor: float | None = None,
                       severe_floor: float | None = None,
                       ktv_measured_on=None,
                       today: date | None = None,
                       dry_weights: list[tuple[Any, float]] | None = None,
                       ) -> Component:
    """Is the treatment happening, is it clearing enough, and is it TOLERATED?

    ⚠️ **The third question was missing, and its absence made this score say the
    opposite of the truth.** Until 2026-10-11 this measured attendance and Kt/V
    only, so on the reference record it returned **94** while the same page
    printed *"26 of 33 treatments ended below 90 mmHg systolic (lowest 54)"*.
    Operator: *"still measuring frequency of log"* — exactly right. Showing up
    is an event count, not a clinical state, and a score built from event counts
    reports a patient as well because they are diligent.

    Measured over 90 days on that record: **38 sessions, 30 with an
    intradialytic nadir below 90 (79%), 14 below 70 (37%), lowest 39.**
    Attendance was perfect throughout. A treatment attended and survived badly
    is not a treatment going well.

    **This is not double-counting `vitals_component`.** That scores the nadir
    VALUE — how low it got, once, across the window. This scores the BURDEN —
    in what FRACTION of treatments it happened. A patient who dipped to 39 on
    one occasion and a patient who drops below 90 in four treatments out of five
    are different clinical pictures, and a single number cannot hold both.

    The floor is the `Post-Dialysis Systolic BP` band's own lower bound, passed
    in by the caller — the SAME band `vitals_component` reads, so the two
    surfaces cannot disagree about what counts as low, and no threshold is
    invented here (§3az: hardcoded thresholds that were LOOSER than the
    patient's real limits are why that canon exists).

    A patient on dialysis who misses treatment cannot be well, and until now
    nothing in this score could express that: `wellness_scores` had no dialysis
    column, so a record with 2,032 sessions contributed exactly nothing.

    **Attendance is measured against the patient's OWN established cadence, not
    a constant.** There is no prescribed-schedule column anywhere in this
    schema — `therapy_sessions` carries `day_of_week` and
    `next_session_scheduled` and no frequency — so a hardcoded "three per week"
    would be a number invented here and wrong for everyone on a different
    regimen. Home and nocturnal schedules vary widely. Their own long-run rate
    is a fact about them; a constant is a fact about nobody.

    `status` is deliberately NOT the instrument. The enum has a MISSED value
    and nothing has ever written it — all 2,032 rows on the reference record
    read COMPLETED — so counting missed rows would report perfect attendance
    for every patient forever (§3ar: a control nothing writes measures
    nothing). A drop in RATE is observable from the rows that do exist.

    Adequacy uses the band from `clinical_thresholds` (KDOQI Kt/V >= 1.4), the
    same row `hebcs_engine` scores against, so the two cannot disagree.

    **`dry_weights` reports a prescription that disagrees with the record**, and
    it is here because the alternative was found in a patient's chart. Session
    2776 arrived from a DaVita report ordering a target weight of **50.0 kg**
    while the 38 treatments before it recorded 53.2-54.8 — and the discrepancy
    was preserved by typing a paragraph about it into `patient_notes`, together
    with an instruction to raise it with the care team. Operator: *"this is not
    patient notes but your own debate."* Correct: the chart holds what the
    document said, and an ANALYSIS of the chart belongs here, where it is
    re-derived from the rows on every read instead of ageing in a text field
    that no query can reach.

    The target weight is what the machine's UF volume is computed from, so an
    order 3.3 kg low asks the treatment to remove three extra litres.

    **No threshold is invented for it** (§3az). The comparison is against this
    patient's own record and nothing else: the figure must sit outside the full
    range of every other dry weight in the window, and sit outside it by more
    than that range's own width. A dry weight being tapered deliberately moves
    in steps well inside its historical spread and is silent; a single order
    further out than the figure has ever travelled is not.
    """
    parts: list[tuple[float, float]] = []
    detail: dict[str, Any] = {}
    critical: list[str] = []

    weeks = max(window_days / 7.0, 1e-6)
    rate = sessions_in_window / weeks
    detail["sessions_in_window"] = sessions_in_window
    detail["window_days"] = window_days
    detail["sessions_per_week"] = round(rate, 2)

    if baseline_per_week and baseline_per_week > 0:
        detail["baseline_per_week"] = round(baseline_per_week, 2)
        # Attending at or above their own established rate is full marks;
        # falling away from it scales down. Above baseline is not extra credit.
        ratio = min(rate / baseline_per_week, 1.0)
        # Attendance drops from half the score to 0.3. It is a real input — a
        # patient who misses treatment cannot be well — but it must not be able
        # to carry the domain on its own, which is precisely how 94 happened.
        parts.append((ratio * 100.0, 0.3))
        if ratio < 0.8:
            missed = (baseline_per_week - rate) * weeks
            critical.append(Finding(
                kind="attendance_below_baseline", domain="dialysis",
                severity=DEVIATION,   # against this patient's own baseline
                facts={"measure": "dialysis attendance",
                       "sessions_per_week": round(rate, 1),
                       "usual_sessions_per_week": round(baseline_per_week, 1),
                       "sessions_fewer_than_expected": round(missed),
                       "window_days": window_days},
                fallback=(f"Treatment has fallen to {rate:.1f} sessions a week against "
                          f"their usual {baseline_per_week:.1f} — about {missed:.0f} "
                          f"fewer than expected over {window_days} days.")))
    else:
        detail["baseline"] = ("no established treatment rate yet, so attendance "
                              "is not scored")

    # ── ADEQUACY IS A DATED MEASUREMENT, AND THIS IGNORED THE DATE ───────
    #
    # Operator, 2026-10-22: *"critical findings must be prescient not stale,
    # unless they are perenial/chronic."* Kt/V is neither chronic nor a
    # pattern — it is one lab draw — and this block had no date at all, while
    # the caller's query had no date filter either. A Kt/V from any point in
    # the patient's history produced a "below target" critical finding AND
    # scored the dialysis domain, stated as though it were this month's.
    #
    # §3an already settles the bound: lab recency is FRESH_DAYS/STALE_DAYS
    # (14/30), scaled to a monthly draw cadence, and "a 147-day-old draw is
    # reported as ABSENT, not as the latest". Kt/V is drawn monthly on
    # dialysis, so the 30-day edge is the one that applies.
    ktv_age = None
    if ktv_measured_on is not None:
        reference = today or date.today()
        when = ktv_measured_on
        if hasattr(when, "date") and not isinstance(when, date):
            when = when.date()
        try:
            ktv_age = (reference - when).days
        except TypeError:
            ktv_age = None
    ktv_is_stale = ktv_age is not None and ktv_age > STALE_DAYS

    if latest_ktv is not None and ktv_band:
        detail["ktv"] = round(float(latest_ktv), 2)
        detail["ktv_target"] = ktv_band[1]
        if ktv_measured_on is not None:
            detail["ktv_measured_on"] = str(ktv_measured_on)
        if ktv_is_stale:
            # NOT scored. Adequacy from months ago is not current adequacy,
            # and scoring it asserts a clearance nobody has measured since.
            detail["ktv_note"] = (
                f"drawn {ktv_age} days ago, beyond the {STALE_DAYS}-day "
                f"recency bound — reported, not scored")
        else:
            parts.append((band_score(latest_ktv, ktv_band), 0.3))
        if latest_ktv < ktv_band[1]:
            facts = {"measure": "delivered Kt/V",
                     "value": round(float(latest_ktv), 2),
                     "adequacy_target": ktv_band[1], "below_target": True}
            if ktv_age is not None:
                facts["days_ago"] = ktv_age
            if ktv_measured_on is not None:
                facts["measured_on"] = str(ktv_measured_on)
            critical.append(Finding(
                kind="ktv_below_target", domain="dialysis",
                # A current draw under target is a real deviation; one from
                # beyond the recency bound is history and must not lead.
                severity=CONTEXT if ktv_is_stale else DEVIATION,
                facts=facts,
                fallback=(f"Delivered Kt/V {latest_ktv:.2f} is below the "
                          f"{ktv_band[1]:g} adequacy target"
                          + (f", measured {ktv_age} days ago"
                             if ktv_age is not None else "") + ".")))

    # ── How the treatments GO, which is the half that was missing ────────
    if sessions_with_pressure and hypotension_floor is not None:
        burden = sessions_below_floor / sessions_with_pressure
        # Carries the largest single weight, because on a patient who attends
        # reliably it is the only thing that can distinguish a treatment course
        # that is working from one that is not.
        parts.append((max(0.0, 100.0 * (1.0 - burden)), 0.4))
        detail["sessions_with_pressure"] = sessions_with_pressure
        detail["sessions_below_floor"] = sessions_below_floor
        detail["hypotension_floor"] = hypotension_floor
        detail["hypotension_burden_pct"] = round(burden * 100, 1)
        if lowest_nadir is not None:
            detail["lowest_nadir"] = round(float(lowest_nadir))
        if sessions_below_floor:
            note = (
                f"In the last {window_days} days, {sessions_below_floor} of "
                f"{sessions_with_pressure} treatments ({burden * 100:.0f}%) "
                f"dropped below {hypotension_floor:g} mmHg systolic during "
                "dialysis")
            if lowest_nadir is not None:
                note += f" (lowest {round(float(lowest_nadir))})"
            # Stated separately because it is a different severity, not a
            # louder version of the same one. The severe bound is the band's
            # own CRITICAL low (`band[0]`), never a number chosen here — I had
            # written `below 70` literally, two paragraphs under a docstring
            # citing §3az for exactly that mistake.
            if sessions_severely_below and severe_floor is not None:
                detail["sessions_severely_below"] = sessions_severely_below
                detail["severe_floor"] = severe_floor
                note += (f"; {sessions_severely_below} fell below "
                         f"{severe_floor:g}")
            tolerance_facts = {
                "measure": "systolic blood pressure during dialysis",
                "treatments_below_floor": sessions_below_floor,
                "treatments_with_a_reading": sessions_with_pressure,
                "percent_of_treatments": round(burden * 100),
                "floor": hypotension_floor, "unit": "mmHg",
                # A count with no period is not a finding. "26 of 33
                # treatments" could be a week or a year, and the reader
                # cannot tell which — the same fault as a blood pressure
                # printed without its date.
                "window_days": window_days,
            }
            # The post-treatment count travels WITH the during-treatment one,
            # so the two denominators are read together instead of as rival
            # claims. "Still below when the treatment ended" is a different
            # fact from "went below at some point" — one is about going home.
            if sessions_with_post_reading:
                tolerance_facts["treatments_still_below_at_the_end"] = (
                    sessions_ended_below_floor)
                tolerance_facts["treatments_with_an_end_of_treatment_reading"] = (
                    sessions_with_post_reading)
                if lowest_post is not None:
                    tolerance_facts["lowest_at_end_of_treatment"] = round(
                        float(lowest_post))
            if lowest_nadir is not None:
                tolerance_facts["lowest"] = round(float(lowest_nadir))
            if sessions_severely_below and severe_floor is not None:
                tolerance_facts["treatments_below_severe_floor"] = sessions_severely_below
                tolerance_facts["severe_floor"] = severe_floor
            if sessions_with_post_reading:
                note += (
                    f"; of the {sessions_with_post_reading} with an "
                    f"end-of-treatment reading, {sessions_ended_below_floor} "
                    f"were still below when the treatment finished")
                if lowest_post is not None:
                    note += f" (lowest {round(float(lowest_post))})"
            critical.append(Finding(
                kind="intradialytic_hypotension_burden", domain="dialysis",
                # HARM: these treatments already ended with the patient
                # hypotensive. It is the most dangerous thing on the card
                # and it used to be printed BELOW a 26-day-old reading.
                severity=HARM,
                facts=tolerance_facts, fallback=note + ".",
                # The lowest value and the count below the CRITICAL bound are
                # findings in their own right, not colour. Left optional, the
                # model reported "35 of 37 treatments ... 95% of sessions" and
                # dropped both the 39 and the 16 — §3am's whole point is that
                # the nadir is the finding.
                essential=("treatments_below_floor",
                           "treatments_with_a_reading", "floor",
                           "lowest", "treatments_below_severe_floor")))

    # ── An ordered dry weight the rest of the record disagrees with ──────
    dw_finding = _dry_weight_disagreement(dry_weights, window_days)
    if dw_finding is not None:
        finding, dw_detail = dw_finding
        detail["dry_weight"] = dw_detail
        critical.append(finding)

    if not parts:
        return Component("dialysis", None, DEFAULT_WEIGHTS["dialysis"],
                         {"reason": "no treatment history to measure", **detail})
    total_w = sum(w for _, w in parts)
    return Component("dialysis", round(sum(s * w for s, w in parts) / total_w, 1),
                     DEFAULT_WEIGHTS["dialysis"], detail, critical)


def symptom_component(symptoms: list[dict[str, Any]],
                      today: date | None = None) -> Component:
    """What the patient says is wrong with them, and WHEN they said it.

    `severity` is already a patient-reported 0-10 scale, so ×10 is a unit
    conversion onto this score's range rather than a threshold invented here.

    **The WORST symptom decides it, not the mean.** Averaging a 9/10 abdominal
    pain with a 2/10 ache reports 5.5, which describes neither and reads as
    moderate. A patient in severe pain is not partly well.

    ⚠️ **…but the worst over 90 DAYS is not the worst NOW, and this took the
    former.** Operator, 2026-10-22: *"'twisted abdominal pain' from 40 days
    ago is irrelevant now."* Measured on the record that prompted it:

        2026-07-28   86 days ago   twisted abdominal pain       9/10
        2026-10-09   13 days ago   stomach cramps … twisting    6/10

    `max(severity)` over the window returned the 86-day-old 9/10 and the card
    reported it as the patient's current symptom burden, while the recent 6/10
    — plausibly the same complaint, still going — was never mentioned. The
    caller did not even pass a date, so this function could not have known
    (§3an: "windows, not lifetimes", and a 90-day window with no recency
    weighting is a lifetime in miniature).

    A LOGGED SYMPTOM IS AN EVENT, NOT A STANDING STATE. A lab value persists
    until re-measured; "I had severe pain on 28 July" says nothing about
    today. So the score describes the recent window, and anything older is
    reported as history WITH ITS DATE rather than as the present.

    `STALE_DAYS` is the recency bound the system already defines
    (`dialysis_day_adjustment`, 14/30). The 30-day edge is used here, not the
    14-day one: 14 is "fresh enough to treat as current" for a monthly lab
    cadence, and 30 is the point past which a value is no longer current at
    all — which is the question being asked of a symptom. No second window is
    invented for this (§3an says explicitly not to).
    """
    reference = today or date.today()

    def _age(entry) -> int | None:
        when = entry.get("log_date")
        if when is None:
            return None
        if hasattr(when, "date") and not isinstance(when, date):
            when = when.date()
        try:
            return (reference - when).days
        except TypeError:
            return None

    rated = [s for s in symptoms or [] if s.get("severity") is not None]
    if not symptoms:
        return Component("symptoms", None, DEFAULT_WEIGHTS["symptoms"],
                         {"reason": "no symptoms logged in this window"})
    if not rated:
        return Component("symptoms", None, DEFAULT_WEIGHTS["symptoms"],
                         {"reason": f"{len(symptoms)} symptoms logged, none rated",
                          "logged": len(symptoms)})

    # An undated entry is treated as current rather than discarded: the date
    # is missing from OUR payload, which is not evidence about the patient.
    current = [s for s in rated
               if (_age(s) is None or _age(s) <= STALE_DAYS)]
    older = [s for s in rated if s not in current]

    if not current:
        # Everything on file is history. Saying "9/10" here would assert a
        # present-tense fact nobody recorded; saying nothing would hide that
        # symptoms exist. Report the gap and name the newest (§3aa).
        newest = min((a for a in (_age(s) for s in older) if a is not None),
                     default=None)
        return Component(
            "symptoms", None, DEFAULT_WEIGHTS["symptoms"],
            {"reason": (f"no symptom logged in the last {STALE_DAYS} days"
                        + (f"; the most recent was {newest} days ago"
                           if newest is not None else "")),
             "logged_older": len(older)})

    worst = max(current, key=lambda s: float(s["severity"]))
    severity = float(worst["severity"])
    score = max(0.0, 100.0 - severity * 10.0)
    worst_age = _age(worst)

    critical: list[str] = []
    # A symptom the patient rated in the top third of their own scale, or one
    # they said stops them functioning, is a finding rather than a data point.
    if severity >= 7 or worst.get("affects_function"):
        symptom_facts = {
            "measure": "worst symptom reported",
            "symptom": worst.get("symptom_name") or "unnamed symptom",
            "severity": severity, "severity_scale_max": 10,
        }
        if worst.get("affects_function"):
            symptom_facts["affects_daily_function"] = True
        # The DATE travels with it. A severity with no date is what let an
        # 86-day-old 9/10 read as the present tense.
        if worst_age is not None:
            symptom_facts["days_ago"] = worst_age
        if worst.get("log_date") is not None:
            symptom_facts["logged_on"] = str(worst["log_date"])
        critical.append(Finding(
            kind="severe_symptom", domain="symptoms", facts=symptom_facts,
            # HARM: the patient is in pain, in their own words — and only
            # entries inside the recent window reach here at all.
            severity=HARM,
            essential=("severity",),
            fallback=(f"{worst.get('symptom_name') or 'A symptom'} rated "
                      f"{severity:g}/10"
                      + (f", logged {worst_age} days ago"
                         if worst_age is not None else "")
                      + (" and reported as affecting daily function"
                         if worst.get("affects_function") else "")
                      + ".")))

    return Component("symptoms", round(score, 1), DEFAULT_WEIGHTS["symptoms"],
                     {"logged": len(symptoms),
                      "rated": len(rated),
                      "worst": worst.get("symptom_name"),
                      "worst_severity": severity},
                     critical)


def elimination_component(*, bowel_blood: int, bowel_total: int,
                          vomit_in_window: int, window_days: int,
                          vomit_baseline_per_week: float | None = None,
                          last_blood_on=None,
                          today: date | None = None,
                          ) -> Component:
    """Blood, and how often the patient is being sick.

    **Blood is read from the column OR from what the row says.** Five writers
    fill `bowel_movements` and two of them — the Firestore import paths — insert
    only `(user_id, log_date, log_time, notes)`, so everything they migrate
    arrives as prose with the boolean NULL. On the reference record that is
    **134 of 648 rows reading "Bloody" with `blood_present` empty on every
    one**, which every consumer that checks the flag alone scores as no blood
    at all. `services/elimination_text.blood_in_row` is the shared reader;
    the caller applies it, so this function receives a count that already
    reflects both sources.

    Blood in stool is not graded — any is a finding. The score falls with how
    much of the record carries it, and the finding is stated outright whatever
    the score says.
    """
    detail: dict[str, Any] = {"window_days": window_days}
    critical: list[str] = []
    parts: list[tuple[float, float]] = []

    if bowel_total:
        fraction = bowel_blood / bowel_total
        detail["bowel_total"] = bowel_total
        detail["bowel_with_blood"] = bowel_blood
        detail["bowel_blood_pct"] = round(fraction * 100, 1)

        # **Any blood is abnormal.** That is definitional rather than a cutoff
        # chosen here, so the curve has to express it: falling linearly from
        # zero scored 7 bloody stools in 102 as **95.2**, which reads as a well
        # patient and is the opposite of what the finding means.
        #
        # So presence decides the band and frequency decides the position
        # inside it: no blood at all is 100, and any blood starts at 50 and
        # falls with how much of the record carries it. The proportion still
        # separates one episode from fifty — a patient bleeding once is not the
        # same as one bleeding daily — but neither reads as healthy.
        if bowel_blood:
            bowel_score = max(0.0, 50.0 - fraction * 50.0)
            # ── WHEN WAS THE LAST ONE ────────────────────────────────────
            #
            # Operator, 2026-10-22: *"critical findings must be prescient not
            # stale, unless they are perenial/chronic."* A count over 90 days
            # cannot tell bleeding that stopped in August from bleeding last
            # week — both render as "blood recorded in 7 of 97". This
            # component was handed counts ALONE and so could not have said,
            # the same structural blindness that let an 86-day-old pain read
            # as current.
            #
            # Recurring blood IS the chronic case the operator exempts, and
            # that is judged by the MOST RECENT episode: still bleeding is
            # chronic and current; bleeding that stopped is history. The
            # score is unchanged either way — a bleed inside the window
            # happened, whenever it was.
            blood_age = None
            if last_blood_on is not None:
                reference = today or date.today()
                when = last_blood_on
                if hasattr(when, "date") and not isinstance(when, date):
                    when = when.date()
                try:
                    blood_age = (reference - when).days
                except TypeError:
                    blood_age = None
            if blood_age is not None:
                detail["days_since_blood"] = blood_age
                detail["last_blood_on"] = str(last_blood_on)
            facts = {"measure": "bowel movements with blood recorded",
                     "with_blood": bowel_blood, "total": bowel_total,
                     "percent": round(fraction * 100),
                     "window_days": window_days}
            if blood_age is not None:
                facts["days_since_most_recent"] = blood_age
                facts["most_recent_on"] = str(last_blood_on)
            critical.append(Finding(
                kind="blood_in_stool", domain="elimination",
                # HARM while it is still happening. Blood whose most recent
                # episode is beyond the recency bound is reported, and not as
                # something occurring now.
                severity=(CONTEXT if (blood_age is not None
                                      and blood_age > STALE_DAYS) else HARM),
                facts=facts,
                essential=("with_blood", "total"),
                fallback=(f"Blood recorded in {bowel_blood} of {bowel_total} "
                          f"bowel movements ({fraction * 100:.0f}%) over the "
                          f"last {window_days} days"
                          + (f", most recently {blood_age} days ago"
                             if blood_age is not None else "") + ".")))
        else:
            bowel_score = 100.0
        parts.append((bowel_score, 0.7))

    weeks = max(window_days / 7.0, 1e-6)
    rate = vomit_in_window / weeks
    if vomit_in_window or vomit_baseline_per_week:
        detail["vomiting_in_window"] = vomit_in_window
        detail["vomiting_per_week"] = round(rate, 2)
        if vomit_baseline_per_week and vomit_baseline_per_week > 0:
            detail["vomiting_baseline_per_week"] = round(vomit_baseline_per_week, 2)
            # Judged against their own long-run rate: there is no published
            # episodes-per-week band, and inventing one here is what §0 forbids.
            # A rise above their own established pattern is observable.
            ratio = rate / vomit_baseline_per_week
            parts.append((max(0.0, 100.0 - max(0.0, ratio - 1.0) * 100.0), 0.3))
            if ratio > 1.5:
                critical.append(Finding(
                    kind="vomiting_above_baseline", domain="elimination",
                    severity=DEVIATION,   # against their own usual rate
                    facts={"measure": "vomiting episodes",
                           "per_week": round(rate, 1),
                           "usual_per_week": round(vomit_baseline_per_week, 1)},
                    fallback=(f"Vomiting {rate:.1f} times a week against their "
                              f"usual {vomit_baseline_per_week:.1f}.")))

    if not parts:
        return Component("elimination", None, DEFAULT_WEIGHTS["elimination"],
                         {"reason": "nothing logged in this window", **detail})
    total_w = sum(w for _, w in parts)
    return Component("elimination", round(sum(s * w for s, w in parts) / total_w, 1),
                     DEFAULT_WEIGHTS["elimination"], detail, critical)


def grade_for(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"
