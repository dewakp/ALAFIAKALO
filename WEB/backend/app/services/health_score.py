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
DEFAULT_WEIGHTS: dict[str, float] = {
    "nutrition": 0.25,
    "medication_adherence": 0.20,
    "vitals": 0.15,
    "sleep": 0.15,
    "mood": 0.13,
    "fitness": 0.12,
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


def vitals_component(*, bmi: float | None = None,
                     systolic: float | None = None,
                     diastolic: float | None = None,
                     on_dialysis: bool = False) -> Component:
    """Blood pressure first; BMI only where it means something.

    On dialysis, weight swings with fluid between sessions, so a BMI taken from
    it is not a body-composition measure. It is dropped rather than dressed up.
    """
    parts: list[tuple[float, float]] = []
    detail: dict[str, Any] = {}

    if systolic is not None and diastolic is not None:
        if systolic < 130 and diastolic < 80:
            bp_score = 100.0
        elif systolic < 140 and diastolic < 90:
            bp_score = 75.0
        elif systolic < 160 and diastolic < 100:
            bp_score = 50.0
        else:
            bp_score = 25.0
        parts.append((bp_score, 0.7 if not on_dialysis else 1.0))
        detail["blood_pressure"] = f"{round(systolic)}/{round(diastolic)}"

    if bmi is not None and not on_dialysis:
        if 18.5 <= bmi < 25:
            bmi_score = 100.0
        elif 25 <= bmi < 30 or 17 <= bmi < 18.5:
            bmi_score = 75.0
        else:
            bmi_score = 50.0
        parts.append((bmi_score, 0.3))
        detail["bmi"] = round(bmi, 1)
    elif bmi is not None:
        detail["bmi_excluded"] = (
            "BMI is not scored on dialysis — weight varies with fluid between sessions")

    if not parts:
        return Component("vitals", None, DEFAULT_WEIGHTS["vitals"],
                         {"reason": "no blood pressure recorded", **detail})
    total_w = sum(w for _, w in parts)
    return Component("vitals", round(sum(s * w for s, w in parts) / total_w, 1),
                     DEFAULT_WEIGHTS["vitals"], detail)


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
    overall = sum(c.score * c.weight for c in scored) / total_w
    # How much of the intended picture was actually available.
    confidence = total_w / sum(c.weight for c in components)

    return {
        "overall_score": round(overall, 1),
        "grade": grade_for(overall),
        "component_scores": {c.key: c.score for c in components},
        "components_scored": [c.key for c in scored],
        "components_unknown": unknown,
        "confidence": round(confidence, 2),
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
