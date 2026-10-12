# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

import logging
"""Wellness endpoints — score, trends, daily recs, health improvements."""

import json
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Header, Query

from app.core.patient_time import TIMEZONE_HEADER, patient_today
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, or_, select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.labs import LabResult
from app.models.chronic_conditions import TherapySession, IntradialyticReading
from app.models.nutrition import NutritionLog
from app.models.fitness import FitnessLog
from app.models.mood import MoodEntry
from app.models.sleep import SleepLog
from app.models.vitals import VitalsLog
from app.models.medications import Medication
from app.models.wellness import WellnessScore as WellnessScoreModel
from app.schemas.wellness import (
    WellnessScoreResponse, HealthTrendResponse, TrendStream, TrendDataPoint,
    DailyRecommendationsResponse, RecommendationItem, HealthImprovementsResponse,
    HEBCSScoreResponse, WhatIfRequest, WhatIfResponse, WhatIfPathwayDelta,
)
from app.services.health_signals import (
    collect_signals,
    signal_domain,
    signal_label,
)
from app.services.hebcs_engine import compute_hebcs
from app.services.prompt_language import (
    LANGUAGE_HEADER,
    language_name,
    patient_language,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _compute_wellness_score(user_id: int, db: AsyncSession,
                                  language: str | None = None) -> dict:
    """Wellness score from measured values, not from how often the user logged.

    What this replaces, component by component — every one of them counted
    attendance and none of them looked at a value:

        nutrition            min(100, entry_count * 3.3)   30 entries = 100%
        fitness              min(100, workout_count * 8.3)
        vitals               min(100, vitals_count * 10)   no reading was read
        medication_adherence 80 if any active med row else 50
        sleep / mood         defaulted to 50 when absent

    …then averaged flat, so an account with no data landed near 50 whatever the
    patient's actual condition — which is exactly how a score of 50 appeared
    beside a page full of bad signs. Worse, the explanation said "Great
    nutrition tracking consistency", naming what it really measured while being
    presented as health.

    Now: intake scored against this patient's own goals, blood pressure read as
    a value, adherence measured against the prescription, and anything with no
    data reported as UNKNOWN rather than defaulted. `overall_score` is None when
    nothing at all was measured.
    """
    from app.services import health_score as hs
    from app.services import clinical_sources as sources
    from app.services.nutrient_goals_service import compute_goals
    from app.models.user import User as UserModel

    today = date.today()
    cutoff = today - timedelta(days=30)

    user = (await db.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one_or_none()

    # ── This patient's goals decide WHICH nutrients are worth averaging ───
    conditions = list(await sources.conditions(db, user_id, active_only=True))
    from app.services.nutrient_quota_service import quotas_for_conditions
    _quota_set = await quotas_for_conditions(
        db, conditions,
        weight_kg=user.current_weight_kg if user else None,
        sex=user.gender if user else None,
        date_of_birth=user.date_of_birth if user else None,
    )
    _goals_preview = compute_goals(
        date_of_birth=str(user.date_of_birth) if user and user.date_of_birth else None,
        sex=user.gender if user else None,
        height_cm=user.height_cm if user else None,
        current_weight_kg=user.current_weight_kg if user else None,
        target_weight_kg=user.target_weight_kg if user else None,
        activity_level=user.activity_level if user else None,
        conditions=conditions,
        quotas=_quota_set.as_goal_overrides(),
    )

    # ── Nutrition: mean daily intake vs this patient's own goals ──────────
    # Which nutrients to average is decided by the GOALS, not by a list typed
    # here: whatever `compute_goals` produces for this patient is what gets
    # scored, so adding a goal needs no second edit. Goal keys are already the
    # column names.
    goal_keys = [str(g.get("key") or "") for g in (_goals_preview.get("goals") or [])]
    nutrient_cols = {
        key: getattr(NutritionLog, key)
        for key in goal_keys
        if key and hasattr(NutritionLog, key)
    }
    intake: dict[str, float | None] = {}
    for key, col in nutrient_cols.items():
        # Per-day totals first, then the mean over days that HAVE data — a
        # patient who logs twice a week must not read as eating a seventh of
        # their potassium.
        daily = (await db.execute(
            select(func.sum(col)).where(
                NutritionLog.user_id == user_id,
                NutritionLog.log_date >= cutoff,
                col.isnot(None),
            ).group_by(NutritionLog.log_date)
        )).scalars().all()
        vals = [float(v) for v in daily if v is not None]
        intake[key] = sum(vals) / len(vals) if vals else None

    goals_payload = _goals_preview
    on_dialysis = any(
        "dialysis" in (getattr(c, "name", "") or "").lower()
        or "renal" in (getattr(c, "name", "") or "").lower()
        or str(getattr(c, "icd11_code", "") or "").upper().startswith("GB6")
        for c in conditions
    )

    # ── Fitness ──────────────────────────────────────────────────────────
    fit_count = (await db.execute(
        select(func.count(FitnessLog.id)).where(
            FitnessLog.user_id == user_id, FitnessLog.log_date >= cutoff)
    )).scalar() or 0
    any_fitness = (await db.execute(
        select(func.count(FitnessLog.id)).where(FitnessLog.user_id == user_id)
    )).scalar() or 0
    # No activity EVER is unknown; none in the window on an active logger is a
    # real zero.
    workouts_per_week = (fit_count / (30 / 7)) if any_fitness else None

    # ── Sleep ────────────────────────────────────────────────────────────
    sleep_row = (await db.execute(
        select(func.avg(SleepLog.total_hours), func.avg(SleepLog.quality_score))
        .where(SleepLog.user_id == user_id, SleepLog.sleep_date >= cutoff)
    )).first()
    avg_sleep = float(sleep_row[0]) if sleep_row and sleep_row[0] is not None else None
    avg_quality = float(sleep_row[1]) if sleep_row and sleep_row[1] is not None else None

    # ── Mood ─────────────────────────────────────────────────────────────
    mood_row = (await db.execute(
        select(func.avg(MoodEntry.mood_score), func.avg(MoodEntry.energy_level),
               func.avg(MoodEntry.stress_level))
        .where(MoodEntry.user_id == user_id, MoodEntry.entry_date >= cutoff)
    )).first()
    avg_mood = float(mood_row[0]) if mood_row and mood_row[0] is not None else None
    avg_energy = float(mood_row[1]) if mood_row and mood_row[1] is not None else None
    avg_stress = float(mood_row[2]) if mood_row and mood_row[2] is not None else None

    # ── Vitals: a WINDOW of self-recorded readings, not the newest row ───
    #
    # This took `.order_by(log_date.desc()).limit(1)` — ONE row — and the whole
    # self-recorded half of the vitals domain was scored on it. Asked "81 mmHg?
    # how?", the answer was: the single most recent `vitals_logs` row,
    # 2026-09-26 07:00, 81/62, noted "Just woke up after an 8 hr sleep" — a
    # real reading, FIFTEEN DAYS OLD, presented with no date as though it were
    # today's, and labelled "Resting" when the row before it reads "Just after
    # poop" and nothing records posture at all.
    #
    # §3an already settles both halves of this: "Windows, not lifetimes" (an
    # all-time mean is not an observation — and n=1 is the same error from the
    # other end: this patient's 43 readings average 97, so one reading of 81
    # is the low end of their own distribution stated as their blood pressure),
    # and "Lab recency is ALREADY DEFINED — do not invent a second window",
    # which is why the staleness bound below is `dialysis_day_adjustment`'s
    # FRESH_DAYS/STALE_DAYS rather than a number chosen here.
    # The 30-day window (`cutoff`) — one of §3an's stated windows, kept rather
    # than widened. On this record it holds TWO readings, which is exactly why
    # the count travels with the figure instead of being hidden behind it.
    vitals_rows = (await db.execute(
        select(VitalsLog).where(
            VitalsLog.user_id == user_id, VitalsLog.log_date >= cutoff)
        .order_by(VitalsLog.log_date.desc())
    )).scalars().all()
    vitals = vitals_rows[0] if vitals_rows else None
    self_recorded = {
        "systolic": [r.blood_pressure_systolic for r in vitals_rows
                     if r.blood_pressure_systolic is not None],
        "diastolic": [r.blood_pressure_diastolic for r in vitals_rows
                      if r.blood_pressure_diastolic is not None],
        "heart_rate": [r.heart_rate_bpm for r in vitals_rows
                       if r.heart_rate_bpm is not None],
        "latest_on": vitals.log_date if vitals else None,
        "age_days": (today - vitals.log_date).days if vitals else None,
    }

    # When was the pressure last measured BY ANY MEANS?
    #
    # Without this the staleness note said "the most recent was 15 days ago
    # (2026-09-26)" — true of `vitals_logs` and FALSE of the patient's blood
    # pressure, which was measured on 2026-10-09. The same card then said "35
    # of 37 treatments dropped below 90 mmHg systolic during dialysis", so it
    # contradicted itself two sentences apart. §3aa: reading one source and
    # speaking as though it were the whole is the fault this canon exists for,
    # and here it reached a sentence telling a patient their pressure had not
    # been checked in a fortnight.
    _last_treatment_bp = (await db.execute(
        select(func.max(func.date(TherapySession.scheduled_date)))
        .where(TherapySession.user_id == user_id)
        .where(or_(TherapySession.pre_systolic_bp.isnot(None),
                   TherapySession.post_systolic_bp.isnot(None),
                   TherapySession.id.in_(
                       select(IntradialyticReading.session_id)
                       .where(IntradialyticReading.systolic_bp.isnot(None)))))
    )).scalar()

    # ── Medication adherence vs the prescription ─────────────────────────
    # Through clinical_sources, never the models directly: prescribed and taken
    # live in different tables and reading one alone is how a physician saw two
    # drugs stopped in 2017 beside 921 dose logs (canon 3aa).
    prescribed = [m.name for m in
                  await sources.medications_prescribed(db, user_id, active_only=True)]
    logged = [m.name for m in await sources.medications_taken(db, user_id, since=cutoff)]

    # ── The bands every vital is judged against ──────────────────────────
    # From `clinical_thresholds`, each row carrying the guideline it came from.
    # An input with no band goes UNSCORED: the reason this component scored a
    # dialysis patient's 81/62 as 100 was a band written into the source.
    from app.models.conditions import SymptomLog
    from app.models.elimination import BowelMovement, VomitingLog
    from app.services import elimination_text
    from app.services import reference_ranges as refs

    bands = await refs.bands(db)

    # A treatment-based window: 30 days is three or four sessions, too few to
    # say anything about either attendance or how treatments are ending.
    cutoff_90 = today - timedelta(days=90)
    cutoff_365 = today - timedelta(days=365)

    # ── How OFTEN a treatment runs the pressure down ─────────────────────
    #
    # Per SESSION, because the burden is the finding: on this record 30 of 38
    # treatments in 90 days had a nadir below the floor (79%) and 14 below the
    # critical bound (37%), while the dialysis score read 94 on attendance
    # alone. Operator: "still measuring frequency of log".
    #
    # The nadir of a session is the lowest of its intradialytic readings AND
    # its post-treatment pressure — §3am, the nadir is the finding and a mean
    # hides it. Both thresholds come from the `Post-Dialysis Systolic BP` band
    # (`opt_low` and `crit_low`), the same band `vitals_component` reads.
    _post_band = bands.get("Post-Dialysis Systolic BP")
    tolerance: dict = {
        "sessions_with_pressure": 0, "below_floor": 0, "severely_below": 0,
        "lowest_nadir": None,
        "floor": _post_band[1] if _post_band else None,
        "severe_floor": _post_band[0] if _post_band else None,
    }
    if _post_band:
        _nadirs = (await db.execute(
            select(
                TherapySession.id,
                func.least(
                    func.min(IntradialyticReading.systolic_bp),
                    func.min(TherapySession.post_systolic_bp),
                ).label("nadir"),
            )
            .outerjoin(IntradialyticReading,
                       IntradialyticReading.session_id == TherapySession.id)
            .where(TherapySession.user_id == user_id,
                   TherapySession.scheduled_date >= cutoff_90)
            .group_by(TherapySession.id)
        )).all()
        _vals = [float(n) for _, n in _nadirs if n is not None]
        if _vals:
            tolerance["sessions_with_pressure"] = len(_vals)
            tolerance["below_floor"] = sum(1 for v in _vals if v < _post_band[1])
            tolerance["lowest_nadir"] = min(_vals)
            if _post_band[0] is not None:
                tolerance["severely_below"] = sum(
                    1 for v in _vals if v < _post_band[0])

    # ── What the treatment did to the pressure ───────────────────────────
    post_systolics = [
        float(v) for v in (await db.execute(
            select(TherapySession.post_systolic_bp).where(
                TherapySession.user_id == user_id,
                TherapySession.scheduled_date >= cutoff_90,
                TherapySession.post_systolic_bp.isnot(None))
        )).scalars().all() if v is not None
    ]

    # ── Attendance, against this patient's OWN established rate ──────────
    sessions_90 = (await db.execute(
        select(func.count(TherapySession.id)).where(
            TherapySession.user_id == user_id,
            TherapySession.scheduled_date >= cutoff_90)
    )).scalar() or 0
    sessions_365 = (await db.execute(
        select(func.count(TherapySession.id)).where(
            TherapySession.user_id == user_id,
            TherapySession.scheduled_date >= cutoff_365)
    )).scalar() or 0
    baseline_per_week = (sessions_365 / (365 / 7.0)) if sessions_365 else None

    # Delivered Kt/V — the measured one. `KT/V PRESCRIBED` is deliberately not
    # matched (canon §3ac: the prescription is not what the patient received).
    ktv_row = (await db.execute(
        select(LabResult.value).where(
            LabResult.user_id == user_id,
            LabResult.value.isnot(None),
            func.lower(LabResult.test_name).in_(("spkt/v", "kt/v", "ktv")))
        .order_by(LabResult.test_date.desc()).limit(1)
    )).scalar_one_or_none()

    # ── Symptoms ─────────────────────────────────────────────────────────
    symptom_rows = (await db.execute(
        select(SymptomLog).where(
            SymptomLog.user_id == user_id, SymptomLog.log_date >= cutoff_90)
    )).scalars().all()
    symptoms = [{"symptom_name": s.symptom_name, "severity": s.severity,
                 "affects_function": s.affects_function} for s in symptom_rows]

    # ── Elimination: the column OR what the row says ─────────────────────
    # Two of the five writers of `bowel_movements` insert only
    # (user_id, log_date, log_time, notes), so everything they migrate arrives
    # as prose with the boolean NULL — 134 of 648 rows here read "Bloody" with
    # `blood_present` empty on every one. Reading the flag alone scores that as
    # no blood at all.
    bowel_rows = (await db.execute(
        select(BowelMovement.blood_present, BowelMovement.notes).where(
            BowelMovement.user_id == user_id, BowelMovement.log_date >= cutoff_90)
    )).all()
    bowel_blood = sum(
        1 for flag, notes in bowel_rows
        if elimination_text.blood_in_row(flag=flag, notes=notes))

    vomit_90 = (await db.execute(
        select(func.count(VomitingLog.id)).where(
            VomitingLog.user_id == user_id, VomitingLog.log_date >= cutoff_90)
    )).scalar() or 0
    vomit_365 = (await db.execute(
        select(func.count(VomitingLog.id)).where(
            VomitingLog.user_id == user_id, VomitingLog.log_date >= cutoff_365)
    )).scalar() or 0

    components = [
        hs.nutrition_adherence(intake, goals_payload.get("goals") or []),
        hs.medication_adherence(list(prescribed), list(logged)),
        hs.vitals_component(
            bands=bands,
            bmi=getattr(vitals, "bmi", None) if vitals else None,
            systolic=hs.median(self_recorded["systolic"]),
            diastolic=hs.median(self_recorded["diastolic"]),
            heart_rate=hs.median(self_recorded["heart_rate"]),
            # So the finding can SAY how many readings and how old, instead of
            # stating one number as if it were taken this morning.
            sample_size=len(self_recorded["systolic"]),
            latest_on=self_recorded["latest_on"],
            age_days=self_recorded["age_days"],
            pressure_measured_on=_last_treatment_bp,
            post_dialysis_systolics=post_systolics,
            on_dialysis=on_dialysis,
        ),
        hs.dialysis_component(
            sessions_in_window=sessions_90, window_days=90,
            baseline_per_week=baseline_per_week,
            latest_ktv=float(ktv_row) if ktv_row is not None else None,
            ktv_band=bands.get("KtV (Dialysis Adequacy)"),
            sessions_with_pressure=tolerance["sessions_with_pressure"],
            sessions_below_floor=tolerance["below_floor"],
            sessions_severely_below=tolerance["severely_below"],
            lowest_nadir=tolerance["lowest_nadir"],
            hypotension_floor=tolerance["floor"],
            severe_floor=tolerance["severe_floor"],
        ) if (sessions_365 or on_dialysis) else hs.Component(
            "dialysis", None, hs.DEFAULT_WEIGHTS["dialysis"],
            {"reason": "not on dialysis"}),
        hs.symptom_component(symptoms),
        hs.elimination_component(
            bowel_blood=bowel_blood, bowel_total=len(bowel_rows),
            vomit_in_window=vomit_90, window_days=90,
            vomit_baseline_per_week=(vomit_365 / (365 / 7.0)) if vomit_365 else None,
        ),
        hs.sleep_component(avg_hours=avg_sleep, avg_quality=avg_quality),
        hs.mood_component(avg_mood=avg_mood, avg_energy=avg_energy, avg_stress=avg_stress),
        hs.fitness_component(workouts_per_week),
    ]
    result = hs.overall_score(components)
    by_key = result["component_scores"]

    # ── Explanation: say what was measured AND what was not ──────────────
    parts: list[str] = []
    nutrition_detail = result["detail"].get("nutrition") or {}
    shortfalls = nutrition_detail.get("shortfalls") or []
    if by_key.get("nutrition") is None:
        parts.append("No meals with nutrient data in the last 30 days, so "
                     "nutrition could not be assessed.")
    elif shortfalls:
        parts.append("Nutrition is short on " + ", ".join(shortfalls) + ".")
    else:
        parts.append("Intake is within your targets.")

    med_detail = result["detail"].get("medication_adherence") or {}
    if med_detail.get("not_logged"):
        parts.append("No doses logged for " + ", ".join(med_detail["not_logged"]) + ".")

    if result["components_unknown"]:
        parts.append("Not assessed for lack of data: "
                     + ", ".join(result["components_unknown"]) + ".")

    # A finding outranks the summary and is stated before it. "Blood recorded
    # in 134 of 648 bowel movements" must not sit below "Intake is within your
    # targets" — §3aa, applied to the order of sentences.
    # ALAFIA writes these; the backend decided WHAT they are. Verified against
    # the facts, so a number cannot be altered or dropped — see
    # `finding_text.render`. Falls back to the deterministic wording per
    # finding, so a model outage costs phrasing and never a finding.
    from app.services import finding_text
    findings = await finding_text.render(
        result.get("critical_findings") or [],
        language=language_name(language) if language else None)
    if findings:
        parts = list(findings) + parts

    return {
        "overall_score": result["overall_score"],
        "nutrition_score": by_key.get("nutrition"),
        "fitness_score": by_key.get("fitness"),
        "sleep_score": by_key.get("sleep"),
        "mood_score": by_key.get("mood"),
        "vitals_score": by_key.get("vitals"),
        "medication_adherence_score": by_key.get("medication_adherence"),
        "dialysis_score": by_key.get("dialysis"),
        "symptom_score": by_key.get("symptoms"),
        "elimination_score": by_key.get("elimination"),
        "confidence": result["confidence"],
        "components_unknown": result["components_unknown"],
        "critical_findings": findings,
        "detail": result["detail"],
        "explanation": " ".join(parts),
        "recommendations": json.dumps(parts),
    }


@router.get("/omega", response_model=HEBCSScoreResponse)
async def get_hebcs_omega_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """HEBCS Ω — Clinical biomarker wellness score using the published
    trapezoidal/pathway/geometric-mean framework (7-pathway ESRD model).

    Returns Ω ∈ (0, 1) with per-pathway and per-biomarker breakdown.
    """
    # Fetch each user's most recent lab value per test_name, WITH the range the
    # lab reported for it — there is no single optimal BUN, so the band has to
    # come from the report rather than from a number written into the engine.
    result = await db.execute(
        select(
            LabResult.test_name,
            LabResult.value,
            LabResult.test_date,
            LabResult.reference_range_low,
            LabResult.reference_range_high,
        )
        .where(LabResult.user_id == current_user.id, LabResult.value.isnot(None))
        .order_by(LabResult.test_name, LabResult.test_date.desc())
    )
    rows = result.all()

    # Keep only the most recent value per analyte
    biomarker_values: dict[str, float] = {}
    lab_ranges: dict[str, tuple[float | None, float | None]] = {}
    latest_date: date | None = None
    seen: set[str] = set()
    for test_name, value, test_date, ref_low, ref_high in rows:
        if test_name not in seen:
            biomarker_values[test_name] = value
            if ref_low is not None and ref_high is not None:
                lab_ranges[test_name] = (ref_low, ref_high)
            seen.add(test_name)
            if latest_date is None or test_date > latest_date:
                latest_date = test_date

    # nPCR carries 40% of the Nutritional pathway and this lab reports it as
    # N/A on every date, so the pathway has always scored on albumin and BUN
    # alone. It is computable from urea kinetics — see services/urea_kinetics.py
    # — and is passed in as DERIVED so it is scored without being counted as
    # measured.
    derived: dict[str, float] = {}
    try:
        from app.services import urea_kinetics as uk

        pre_bun = biomarker_values.get("BUN")
        post_bun = next((biomarker_values.get(k) for k in
                         ("BUN Post", "BUN-P", "BUN - Post")
                         if biomarker_values.get(k) is not None), None)

        # Kt/V and URR are CALCULATED, not looked up — a lab reports them only
        # when it chooses to, and this record has them on 6 of 12 dates. Both
        # come from the two BUN draws the lab does report, plus the session.
        # Validated against every date that has both inputs and a reported
        # value: 1.61/1.62, 1.34/1.35, 1.44/1.44, 0.90/0.90.
        if biomarker_values.get("spKt/V") is None:
            session = (await db.execute(
                select(TherapySession)
                # current_user.id, NOT a bare `user_id` — this route binds
                # `current_user` and there is no `user_id` in scope. The
                # NameError was swallowed by the `except Exception` below and
                # logged as "Could not derive urea kinetics", which reads like
                # missing data rather than a typo. Kt/V and URR were therefore
                # silently never derived on any date where the lab did not
                # report spKt/V — about half of them.
                .where(TherapySession.user_id == current_user.id,
                       TherapySession.duration_minutes.isnot(None))
                .order_by(TherapySession.scheduled_date.desc()).limit(1)
            )).scalar_one_or_none()
            if session is not None:
                # UF comes from the MACHINE minus saline returned, never from
                # pre-minus-post weight: that figure inherits every scale error
                # and averages -0.02 L across this record, against +0.87 L from
                # the readings. A post-dialysis weight of 0.3 kg in this data
                # produced a "60,900 ml removed".
                readings = (await db.execute(
                    select(IntradialyticReading)
                    .where(IntradialyticReading.session_id == session.id)
                    .order_by(IntradialyticReading.reading_number)
                )).scalars().all()
                uf_l = uk.net_ultrafiltration_litres(readings)
                if uf_l is None:
                    uf_l = session.total_uf_liters
                if uf_l is None and session.fluid_removed_ml is not None:
                    uf_l = session.fluid_removed_ml / 1000.0
                ktv = uk.single_pool_ktv(
                    pre_bun, post_bun, session.duration_minutes, uf_l,
                    session.post_dialysis_weight_kg)
                if ktv is not None:
                    derived["KtV (Dialysis Adequacy)"] = ktv.value

        if biomarker_values.get("URR") is None and biomarker_values.get("URR%") is None:
            urr = uk.urea_reduction_ratio(pre_bun, post_bun)
            if urr is not None:
                derived["URR (Urea Reduction Ratio)"] = urr.value

        # nPCR needs a Kt/V, computed or reported.
        npcr = uk.estimate_npcr(
            pre_bun,
            biomarker_values.get("spKt/V") or derived.get("KtV (Dialysis Adequacy)"))
        if npcr is not None:
            derived["nPCR (Protein Catabolic Rate)"] = npcr.value
    except Exception:  # noqa: BLE001 - a derivation must not break the score
        logger.warning("Could not derive urea kinetics", exc_info=True)

    # Ranges the labs actually reported — this patient's own first, then the
    # range most commonly reported for that analyte across the population.
    # Anything with neither keeps the framework's published band, and says so.
    from app.services import reference_ranges as refs
    resolved_ranges = await refs.resolve(db, current_user.id)
    resolved_ranges.update(lab_ranges)      # the latest row for this patient wins

    result_data = compute_hebcs(biomarker_values, derived_values=derived,
                                reference_ranges=resolved_ranges)
    omega = result_data["omega"]

    # ── What Ω is, said before what it is worth ──────────────────────────
    #
    # Ω scores BIOLOGICAL STATE from laboratory values. It carries no vital
    # sign, no treatment attendance, no symptom and no elimination finding, so
    # presenting it alone as a wellness verdict overstates what was looked at.
    #
    # And the old wording was the specific complaint: at 0.777 this read
    # "relatively well-managed health given your ESRD diagnosis" for a patient
    # whose glucose scored 0.000 and whose transferrin saturation scored 0.048.
    # A reassuring adjective in front of that is worse than no sentence.
    # `clinical_sources` is imported inside `_compute_wellness_score`, not at
    # module scope, so this function never had it — captured from the real call
    # as `NameError: name 'sources' is not defined` rather than reasoned about.
    # Conditions go through the canonical reader because they live in TWO
    # tables and reading one alone reports "no active conditions" for a patient
    # with four (§3aa).
    from app.services import clinical_sources as sources

    conditions_now = await sources.conditions(db, current_user.id, active_only=True)
    # Names are stripped for joining only. The stored wording is never
    # rewritten — one of these rows reads "G6PD Deficitency", and correcting a
    # patient's own clinical record to tidy a sentence invents a fact about
    # their chart (§3aj: the declared text is never rewritten).
    severe = [c.name.strip() for c in conditions_now
              if getattr(c, "is_severe", False) and c.name]
    others = [c.name.strip() for c in conditions_now
              if not getattr(c, "is_severe", False) and c.name]
    criticals = result_data.get("critical_biomarkers") or []

    if omega is None:
        interp = (
            "There are no lab results on file yet, so a wellness score cannot be "
            "calculated. This is not a score of zero — nothing has been measured."
        )
    else:
        interp = (f"Ω {omega:.3f} scores your most recent laboratory values "
                  "across seven pathways. It measures biological state only — "
                  "it does not include your blood pressure, your treatments, "
                  "your symptoms or anything you have logged.")

        # The burden is stated as a fact beside the score, never blended into
        # it. A number that mixed "managed well" with "has a terminal illness"
        # could answer neither question — and capping by diagnosis would erase
        # the difference between a well-controlled patient and a deteriorating
        # one, which is the distinction worth keeping.
        if severe:
            interp += (" You are living with " + ", ".join(severe)
                       + ", recorded as severe. A good score here describes how "
                         "well that is being managed, not its absence.")
        elif others:
            interp += " Recorded conditions: " + ", ".join(others) + "."

        if criticals:
            named = ", ".join(
                f"{b['name']} {b['value']:g}" for b in criticals[:3]
                if b.get("value") is not None)
            interp += (f" {len(criticals)} marker(s) sit at or below the bottom "
                       f"of their own reference band: {named}. A pathway score "
                       "is an average, so these do not show in it.")

    low_pathways = [] if omega is None else [
        name for name, pdata in result_data["pathways"].items()
        if pdata["score"] is not None and pdata["score"] < 0.5
    ]
    if low_pathways:
        interp += f" Lowest pathways: {', '.join(low_pathways)}."

    # Say what could NOT be assessed. A pathway with no biomarker drops out of
    # the geometric mean silently, so without this the score reads as a
    # whole-patient verdict when part of the patient was never looked at.
    if result_data["unscored_pathways"]:
        interp += (" Not assessed for lack of recent results: "
                   + ", ".join(result_data["unscored_pathways"]) + ".")

    # A pathway scored on less than half its evidence is worth saying out loud.
    thin = [name for name, pdata in result_data["pathways"].items()
            if pdata["score"] is not None and pdata["coverage"] < 0.5]
    if thin:
        interp += (" Based on limited results: " + ", ".join(thin) + ".")

    from app.schemas.wellness import HEBCSPathwayResult, HEBCSBiomarkerDetail
    pathway_response = {
        name: HEBCSPathwayResult(
            score=pdata["score"],
            weight=pdata["weight"],
            coverage=pdata["coverage"],
            coverage_with_derived=pdata["coverage_with_derived"],
            measured=pdata["measured"],
            derived=pdata["derived"],
            expected=pdata["expected"],
            biomarkers=[HEBCSBiomarkerDetail(**b) for b in pdata["biomarkers"]],
        )
        for name, pdata in result_data["pathways"].items()
    }

    return HEBCSScoreResponse(
        computed_at=datetime.now(timezone.utc),
        lab_date_used=latest_date,
        omega=result_data["omega"],
        omega_pct=result_data["omega_pct"],
        data_coverage=result_data["data_coverage"],
        pathways=pathway_response,
        unscored_pathways=result_data["unscored_pathways"],
        critical_biomarkers=criticals,
        interpretation=interp,
    )


@router.get("/score", response_model=WellnessScoreResponse)
async def get_wellness_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    client_timezone: str | None = Header(None, alias=TIMEZONE_HEADER),
    client_language: str | None = Header(None, alias=LANGUAGE_HEADER),
):
    """Calculate and return current wellness score (0-100)."""
    # §3aw: prose follows the patient. The findings were hand-written English
    # f-strings, so a patient who chose Yoruba read their own observations in
    # a language they did not pick — a gap the hardcoded sentences could not
    # close at all.
    data = await _compute_wellness_score(
        current_user.id, db,
        language=patient_language(current_user, client_language))
    # `today` becomes this row's `score_date` and the key the upsert dedupes
    # on. The containers run UTC, so from early evening in the Americas
    # `date.today()` is already TOMORROW for the patient — the score for their
    # Tuesday was filed under Wednesday, and opening the page on the real
    # Wednesday then found a row and did not recompute (§3am).
    today = patient_today(client_timezone, getattr(current_user, "timezone", None))

    # `confidence`, `components_unknown` and `detail` are computed per request
    # and have no column — the stored row is the history series. Splitting on
    # the model's real columns keeps them out of the constructor rather than
    # relying on the dict happening to match the table.
    columns = {c.name for c in WellnessScoreModel.__table__.columns}
    persisted = {k: v for k, v in data.items() if k in columns}

    # One row per DAY, updated in place. This used to `db.add` on every GET, so
    # merely opening the page inserted another row for today: measured on the
    # reference record 2026-10-04, **117 rows across 49 distinct days**, which
    # is why the 30-day history chart repeats dates (Sep 14, Sep 14 · Sep 10,
    # Sep 10 · Sep 6, Sep 6). The score is recomputed per request either way —
    # it answers "right now" — but the stored series is a daily history and a
    # day must appear in it once.
    score_obj = (await db.execute(
        select(WellnessScoreModel).where(
            WellnessScoreModel.user_id == current_user.id,
            WellnessScoreModel.score_date == today)
        .order_by(WellnessScoreModel.id.desc()).limit(1)
    )).scalar_one_or_none()

    if score_obj is None:
        score_obj = WellnessScoreModel(user_id=current_user.id, score_date=today)
        db.add(score_obj)
    for key, value in persisted.items():
        setattr(score_obj, key, value)
    await db.flush()
    await db.refresh(score_obj)

    return WellnessScoreResponse(
        **{c: getattr(score_obj, c) for c in columns},
        confidence=data.get("confidence"),
        components_unknown=data.get("components_unknown") or [],
        critical_findings=data.get("critical_findings") or [],
        detail=data.get("detail"),
    )


@router.get("/score/history", response_model=list[WellnessScoreResponse])
async def get_wellness_score_history(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() - timedelta(days=days)
    result = await db.execute(
        select(WellnessScoreModel)
        .where(WellnessScoreModel.user_id == current_user.id, WellnessScoreModel.score_date >= cutoff)
        .order_by(WellnessScoreModel.score_date.desc())
    )
    return result.scalars().all()


@router.get("/trends", response_model=HealthTrendResponse)
async def get_health_trends(
    days: int = Query(90, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    client_timezone: str | None = Header(None, alias=TIMEZONE_HEADER),
):
    """Multi-dimensional health trend analysis across EVERY logged domain.

    Streams come from `health_signals.collect_signals`, the same substrate the
    insight surface uses, rather than from one hand-written query per stream.

    Until 2026-10-11 this endpoint enumerated four: daily calories, mood,
    weekly workouts and weight-from-`vitals_logs`. Measured on the reference
    record, that produced *"Analyzing 3 health data streams over the past 90
    days"* with **Weight (kg) = 9 points** — on a patient holding 2,035
    dialysis sessions, 2,436 bowel movements, 1,029 dose logs and 5,221 recorded
    weights. Operator, 2026-10-11: *"All data must be visible and used by the
    various anaytytes, aggregators and AI queries. This cannot be compromised."*

    One substrate means a domain can only be forgotten in ONE place, and
    `tests/test_signals_cover_every_domain.py` already fails the build when a
    named domain has no signal. A new signal appears here with no change to
    this endpoint — which is the opposite of the four queries it replaces.
    """
    today = patient_today(client_timezone, getattr(current_user, "timezone", None))
    cutoff = today - timedelta(days=days)

    signals = await collect_signals(db, current_user.id, cutoff, today)

    # Most-populated first: a reader scrolling a trend page wants the series
    # that actually has shape, and the lab domain alone contributes ~84 keys.
    ordered = sorted(signals.items(), key=lambda kv: -len(kv[1]))

    streams: list[TrendStream] = []
    for key, series in ordered:
        if len(series) < 2:
            # A single point is not a trend. It is still visible through
            # /insights/signals, which reports sample counts rather than shape.
            continue
        points = [TrendDataPoint(date=str(d), value=float(v))
                  for d, v in sorted(series.items())]
        streams.append(TrendStream(
            name=signal_label(key),
            data=points,
            trend=_direction(key, [p.value for p in points]),
        ))

    domains = {signal_domain(k) for k, v in ordered if len(v) >= 2}
    summary = (
        f"Analyzing {len(streams)} health data streams across "
        f"{len(domains)} domains ({', '.join(sorted(domains))}) over the past "
        f"{days} days."
    ) if streams else (
        f"No stream has two or more days of data in the past {days} days."
    )

    correlations: list[str] = []
    suggestions = ["Continue monitoring your health metrics regularly."]
    if any(s.trend == "improving" for s in streams):
        correlations.append("Positive trends detected in multiple health areas.")

    return HealthTrendResponse(
        overall_summary=summary, streams=streams,
        correlations=correlations, suggestions=suggestions,
    )


#: Signals where the BETTER direction is clinically unambiguous, with `False`
#: meaning lower is better. A direction is ALLOW-LISTED, never defaulted.
#:
#: The first version of this defaulted to "rising is improving" for anything
#: unlisted, and the real record immediately produced **"Carbs improving"**,
#: **"Fat improving"** and **"Bowel movements improving"** — three clinical
#: claims nobody can support. More carbohydrate is not an improvement, and
#: whether more bowel movements is better depends entirely on why.
#:
#: §3az is the precedent and it is exact: that surface's thresholds were
#: population constants LOOSER than the patient's own limits — potassium 4,700
#: against this patient's 2,200 — so the alert could not fire at any intake
#: that endangered them. A judgement with no authority behind it is worse than
#: none, because it reads as one.
#:
#: ⚠️ Nutrient directions are deliberately NOT here. Whether a patient's sodium
#: should fall depends on `compute_goals`, which gives THIS patient 2,000 mg and
#: a renal potassium cap of 2,200 — a target, not a slope. Judging a nutrient
#: against its own last fortnight says nothing about whether it is safe. Wiring
#: these to the quota is queued rather than guessed (TASKS 15).
_BETTER_WHEN_RISING: dict[str, bool] = {
    "mood.score": True,
    "mood.energy": True,
    "sleep.quality": True,
    "sleep.hours": True,
    "activity.duration_min": True,
    "activity.steps": True,
    "medication.doses": True,          # adherence
    "mood.stress": False,
    "social.work_stress": False,
    "social.financial_stress": False,
    "symptom.count": False,
    "symptom.severity_max": False,
    "sleep.awakenings": False,
    "dialysis.readings_under_90": False,
    "elimination.blood_episodes": False,
    "elimination.vomiting": False,
}


def _direction(key: str, values: list[float]) -> str:
    """"stable" is the answer whenever no direction can be justified.

    Compares the first and last THIRD, not the first and last point: two
    endpoints make a direction out of noise, and on a patient whose pressure
    swings 40 mmHg inside one treatment whichever day happens to sit at each
    end would decide the label.

    A nadir is NOT judged this way either — §3am: it is read against a
    threshold (below 90 systolic is intradialytic hypotension), not against
    last fortnight. `dialysis.readings_under_90` carries that instead, where
    fewer is unambiguously better.
    """
    better_when_rising = _BETTER_WHEN_RISING.get(key)
    if better_when_rising is None or len(values) < 6:
        return "stable"
    third = max(len(values) // 3, 1)
    head = sum(values[:third]) / third
    tail = sum(values[-third:]) / third
    if head == 0:
        return "stable"
    change = (tail - head) / abs(head)
    if abs(change) < 0.05:          # under 5% is drift, not a trend
        return "stable"
    improving = (change > 0) == better_when_rising
    return "improving" if improving else "declining"


@router.get("/recommendations", response_model=DailyRecommendationsResponse)
async def get_daily_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    client_timezone: str | None = Header(None, alias=TIMEZONE_HEADER),
):
    """Personalized daily recommendations across 7 categories."""
    # "Today's" recommendations have to be the patient's today: on the server's
    # UTC date these would advise an evening in the Americas about tomorrow.
    #
    # The windows below are computed from the SAME date, and for the one-day
    # one that is not a nicety. A 30-day cutoff shrugs off a day's shift; a
    # window of `today - 1` becomes "today only" instead of "today and
    # yesterday" — a whole day of the patient's record dropped out of a check
    # that decides whether to tell them they have not logged anything.
    today = patient_today(client_timezone, getattr(current_user, "timezone", None))
    today_str = str(today)
    recs: dict[str, list[RecommendationItem]] = {
        "nutrition": [], "fitness": [], "sleep": [], "medication": [],
        "mood": [], "hydration": [], "general": [],
    }

    # Nutrition recs
    result = await db.execute(
        select(func.count(NutritionLog.id)).where(
            NutritionLog.user_id == current_user.id,
            NutritionLog.log_date >= (today - timedelta(days=1)),
        )
    )
    yesterday_meals = result.scalar() or 0
    if yesterday_meals < 3:
        recs["nutrition"].append(RecommendationItem(
            category="nutrition", title="Log your meals",
            description="You logged fewer than 3 meals yesterday. Try tracking all meals today.",
            priority="high", action="Go to Nutrition",
        ))
    recs["nutrition"].append(RecommendationItem(
        category="nutrition", title="Eat colorful vegetables",
        description="Aim for at least 5 servings of varied vegetables today.",
        priority="medium",
    ))

    # Fitness recs
    result = await db.execute(
        select(func.count(FitnessLog.id)).where(
            FitnessLog.user_id == current_user.id,
            FitnessLog.log_date >= (today - timedelta(days=7)),
        )
    )
    weekly_workouts = result.scalar() or 0
    target = 4
    if weekly_workouts < target:
        recs["fitness"].append(RecommendationItem(
            category="fitness", title="Get moving today",
            description=f"You've had {weekly_workouts} workouts this week (target: {target}). Try a 30-minute walk.",
            priority="high", action="Go to Fitness",
        ))

    # Sleep recs
    recs["sleep"].append(RecommendationItem(
        category="sleep", title="Aim for 7-8 hours",
        description="Consistent bedtime and wake time improve sleep quality.",
        priority="medium",
    ))

    # Medication recs
    result = await db.execute(
        select(Medication).where(Medication.user_id == current_user.id, Medication.is_active == True)
    )
    active_meds = result.scalars().all()
    if active_meds:
        recs["medication"].append(RecommendationItem(
            category="medication", title="Take your medications",
            description=f"You have {len(active_meds)} active medication(s). Don't forget today's doses.",
            priority="high",
        ))

    # Mood recs
    recs["mood"].append(RecommendationItem(
        category="mood", title="Check in with yourself",
        description="Take a moment to log your mood and reflect on how you're feeling.",
        priority="medium", action="Go to Mood",
    ))

    # Hydration recs
    recs["hydration"].append(RecommendationItem(
        category="hydration", title="Stay hydrated",
        description="Aim for 8 glasses of water today. Adjust based on activity level.",
        priority="medium",
    ))

    # General recs
    recs["general"].append(RecommendationItem(
        category="general", title="Health check reminder",
        description="Schedule your next routine check-up if it's been over 6 months.",
        priority="low",
    ))

    all_recs = [r for v in recs.values() for r in v]
    return DailyRecommendationsResponse(
        date=today_str, recommendations=all_recs, **recs,
    )


@router.get("/improvements", response_model=HealthImprovementsResponse)
async def get_health_improvements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Score-based health improvement recommendations."""
    data = await _compute_wellness_score(current_user.id, db)
    score = data["overall_score"]

    nutrition_improvements = []
    fitness_improvements = []
    sleep_improvements = []
    mood_improvements = []
    medical_improvements = []

    # `None` means the domain was never measured, and `None < 70` raises
    # TypeError. Captured from the deployed service on 2026-10-04:
    #
    #   GET /api/v1/wellness/improvements -> 500
    #   TypeError: '<' not supported between instances of 'NoneType' and 'int'
    #
    # Every one of the five comparisons below carried it, and the summary line
    # formatted `score` the same way. The faults are the same shape as the ones
    # `74c8671` fixed in /score and `44641f5` fixed again: making a score
    # legitimately None is only half a change — every reader has to learn that
    # absence is not a low number. This endpoint never did, so the Improve tab
    # has answered 500 to any patient missing a domain, which on the reference
    # record is sleep, mood and fitness.
    def _below(key: str, threshold: float) -> bool:
        """True only when the domain was MEASURED and fell short."""
        value = data.get(key)
        return value is not None and value < threshold

    if _below("nutrition_score", 70):
        nutrition_improvements.extend([
            "Log meals consistently to track nutrient intake.",
            "Focus on whole foods: fruits, vegetables, lean proteins, whole grains.",
            "Reduce processed food and added sugar intake.",
        ])
    if _below("fitness_score", 70):
        fitness_improvements.extend([
            "Start with 150 minutes of moderate exercise per week.",
            "Include both cardio and strength training.",
            "Take breaks from sitting every hour.",
        ])
    if _below("sleep_score", 70):
        sleep_improvements.extend([
            "Maintain a consistent sleep schedule.",
            "Limit caffeine after 2 PM.",
            "Create a dark, quiet sleep environment.",
        ])
    if _below("mood_score", 60):
        mood_improvements.extend([
            "Practice daily gratitude journaling.",
            "Engage in activities you enjoy.",
            "Consider mindfulness meditation for stress management.",
        ])
    if _below("vitals_score", 50):
        medical_improvements.extend([
            "Log vitals regularly to track health trends.",
            "Schedule a check-up with your healthcare provider.",
        ])

    # A clinical finding outranks a lifestyle tip. These are already written as
    # finished sentences naming the value and what judged it, so they are shown
    # verbatim rather than summarised into something vaguer.
    for finding in (data.get("critical_findings") or []):
        medical_improvements.append(finding)

    if score is None:
        summary = ("There is not enough recorded yet to calculate a wellness "
                   "score. This is not a score of zero — nothing has been "
                   "measured.")
    else:
        summary = f"Your wellness score is {score:.0f}/100. "
        if data.get("critical_findings"):
            # Never congratulate past a finding. A patient whose treatments end
            # hypotensive must not read "You're doing great".
            summary += "Some findings below need clinical attention."
        elif score >= 80:
            summary += "You're doing great! Keep up the healthy habits."
        elif score >= 60:
            summary += "You're on the right track. Focus on the areas below for improvement."
        else:
            summary += "There are several areas where you can improve. Start with small changes."

    return HealthImprovementsResponse(
        summary=summary, wellness_score=score,
        nutrition_improvements=nutrition_improvements,
        fitness_improvements=fitness_improvements,
        sleep_improvements=sleep_improvements,
        mood_improvements=mood_improvements,
        medical_improvements=medical_improvements,
    )


# ── HEBCS What-If Simulator ────────────────────────────────────────────────

async def _fetch_latest_biomarkers(user_id: int, db: AsyncSession) -> dict[str, float]:
    """Return the most recent value per lab test_name for this user."""
    result = await db.execute(
        select(LabResult.test_name, LabResult.value, LabResult.test_date)
        .where(LabResult.user_id == user_id, LabResult.value.isnot(None))
        .order_by(LabResult.test_name, LabResult.test_date.desc())
    )
    biomarkers: dict[str, float] = {}
    seen: set[str] = set()
    for test_name, value, _ in result.all():
        if test_name not in seen:
            biomarkers[test_name] = value
            seen.add(test_name)
    return biomarkers


@router.post("/whatif", response_model=WhatIfResponse)
async def what_if_scenario(
    request: WhatIfRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """HEBCS What-If Clinical Simulator.

    Override any subset of biomarker values to simulate how a clinical
    intervention (dietary change, medication adjustment, dialysis
    parameter change) would affect the patient's Ω wellness score.

    Example: {"Phosphorus": 4.5, "Albumin": 4.2} asks
    "What would my Ω be if phosphorus dropped to 4.5 and albumin
    improved to 4.2?"
    """
    # Baseline: real latest lab values
    baseline_bio = await _fetch_latest_biomarkers(current_user.id, db)

    # Scenario: override with hypothetical values
    overrides = request.to_biomarker_dict()
    scenario_bio = {**baseline_bio, **overrides}

    # If both Calcium and Phosphorus are present (either real or overridden),
    # recompute CaxP product automatically for the scenario
    ca = scenario_bio.get("Calcium")
    p = scenario_bio.get("Phosphorus")
    if ca is not None and p is not None:
        scenario_bio["CaxP Product"] = ca * p
    ca_b = baseline_bio.get("Calcium")
    p_b = baseline_bio.get("Phosphorus")
    if ca_b is not None and p_b is not None:
        baseline_bio["CaxP Product"] = ca_b * p_b

    baseline_result = compute_hebcs(baseline_bio)
    scenario_result = compute_hebcs(scenario_bio)

    baseline_omega = baseline_result["omega"]
    scenario_omega = scenario_result["omega"]
    delta = scenario_omega - baseline_omega

    # Per-pathway deltas
    pathway_deltas: dict[str, WhatIfPathwayDelta] = {}
    for pname in baseline_result["pathways"]:
        b_score = baseline_result["pathways"][pname]["score"]
        s_score = scenario_result["pathways"][pname].get("score")
        pathway_deltas[pname] = WhatIfPathwayDelta(
            baseline_score=b_score,
            scenario_score=s_score,
            delta=(s_score - b_score) if (s_score is not None and b_score is not None) else None,
        )

    # Interpretation
    delta_pct = delta * 100
    if abs(delta_pct) < 0.5:
        interp = f"Minimal change (Δ = {delta_pct:+.1f}%). The selected parameter adjustments have little impact on your overall Ω."
    elif delta > 0:
        top_gainers = sorted(
            [(n, d.delta) for n, d in pathway_deltas.items() if d.delta and d.delta > 0],
            key=lambda x: x[1], reverse=True,
        )[:2]
        gainers_str = ", ".join(f"{n} (+{v:.2f})" for n, v in top_gainers)
        interp = (
            f"This intervention would improve your Ω by {delta_pct:+.1f}% "
            f"({baseline_omega:.3f} → {scenario_omega:.3f}). "
            f"Pathways gaining most: {gainers_str}."
        )
    else:
        top_losers = sorted(
            [(n, d.delta) for n, d in pathway_deltas.items() if d.delta and d.delta < 0],
            key=lambda x: x[1],
        )[:2]
        losers_str = ", ".join(f"{n} ({v:.2f})" for n, v in top_losers)
        interp = (
            f"This scenario worsens your Ω by {abs(delta_pct):.1f}% "
            f"({baseline_omega:.3f} → {scenario_omega:.3f}). "
            f"Most affected pathways: {losers_str}."
        )

    return WhatIfResponse(
        scenario_name=request.scenario_name,
        baseline_omega=baseline_omega,
        scenario_omega=scenario_omega,
        delta_omega=delta,
        delta_pct=delta_pct,
        pathway_deltas=pathway_deltas,
        overridden_biomarkers=list(overrides.keys()),
        interpretation=interp,
    )
