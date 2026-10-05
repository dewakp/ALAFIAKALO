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
from typing import Any


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
    #: Findings that are dangerous on their own terms, each a finished sentence
    #: naming the value and what it was judged against. A score is a summary and
    #: a summary can be read past; "25 of 37 treatments ended below 90 mmHg"
    #: cannot. These travel beside the number so the number is never the whole
    #: message — the same reason `nutrition` names its shortfalls.
    critical: list[str] = field(default_factory=list)


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
                     post_dialysis_systolics: list[float] | None = None,
                     on_dialysis: bool = False) -> Component:
    """Blood pressure, pulse, and what the treatment itself did to them.

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
        if systolic < sys_band[1]:
            critical.append(
                f"Resting systolic {round(float(systolic))} mmHg is below the "
                f"{sys_band[1]:g}-{sys_band[2]:g} mmHg reference band.")
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
            critical.append(
                f"Resting pulse {round(float(heart_rate))} bpm is above the "
                f"{hr_band[1]:g}-{hr_band[2]:g} bpm reference band.")

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
        if below:
            critical.append(
                f"{len(below)} of {len(readings)} treatments ended below "
                f"{floor:g} mmHg systolic (lowest {round(nadir)}).")

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
    critical = [line for c in scored for line in (c.critical or [])]

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


def dialysis_component(*, sessions_in_window: int,
                       window_days: int,
                       baseline_per_week: float | None,
                       latest_ktv: float | None = None,
                       ktv_band: tuple[float | None, float, float, float | None] | None = None,
                       ) -> Component:
    """Is the treatment happening, and is it clearing enough?

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
        parts.append((ratio * 100.0, 0.5))
        if ratio < 0.8:
            missed = (baseline_per_week - rate) * weeks
            critical.append(
                f"Treatment has fallen to {rate:.1f} sessions a week against "
                f"their usual {baseline_per_week:.1f} — about {missed:.0f} "
                f"fewer than expected over {window_days} days.")
    else:
        detail["baseline"] = ("no established treatment rate yet, so attendance "
                              "is not scored")

    if latest_ktv is not None and ktv_band:
        parts.append((band_score(latest_ktv, ktv_band), 0.5))
        detail["ktv"] = round(float(latest_ktv), 2)
        detail["ktv_target"] = ktv_band[1]
        if latest_ktv < ktv_band[1]:
            critical.append(
                f"Delivered Kt/V {latest_ktv:.2f} is below the {ktv_band[1]:g} "
                "adequacy target.")

    if not parts:
        return Component("dialysis", None, DEFAULT_WEIGHTS["dialysis"],
                         {"reason": "no treatment history to measure", **detail})
    total_w = sum(w for _, w in parts)
    return Component("dialysis", round(sum(s * w for s, w in parts) / total_w, 1),
                     DEFAULT_WEIGHTS["dialysis"], detail, critical)


def symptom_component(symptoms: list[dict[str, Any]]) -> Component:
    """What the patient says is wrong with them.

    `severity` is already a patient-reported 0-10 scale, so ×10 is a unit
    conversion onto this score's range rather than a threshold invented here.

    **The WORST symptom decides it, not the mean.** Averaging a 9/10 abdominal
    pain with a 2/10 ache reports 5.5, which describes neither and reads as
    moderate. A patient in severe pain is not partly well.
    """
    rated = [s for s in symptoms or [] if s.get("severity") is not None]
    if not symptoms:
        return Component("symptoms", None, DEFAULT_WEIGHTS["symptoms"],
                         {"reason": "no symptoms logged in this window"})
    if not rated:
        return Component("symptoms", None, DEFAULT_WEIGHTS["symptoms"],
                         {"reason": f"{len(symptoms)} symptoms logged, none rated",
                          "logged": len(symptoms)})

    worst = max(rated, key=lambda s: float(s["severity"]))
    severity = float(worst["severity"])
    score = max(0.0, 100.0 - severity * 10.0)

    critical: list[str] = []
    # A symptom the patient rated in the top third of their own scale, or one
    # they said stops them functioning, is a finding rather than a data point.
    if severity >= 7 or worst.get("affects_function"):
        critical.append(
            f"{worst.get('symptom_name') or 'A symptom'} rated "
            f"{severity:g}/10"
            + (" and reported as affecting daily function" if worst.get("affects_function") else "")
            + ".")

    return Component("symptoms", round(score, 1), DEFAULT_WEIGHTS["symptoms"],
                     {"logged": len(symptoms),
                      "rated": len(rated),
                      "worst": worst.get("symptom_name"),
                      "worst_severity": severity},
                     critical)


def elimination_component(*, bowel_blood: int, bowel_total: int,
                          vomit_in_window: int, window_days: int,
                          vomit_baseline_per_week: float | None = None,
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
            critical.append(
                f"Blood recorded in {bowel_blood} of {bowel_total} bowel "
                f"movements ({fraction * 100:.0f}%).")
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
                critical.append(
                    f"Vomiting {rate:.1f} times a week against their usual "
                    f"{vomit_baseline_per_week:.1f}.")

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
