"""Meal & Exercise Planner endpoints — AI-powered 7-day plans with deterministic fallback."""

import json
import logging
import httpx
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.wellness import MealPlan as MealPlanModel, ExercisePlan as ExercisePlanModel
from app.models.chronic_conditions import ChronicCondition, TherapySession
from app.models.medications import Medication
from app.models.nutrition import NutritionLog
from app.models.labs import LabResult
from app.models.pantry import PantryItem
# Module scope, not inside the helpers: the endpoint needs to catch this too,
# and a function-local import leaves the name unbound in the handler above.
# alafia_model_service imports nothing from app, so there is no cycle.
from app.services.alafia_model_service import ALAFIAModelError
from app.services import food_safety
from app.schemas.wellness import (
    MealPlanRequest, MealPlanResponse, MealItem, DayMeals,
    ExercisePlanRequest, ExercisePlanResponse, ExerciseItem, DayWorkout,
    MealSuggestionRequest, MealSuggestion, MealSuggestionsResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Deterministic Meal Plan Templates ───────────────────────────

MEAL_TEMPLATES = {
    "balanced": {
        "Monday": DayMeals(day="Monday", breakfast=MealItem(name="Oatmeal with berries", calories=350, protein_g=12, carbs_g=55, fat_g=8), lunch=MealItem(name="Grilled chicken salad", calories=450, protein_g=35, carbs_g=20, fat_g=22), dinner=MealItem(name="Salmon with quinoa and vegetables", calories=550, protein_g=38, carbs_g=45, fat_g=18)),
        "Tuesday": DayMeals(day="Tuesday", breakfast=MealItem(name="Greek yogurt parfait", calories=300, protein_g=20, carbs_g=40, fat_g=8), lunch=MealItem(name="Turkey wrap with hummus", calories=420, protein_g=28, carbs_g=38, fat_g=16), dinner=MealItem(name="Lean beef stir-fry with brown rice", calories=520, protein_g=32, carbs_g=48, fat_g=18)),
        "Wednesday": DayMeals(day="Wednesday", breakfast=MealItem(name="Whole grain toast with avocado and eggs", calories=380, protein_g=18, carbs_g=30, fat_g=22), lunch=MealItem(name="Lentil soup with whole grain bread", calories=400, protein_g=22, carbs_g=52, fat_g=8), dinner=MealItem(name="Baked chicken with sweet potato", calories=500, protein_g=36, carbs_g=42, fat_g=14)),
        "Thursday": DayMeals(day="Thursday", breakfast=MealItem(name="Smoothie with spinach, banana, protein powder", calories=320, protein_g=25, carbs_g=42, fat_g=6), lunch=MealItem(name="Tuna salad sandwich", calories=430, protein_g=30, carbs_g=34, fat_g=18), dinner=MealItem(name="Pasta with marinara and vegetables", calories=480, protein_g=18, carbs_g=65, fat_g=12)),
        "Friday": DayMeals(day="Friday", breakfast=MealItem(name="Eggs with whole grain toast", calories=340, protein_g=20, carbs_g=28, fat_g=16), lunch=MealItem(name="Chickpea bowl with tahini dressing", calories=440, protein_g=18, carbs_g=50, fat_g=18), dinner=MealItem(name="Grilled fish tacos", calories=480, protein_g=30, carbs_g=38, fat_g=20)),
        "Saturday": DayMeals(day="Saturday", breakfast=MealItem(name="Pancakes with fresh fruit", calories=400, protein_g=10, carbs_g=60, fat_g=14), lunch=MealItem(name="Grilled vegetable and goat cheese wrap", calories=380, protein_g=16, carbs_g=36, fat_g=18), dinner=MealItem(name="Roast chicken with roasted vegetables", calories=550, protein_g=40, carbs_g=30, fat_g=22)),
        "Sunday": DayMeals(day="Sunday", breakfast=MealItem(name="Veggie omelet with fruit", calories=360, protein_g=22, carbs_g=25, fat_g=18), lunch=MealItem(name="Quinoa Buddha bowl", calories=420, protein_g=16, carbs_g=55, fat_g=14), dinner=MealItem(name="Slow cooker beef stew", calories=500, protein_g=32, carbs_g=40, fat_g=16)),
    },
    "renal": {
        "Monday": DayMeals(day="Monday", breakfast=MealItem(name="Cream of wheat with blueberries", calories=300, protein_g=6, carbs_g=55, fat_g=4), lunch=MealItem(name="Chicken breast with white rice and green beans", calories=420, protein_g=28, carbs_g=48, fat_g=10), dinner=MealItem(name="Baked cod with couscous", calories=400, protein_g=30, carbs_g=42, fat_g=8)),
        "Tuesday": DayMeals(day="Tuesday", breakfast=MealItem(name="Bagel with cream cheese", calories=320, protein_g=8, carbs_g=48, fat_g=10), lunch=MealItem(name="Turkey sandwich on white bread", calories=380, protein_g=24, carbs_g=36, fat_g=12), dinner=MealItem(name="Pasta with olive oil and garlic shrimp", calories=450, protein_g=26, carbs_g=52, fat_g=14)),
        "Wednesday": DayMeals(day="Wednesday", breakfast=MealItem(name="Rice cereal with unsweetened almond milk", calories=280, protein_g=4, carbs_g=52, fat_g=4), lunch=MealItem(name="Egg salad on crackers", calories=350, protein_g=16, carbs_g=28, fat_g=18), dinner=MealItem(name="Pork tenderloin with applesauce", calories=400, protein_g=30, carbs_g=30, fat_g=14)),
        "Thursday": DayMeals(day="Thursday", breakfast=MealItem(name="Pancakes with maple syrup", calories=360, protein_g=6, carbs_g=60, fat_g=10), lunch=MealItem(name="Chicken noodle soup (low sodium)", calories=340, protein_g=22, carbs_g=36, fat_g=10), dinner=MealItem(name="Tilapia with white rice and cabbage slaw", calories=420, protein_g=28, carbs_g=48, fat_g=10)),
        "Friday": DayMeals(day="Friday", breakfast=MealItem(name="Toast with jelly and butter", calories=280, protein_g=4, carbs_g=42, fat_g=10), lunch=MealItem(name="Grilled cheese sandwich (white bread)", calories=380, protein_g=14, carbs_g=32, fat_g=20), dinner=MealItem(name="Roast chicken with mashed cauliflower", calories=440, protein_g=34, carbs_g=20, fat_g=22)),
        "Saturday": DayMeals(day="Saturday", breakfast=MealItem(name="Cornflakes with rice milk", calories=260, protein_g=3, carbs_g=52, fat_g=2), lunch=MealItem(name="BLT on white bread", calories=400, protein_g=14, carbs_g=32, fat_g=22), dinner=MealItem(name="Beef burger patty (no bun) with coleslaw", calories=420, protein_g=28, carbs_g=12, fat_g=28)),
        "Sunday": DayMeals(day="Sunday", breakfast=MealItem(name="Waffles with strawberries", calories=340, protein_g=6, carbs_g=52, fat_g=12), lunch=MealItem(name="Tuna on crackers with cucumber", calories=320, protein_g=22, carbs_g=24, fat_g=12), dinner=MealItem(name="Baked ziti (low potassium cheese)", calories=460, protein_g=20, carbs_g=52, fat_g=16)),
    },
}

SHOPPING_LISTS = {
    "balanced": [
        "Oats", "Berries", "Greek yogurt", "Chicken breast", "Salmon fillet", "Quinoa",
        "Brown rice", "Lentils", "Turkey slices", "Hummus", "Whole grain bread", "Avocados",
        "Eggs", "Spinach", "Bananas", "Protein powder", "Tuna", "Chickpeas", "Tahini",
        "Fresh vegetables", "Sweet potatoes", "Goat cheese", "Lean beef", "Pasta", "Marinara sauce",
    ],
    "renal": [
        "Cream of wheat", "Blueberries", "Bagels", "Cream cheese", "Chicken breast", "White rice",
        "Green beans", "Cod", "Couscous", "Turkey slices", "White bread", "Crackers",
        "Eggs", "Pork tenderloin", "Applesauce", "Pancake mix", "Maple syrup", "Tilapia",
        "Cabbage", "Jelly", "Butter", "Cornflakes", "Rice milk", "Cauliflower",
    ],
}

EXERCISE_TEMPLATES = {
    "beginner": [
        DayWorkout(day="Monday", focus="full_body", total_minutes=30, exercises=[
            ExerciseItem(name="Brisk Walking", type="warmup", duration_minutes=5),
            ExerciseItem(name="Bodyweight Squats", type="strength", sets=2, reps=10),
            ExerciseItem(name="Wall Push-ups", type="strength", sets=2, reps=8),
            ExerciseItem(name="Walking", type="cardio", duration_minutes=10),
            ExerciseItem(name="Stretching", type="flexibility", duration_minutes=5),
        ]),
        DayWorkout(day="Tuesday", focus="rest", total_minutes=15, exercises=[
            ExerciseItem(name="Gentle Stretching", type="flexibility", duration_minutes=15),
        ]),
        DayWorkout(day="Wednesday", focus="cardio", total_minutes=25, exercises=[
            ExerciseItem(name="Warm-up Walk", type="warmup", duration_minutes=5),
            ExerciseItem(name="Brisk Walking or Light Jogging", type="cardio", duration_minutes=15),
            ExerciseItem(name="Cool-down Stretch", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Thursday", focus="rest", total_minutes=15, exercises=[
            ExerciseItem(name="Yoga", type="flexibility", duration_minutes=15),
        ]),
        DayWorkout(day="Friday", focus="full_body", total_minutes=30, exercises=[
            ExerciseItem(name="March in Place", type="warmup", duration_minutes=3),
            ExerciseItem(name="Chair Squats", type="strength", sets=2, reps=10),
            ExerciseItem(name="Knee Push-ups", type="strength", sets=2, reps=8),
            ExerciseItem(name="Seated Leg Raises", type="strength", sets=2, reps=12),
            ExerciseItem(name="Walking", type="cardio", duration_minutes=10),
            ExerciseItem(name="Stretching", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Saturday", focus="cardio", total_minutes=30, exercises=[
            ExerciseItem(name="Walking in Nature", type="cardio", duration_minutes=25),
            ExerciseItem(name="Stretching", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Sunday", focus="rest", total_minutes=0, exercises=[]),
    ],
    "moderate": [
        DayWorkout(day="Monday", focus="upper_body", total_minutes=45, exercises=[
            ExerciseItem(name="Jump Rope", type="warmup", duration_minutes=5),
            ExerciseItem(name="Push-ups", type="strength", sets=3, reps=15),
            ExerciseItem(name="Dumbbell Rows", type="strength", sets=3, reps=12),
            ExerciseItem(name="Shoulder Press", type="strength", sets=3, reps=12),
            ExerciseItem(name="Plank", type="strength", sets=3, reps=30, notes="seconds"),
            ExerciseItem(name="Cool-down Stretch", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Tuesday", focus="cardio", total_minutes=35, exercises=[
            ExerciseItem(name="Warm-up", type="warmup", duration_minutes=5),
            ExerciseItem(name="Running / Cycling", type="cardio", duration_minutes=25),
            ExerciseItem(name="Stretching", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Wednesday", focus="lower_body", total_minutes=45, exercises=[
            ExerciseItem(name="Light Jog", type="warmup", duration_minutes=5),
            ExerciseItem(name="Squats", type="strength", sets=3, reps=15),
            ExerciseItem(name="Lunges", type="strength", sets=3, reps=12),
            ExerciseItem(name="Calf Raises", type="strength", sets=3, reps=15),
            ExerciseItem(name="Glute Bridges", type="strength", sets=3, reps=12),
            ExerciseItem(name="Stretching", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Thursday", focus="rest", total_minutes=20, exercises=[
            ExerciseItem(name="Yoga / Active Recovery", type="flexibility", duration_minutes=20),
        ]),
        DayWorkout(day="Friday", focus="full_body", total_minutes=45, exercises=[
            ExerciseItem(name="Warm-up", type="warmup", duration_minutes=5),
            ExerciseItem(name="Burpees", type="cardio", sets=3, reps=10),
            ExerciseItem(name="Mountain Climbers", type="cardio", sets=3, reps=20),
            ExerciseItem(name="Deadlift (or bodyweight)", type="strength", sets=3, reps=10),
            ExerciseItem(name="Bicep Curls", type="strength", sets=3, reps=12),
            ExerciseItem(name="Stretching", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Saturday", focus="cardio", total_minutes=40, exercises=[
            ExerciseItem(name="HIIT Intervals", type="cardio", duration_minutes=25),
            ExerciseItem(name="Warm-up + Cool-down", type="warmup", duration_minutes=15),
        ]),
        DayWorkout(day="Sunday", focus="rest", total_minutes=0, exercises=[]),
    ],
    "advanced": [
        DayWorkout(day="Monday", focus="upper_body", total_minutes=60, exercises=[
            ExerciseItem(name="Dynamic Warm-up", type="warmup", duration_minutes=5),
            ExerciseItem(name="Bench Press", type="strength", sets=4, reps=8),
            ExerciseItem(name="Pull-ups", type="strength", sets=4, reps=10),
            ExerciseItem(name="Overhead Press", type="strength", sets=4, reps=8),
            ExerciseItem(name="Barbell Rows", type="strength", sets=4, reps=10),
            ExerciseItem(name="Tricep Dips", type="strength", sets=3, reps=12),
            ExerciseItem(name="Bicep Curls", type="strength", sets=3, reps=12),
            ExerciseItem(name="Cool-down", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Tuesday", focus="cardio", total_minutes=50, exercises=[
            ExerciseItem(name="HIIT Sprint Intervals", type="cardio", duration_minutes=30),
            ExerciseItem(name="Warm-up + Cool-down", type="warmup", duration_minutes=20),
        ]),
        DayWorkout(day="Wednesday", focus="lower_body", total_minutes=60, exercises=[
            ExerciseItem(name="Warm-up", type="warmup", duration_minutes=5),
            ExerciseItem(name="Squats", type="strength", sets=4, reps=8),
            ExerciseItem(name="Romanian Deadlifts", type="strength", sets=4, reps=10),
            ExerciseItem(name="Bulgarian Split Squats", type="strength", sets=3, reps=10),
            ExerciseItem(name="Leg Press", type="strength", sets=4, reps=10),
            ExerciseItem(name="Calf Raises", type="strength", sets=4, reps=15),
            ExerciseItem(name="Cool-down", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Thursday", focus="rest", total_minutes=30, exercises=[
            ExerciseItem(name="Active Recovery / Yoga", type="flexibility", duration_minutes=30),
        ]),
        DayWorkout(day="Friday", focus="full_body", total_minutes=60, exercises=[
            ExerciseItem(name="Warm-up", type="warmup", duration_minutes=5),
            ExerciseItem(name="Deadlift", type="strength", sets=4, reps=6),
            ExerciseItem(name="Clean and Press", type="strength", sets=3, reps=8),
            ExerciseItem(name="Box Jumps", type="cardio", sets=3, reps=10),
            ExerciseItem(name="Farmer's Walk", type="strength", sets=3, reps=1, notes="40m each"),
            ExerciseItem(name="Ab Wheel Rollouts", type="strength", sets=3, reps=10),
            ExerciseItem(name="Cool-down", type="cooldown", duration_minutes=5),
        ]),
        DayWorkout(day="Saturday", focus="cardio", total_minutes=50, exercises=[
            ExerciseItem(name="Long Run / Cycling", type="cardio", duration_minutes=40),
            ExerciseItem(name="Warm-up + Cool-down", type="warmup", duration_minutes=10),
        ]),
        DayWorkout(day="Sunday", focus="rest", total_minutes=0, exercises=[]),
    ],
}


# ── Condition → Diet Pattern mapping ─────────────────────────────────────────
_DIET_KEYWORDS: dict[str, list[str]] = {
    "renal": ["renal", "kidney", "ckd", "esrd", "nephropathy", "dialysis", "hemodialysis", "peritoneal"],
    "diabetic": ["diabetes", "diabetic", "hyperglycemia", "type 2 diabetes", "type 1 diabetes"],
    "cardiac": ["heart failure", "cardiac", "cardiomyopathy", "coronary artery"],
}


def _detect_diet_pattern(conditions: list, user_requested: str) -> str:
    """Auto-detect the best dietary pattern from active chronic conditions."""
    if user_requested and user_requested not in ("balanced",):
        return user_requested  # explicit user choice takes precedence
    for cond in conditions:
        name_lc = (cond.name or "").lower()
        for pattern, kws in _DIET_KEYWORDS.items():
            if any(kw in name_lc for kw in kws):
                return pattern
    return user_requested or "balanced"


async def _gather_planner_context(user_id: int, db: AsyncSession) -> dict:
    """Query the DB for data needed to personalise a plan."""
    # Conditions live in TWO tables — see app/services/clinical_sources.py.
    # A meal or exercise plan built without the patient's renal diagnosis is
    # not a safe plan, so this reads both.
    from app.services import clinical_sources

    cond_rows = (await clinical_sources.conditions(db, user_id, active_only=True))[:10]

    med_rows = (await db.execute(
        select(Medication)
        .where(Medication.user_id == user_id, Medication.is_active == True)  # noqa: E712
        .limit(20)
    )).scalars().all()

    cutoff = date.today() - timedelta(days=14)
    nutrition_rows = (await db.execute(
        select(NutritionLog)
        .where(NutritionLog.user_id == user_id, NutritionLog.log_date >= cutoff)
        .order_by(desc(NutritionLog.log_date))
        .limit(20)
    )).scalars().all()

    therapy_rows = (await db.execute(
        select(TherapySession)
        .where(TherapySession.user_id == user_id)
        .order_by(desc(TherapySession.scheduled_date))
        .limit(12)
    )).scalars().all()

    # Most recent lab results (one per test) — drives goals like raising
    # hemoglobin / vitamin D / calcium and lowering phosphorus / potassium.
    lab_rows = (await db.execute(
        select(LabResult)
        .where(LabResult.user_id == user_id)
        .order_by(desc(LabResult.test_date))
        .limit(40)
    )).scalars().all()
    latest_labs: dict[str, LabResult] = {}
    for lab in lab_rows:
        key = (lab.test_name or "").lower()
        if key and key not in latest_labs:
            latest_labs[key] = lab

    pantry_rows = (await db.execute(
        select(PantryItem).where(PantryItem.user_id == user_id).limit(100)
    )).scalars().all()

    # The patient themselves. Without these a "personalised" plan cannot size a
    # single portion: protein is prescribed per kg, energy per kg and age/sex,
    # and both were absent here while the chat surface had them all along.
    user_row = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

    # The SAME authoritative targets the chat surface and the Nutrition screen
    # use, rather than letting the model recall a guideline. A production plan
    # told a haemodialysis patient "~0.6 g/kg" — the PRE-dialysis figure, and
    # roughly half of what `compute_goals` computes for them.
    goals: dict = {}
    if user_row is not None:
        try:
            from app.services.nutrient_goals_service import compute_goals
            goals = compute_goals(
                date_of_birth=str(user_row.date_of_birth) if user_row.date_of_birth else None,
                sex=user_row.gender,
                height_cm=user_row.height_cm,
                current_weight_kg=user_row.current_weight_kg,
                target_weight_kg=user_row.target_weight_kg,
                activity_level=user_row.activity_level,
                conditions=cond_rows,
            )
        except Exception:  # noqa: BLE001 - a plan without targets beats no plan
            logger.warning("Planner: nutrient goals unavailable", exc_info=True)

    return {
        "user": user_row,
        "conditions": cond_rows,
        "medications": med_rows,
        "nutrition_logs": nutrition_rows,
        "therapy_sessions": therapy_rows,
        "labs": list(latest_labs.values()),
        "pantry": pantry_rows,
        "goals": goals,
        "forbidden": food_safety.forbidden_for(user_row, cond_rows) if user_row else [],
    }


def _subject_for(user: "User") -> str:
    """Our handle for the patient, as sent to a model provider.

    NOT the name. Both planner prompts used to open with
    `PATIENT: {user.full_name}` while the chat surface deliberately sent an
    HMAC token — canon §3al: identity never leaves, and not putting the name in
    the payload is stronger than trusting the egress scrubber to recognise it,
    because it also holds on the Ollama path where no scrubbing runs.
    """
    from app.services.prompt_identity import subject_reference
    return subject_reference(user)


def _dialysis_summary(therapy_rows: list) -> str:
    """How often this patient is treated, and when — stated as fact, not schedule.

    Do NOT collapse the gathered sessions into "the days they dialyse". This
    patient's last twelve sessions cover Mon/Wed/Fri *and* Tue/Thu/Sat/Sun,
    because the schedule changed part-way through the window: naively unioning
    the weekdays says "dialysis every day", which would have the exercise
    planner prescribe rest seven days a week.

    The recent DATES are unambiguous and need no inference, so that is what is
    reported, alongside an observed frequency.
    """
    dated = [t for t in (therapy_rows or []) if getattr(t, "scheduled_date", None)]
    if not dated:
        return ""
    dated.sort(key=lambda t: t.scheduled_date, reverse=True)

    recent = dated[:6]
    spans = (recent[0].scheduled_date - recent[-1].scheduled_date).days if len(recent) > 1 else 0
    # n sessions span n-1 intervals: 6 sessions over 11 days is 3/week, not 4.
    per_week = ((len(recent) - 1) / (spans / 7)) if spans >= 7 else None

    parts = []
    if per_week:
        parts.append(f"about {per_week:.0f} sessions/week")
    latest = "; ".join(
        f"{_DAYS[t.scheduled_date.weekday()]} {t.scheduled_date.date()}"
        for t in recent[:3]
    )
    parts.append(f"most recent: {latest}")
    return " — ".join(parts)


def _patient_block(user: "User", ctx: dict) -> str:
    """Who the patient is, and the numbers a plan has to hit.

    Age, sex and weight are not optional colour: a renal protein target is
    prescribed per kg of body weight, so a planner without them is guessing.
    """
    u = ctx.get("user") or user
    lines: list[str] = [f"PATIENT REFERENCE: {_subject_for(u)}"]

    # date_of_birth is a String(10) column, not a Date — parse it with the same
    # helper compute_goals uses rather than a second, subtly different one.
    from app.services.nutrient_goals_service import _calc_age
    age = _calc_age(getattr(u, "date_of_birth", None))
    if age is not None:
        lines.append(f"AGE: {age}")
    if getattr(u, "gender", None):
        lines.append(f"SEX: {u.gender}")
    if getattr(u, "current_weight_kg", None):
        lines.append(f"BODY WEIGHT: {u.current_weight_kg} kg")
    if getattr(u, "height_cm", None):
        lines.append(f"HEIGHT: {u.height_cm} cm")
    if getattr(u, "activity_level", None):
        lines.append(f"ACTIVITY LEVEL: {u.activity_level}")

    dialysis = _dialysis_summary(ctx.get("therapy_sessions") or [])
    if dialysis:
        lines.append(f"DIALYSIS: {dialysis}")
        lines.append(
            "A dialysis session removes potassium and phosphorus from the BLOOD. "
            "It does not raise the dietary limits below — those already assume "
            "a patient on dialysis."
        )

    goal_rows = (ctx.get("goals") or {}).get("goals") or []
    if goal_rows:
        lines.append("")
        lines.append("DAILY TARGETS FOR THIS PATIENT (authoritative — use these exact figures,")
        lines.append("do not substitute a remembered guideline, and never quote a SERUM")
        lines.append("reference range (mmol/L, mEq/L) as a dietary intake limit):")
        for g in goal_rows:
            kind = "max/day" if g.get("kind") == "limit" else "aim/day"
            lines.append(
                f"  - {g.get('name') or g.get('key')}: "
                f"{g.get('goal')} {g.get('unit') or ''} ({kind})".rstrip()
            )
        energy = (ctx.get("goals") or {}).get("energy_kcal")
        if energy:
            lines.append(f"  - Energy: {energy} kcal (aim/day)")

    forbidden_block = food_safety.prompt_block(ctx.get("forbidden") or [])
    if forbidden_block:
        lines.append("")
        lines.append(forbidden_block)

    return "\n".join(lines)


_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


async def _ollama_generate_meal_plan(
    user: "User",
    ctx: dict,
    pattern: str,
) -> "list[DayMeals] | None":
    """Ask Ollama to generate a personalised 7-day meal plan. Returns None on any failure."""
    conditions_str = "; ".join(c.name for c in ctx["conditions"]) or "None reported"
    meds_str = (
        "; ".join(
            f"{m.name} {m.dosage or ''} {m.dosage_unit or ''} {m.frequency or ''}".strip()
            for m in ctx["medications"]
        )
        or "None"
    )
    recent_foods = (
        "; ".join(n.food_name for n in ctx["nutrition_logs"][:10] if n.food_name)
        or "Not recorded"
    )
    restrictions = "; ".join(
        v for v in (
            getattr(user, "dietary_restrictions", None),
            getattr(user, "allergies", None),
            getattr(user, "food_intolerances", None),
        )
        if v
    ) or "None"

    meal_schema = '{"name":"...","calories":400,"protein_g":25,"carbs_g":45,"fat_g":12}'
    day_schema = (
        f'{{"day":"Monday","breakfast":{meal_schema},'
        f'"lunch":{meal_schema},"dinner":{meal_schema},"snack":{meal_schema}}}'
    )
    labs_str = _labs_summary(ctx.get("labs", []))
    prompt = (
        f"You are a clinical dietitian. Generate a personalized 7-day meal plan.\n\n"
        f"{_patient_block(user, ctx)}\n\n"
        f"CHRONIC CONDITIONS: {conditions_str}\n"
        f"ACTIVE MEDICATIONS: {meds_str}\n"
        f"RECENT LAB RESULTS: {labs_str}\n"
        f"DIETARY RESTRICTIONS / ALLERGIES: {restrictions}\n"
        f"DIETARY PATTERN: {pattern}\n"
        f"RECENT FOODS PATIENT EATS: {recent_foods}\n\n"
        f"RULES:\n"
        f"1. Output ONLY a valid JSON array. No markdown, no code fences, no explanation.\n"
        f"2. Exactly 7 objects (Monday-Sunday), each matching: {day_schema}\n"
        f"3. All calorie/macro fields must be numbers.\n"
        f"4. If pattern is 'renal': low potassium (avoid bananas, oranges, potatoes, tomatoes), "
        f"low phosphorus (avoid nuts, whole grains, cola), sodium <1500 mg/day, moderate protein.\n"
        f"5. If pattern is 'diabetic': low glycemic index, limit simple carbs, even carb distribution.\n"
        f"6. Respect all allergies and restrictions listed above. Never include a "
        f"FORBIDDEN item, in any form or as a substitution.\n"
        f"7. Personalise based on recent foods the patient eats.\n"
        f"8. The whole day's totals must land on the DAILY TARGETS above — protein "
        f"and energy in particular. Size portions to this patient's body weight.\n\n"
        f"Output only the JSON array:"
    )

    # Routed through ALAFIAModel (Ollama → OpenAI fallback). Freeform output —
    # the model returns a JSON array, which is extracted below.
    from app.services.alafia_model_service import alafia_chat, ALAFIAModelError
    try:
        raw = (await alafia_chat(
            [{"role": "user", "content": prompt}], temperature=0.4, max_tokens=2048,
        )).strip()
    except ALAFIAModelError as exc:
        # Falling back to a deterministic template is deliberate: the user
        # still gets a plan. But the reason has to reach the logs, or a
        # provider that has been down for weeks is indistinguishable from
        # "the template was fine".
        logger.warning("Planner: model unavailable, using template fallback: %s", exc)
        return None

    try:
        start = raw.index("[")
        end = raw.rindex("]") + 1
        days_data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(days_data, list) or len(days_data) < 7:
        return None

    def _parse_meal(m: object) -> "MealItem | None":
        if not isinstance(m, dict):
            return None
        try:
            return MealItem(
                name=str(m.get("name", "Meal")),
                calories=float(m.get("calories") or 0),
                protein_g=float(m.get("protein_g") or 0),
                carbs_g=float(m.get("carbs_g") or 0),
                fat_g=float(m.get("fat_g") or 0),
            )
        except (TypeError, ValueError):
            return None

    try:
        weekly: list[DayMeals] = []
        for i, d in enumerate(days_data[:7]):
            weekly.append(DayMeals(
                day=str(d.get("day", _DAYS[i])),
                breakfast=_parse_meal(d.get("breakfast")),
                lunch=_parse_meal(d.get("lunch")),
                dinner=_parse_meal(d.get("dinner")),
                snack=_parse_meal(d.get("snack")),
            ))
        return weekly
    except Exception:
        return None


def _sanitize_week(weekly: list, forbidden: list) -> tuple[list, list[str]]:
    """Strip any meal that offers a forbidden food. Returns (plan, what went).

    Applied to the AI plan AND to the deterministic template, because the
    template is static text that was never checked against a patient profile:
    its renal week serves "Cream of wheat with blueberries" and "Waffles with
    strawberries" to whoever asks.

    A removed slot is reported, never left as a silent blank — the patient has
    to know the plan is short because of their allergy, not because the app
    lost a meal.
    """
    if not forbidden:
        return weekly, []

    removed: list[str] = []
    for day in weekly:
        for slot in ("breakfast", "lunch", "dinner", "snack"):
            meal = getattr(day, slot, None)
            name = getattr(meal, "name", None)
            if not name:
                continue
            hits = food_safety.violations(name, forbidden)
            if hits:
                removed.append(f"{day.day} {slot}: {name} ({hits[0].reason})")
                setattr(day, slot, None)
    return weekly, removed


async def _ollama_generate_exercise_plan(
    user: "User",
    ctx: dict,
    level: str,
) -> "list[DayWorkout] | None":
    """Ask Ollama to generate a personalised 7-day exercise plan. Returns None on any failure."""
    conditions_str = "; ".join(c.name for c in ctx["conditions"]) or "None reported"

    # Case-insensitively: this column holds both "THURSDAY" and "Thursday", so
    # a case-sensitive check lists the same weekday twice (canon §3aa, which
    # learned it from "Calcium Carbonate" vs "Calcium carbonate").
    dialysis_days: list[str] = []
    seen_days: set[str] = set()
    for ts in ctx["therapy_sessions"]:
        dw = (getattr(ts, "day_of_week", None) or "").strip()
        if dw and dw.lower() not in seen_days:
            seen_days.add(dw.lower())
            dialysis_days.append(dw.title())
    dialysis_str = ", ".join(dialysis_days) if dialysis_days else "none detected"

    ex_schema = '{"name":"Push-ups","type":"strength","sets":3,"reps":10}'
    day_schema = f'{{"day":"Monday","focus":"upper_body","total_minutes":45,"exercises":[{ex_schema}]}}'
    prompt = (
        f"You are a certified exercise physiologist. Generate a personalized 7-day exercise plan.\n\n"
        f"{_patient_block(user, ctx)}\n\n"
        f"CHRONIC CONDITIONS: {conditions_str}\n"
        f"FITNESS LEVEL: {level}\n"
        f"DIALYSIS DAYS (if applicable): {dialysis_str}\n\n"
        f"RULES:\n"
        f"1. Output ONLY a valid JSON array. No markdown, no code fences, no explanation.\n"
        f"2. Exactly 7 objects (Monday-Sunday), each matching: {day_schema}\n"
        f"3. Valid 'type' values: warmup, cardio, strength, flexibility, cooldown.\n"
        f"4. Each exercise must have 'name' and 'type'. Optional: sets, reps, duration_minutes, notes.\n"
        f"5. If patient has ESRD/CKD/dialysis/kidney disease:\n"
        f"   - Light to moderate exercise only (walking, gentle cycling, chair exercises, stretching).\n"
        f"   - Avoid heavy lifting (protects AV fistula, prevents hernias).\n"
        f"   - On dialysis days ({dialysis_str}): rest or very light stretching only (max 15 min).\n"
        f"6. If 'beginner': gentle exercises, 20-30 min/session.\n"
        f"7. If 'advanced': higher intensity, 45-60 min/session, compound movements.\n"
        f"8. Include at least 1-2 rest/recovery days.\n\n"
        f"Output only the JSON array:"
    )

    # Routed through ALAFIAModel (Ollama → OpenAI fallback). Freeform output —
    # the model returns a JSON array, which is extracted below.
    from app.services.alafia_model_service import alafia_chat, ALAFIAModelError
    try:
        raw = (await alafia_chat(
            [{"role": "user", "content": prompt}], temperature=0.4, max_tokens=2048,
        )).strip()
    except ALAFIAModelError as exc:
        # Falling back to a deterministic template is deliberate: the user
        # still gets a plan. But the reason has to reach the logs, or a
        # provider that has been down for weeks is indistinguishable from
        # "the template was fine".
        logger.warning("Planner: model unavailable, using template fallback: %s", exc)
        return None

    try:
        start = raw.index("[")
        end = raw.rindex("]") + 1
        days_data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(days_data, list) or len(days_data) < 7:
        return None

    def _parse_exercise(e: object) -> "ExerciseItem | None":
        if not isinstance(e, dict):
            return None
        try:
            return ExerciseItem(
                name=str(e.get("name", "Exercise")),
                type=str(e.get("type", "strength")),
                sets=int(e["sets"]) if "sets" in e else None,
                reps=int(e["reps"]) if "reps" in e else None,
                duration_minutes=int(e["duration_minutes"]) if "duration_minutes" in e else None,
                notes=str(e["notes"]) if "notes" in e else None,
            )
        except (TypeError, ValueError):
            return None

    try:
        weekly: list[DayWorkout] = []
        for i, d in enumerate(days_data[:7]):
            raw_exs = d.get("exercises") or []
            exercises = [ex for ex in (_parse_exercise(e) for e in raw_exs) if ex]
            weekly.append(DayWorkout(
                day=str(d.get("day", _DAYS[i])),
                focus=str(d.get("focus", "general")),
                total_minutes=int(d.get("total_minutes") or 0),
                exercises=exercises,
            ))
        return weekly
    except Exception:
        return None


# ── AI Meal Suggestions (goals + pantry aware) ────────────────────────────────


def _parse_pantry_text(text_val: str | None) -> list[str]:
    """Split free-text pantry input into clean, de-duplicated item names."""
    if not text_val:
        return []
    import re as _re
    seen: dict[str, str] = {}
    for part in _re.split(r"[,\n;]+", text_val):
        name = part.strip()
        if name and name.lower() not in seen:
            seen[name.lower()] = name[:255]
    return list(seen.values())


async def _save_pantry_items(db: AsyncSession, user_id: int, names: list[str]) -> int:
    """Upsert pantry item names to the user's profile pantry. Best-effort."""
    if not names:
        return 0
    existing = (await db.execute(
        select(PantryItem.name).where(PantryItem.user_id == user_id)
    )).scalars().all()
    have = {(n or "").lower() for n in existing}
    added = 0
    for name in names:
        if name.lower() in have:
            continue
        db.add(PantryItem(user_id=user_id, name=name, category="other"))
        have.add(name.lower())
        added += 1
    if added:
        await db.flush()
    return added


def _labs_summary(labs: list) -> str:
    out = []
    for lab in labs[:15]:
        val = lab.value if lab.value is not None else lab.value_string
        if val is None:
            continue
        unit = f" {lab.unit}" if lab.unit else ""
        out.append(f"{lab.test_name}: {val}{unit}")
    return "; ".join(out) or "None on file"


async def _generate_meal_suggestions(
    user: "User", ctx: dict, req: MealSuggestionRequest, pantry_names: list[str],
) -> list[MealSuggestion]:
    """Ask the LLM for N pantry- and condition-aware meal suggestions."""
    conditions_str = "; ".join(c.name for c in ctx["conditions"]) or "None reported"
    meds_str = "; ".join(
        f"{m.name} {m.dosage or ''} {m.dosage_unit or ''}".strip() for m in ctx["medications"]
    ) or "None"
    recent_foods = "; ".join(
        n.food_name for n in ctx["nutrition_logs"][:10] if n.food_name
    ) or "Not recorded"
    restrictions = "; ".join(v for v in (
        getattr(user, "dietary_restrictions", None),
        getattr(user, "allergies", None),
        getattr(user, "food_intolerances", None),
    ) if v) or "None"
    labs_str = _labs_summary(ctx.get("labs", []))
    pantry_str = ", ".join(pantry_names) or "None provided"
    count = max(1, min(req.count or 3, 6))

    item_schema = (
        '{"name":"Meal name","meal_type":"breakfast|lunch|dinner|snack",'
        '"description":"1-2 sentences","ingredients":["item with rough qty"],'
        '"pantry_used":["pantry items used"],"missing_items":["ingredients to buy"],'
        '"calories":450,"protein_g":25,"carbs_g":40,"fat_g":15,'
        '"rationale":"why this fits the patient goals/labs/conditions"}'
    )
    prompt = (
        "You are ALAFIA's clinical dietitian. Suggest meals personalised to this patient.\n\n"
        f"{_patient_block(user, ctx)}\n\n"
        f"CHRONIC CONDITIONS: {conditions_str}\n"
        f"ACTIVE MEDICATIONS: {meds_str}\n"
        f"RECENT LAB RESULTS: {labs_str}\n"
        f"ALLERGIES / RESTRICTIONS: {restrictions}\n"
        f"RECENTLY EATEN: {recent_foods}\n"
        f"STATED HEALTH GOALS: {req.health_goals or 'general wellness'}\n"
        f"PREFERENCES / LIKES / DISLIKES: {req.preferences or 'none stated'}\n"
        f"PANTRY / FRIDGE ON HAND: {pantry_str}\n\n"
        "RULES:\n"
        f"1. Output ONLY a valid JSON array of EXACTLY {count} objects, each matching: {item_schema}\n"
        "2. PREFER recipes that use the pantry items on hand; list those exact items in 'pantry_used'.\n"
        "3. Put every ingredient NOT already in the pantry into 'missing_items' (a shopping recommendation).\n"
        "4. Respect ALL allergies/restrictions absolutely; never include a FORBIDDEN "
        "item, in any form or as a substitution. Honour the stated preferences.\n"
        "5. Tailor to the conditions & labs (e.g. renal/CKD -> limit potassium, phosphorus, sodium; "
        "low hemoglobin -> iron-rich foods + vitamin C; low vitamin D / calcium -> fortified or dairy options).\n"
        "6. All calorie/macro fields are numbers; keep ingredient names simple.\n\n"
        "Output only the JSON array:"
    )

    from app.services.alafia_model_service import alafia_chat, ALAFIAModelError
    try:
        raw = (await alafia_chat(
            [{"role": "user", "content": prompt}], temperature=0.5, max_tokens=2600,
        )).strip()
    except ALAFIAModelError:
        # NOT swallowed into []. There is no template fallback on this path, so
        # an empty list becomes a bare 503 and the real cause is lost -- an
        # error rendered as an empty state (CLAUDE.md §3aa). Let it propagate;
        # the endpoint turns it into a 503 that names the reason.
        logger.error("Meal suggestions: model unavailable", exc_info=True)
        raise

    try:
        items = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    except (ValueError, json.JSONDecodeError):
        return []
    if not isinstance(items, list):
        return []

    def _strlist(v) -> list[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    out: list[MealSuggestion] = []
    for it in items[:count]:
        if not isinstance(it, dict):
            continue
        out.append(MealSuggestion(
            name=str(it.get("name", "Meal")),
            meal_type=str(it.get("meal_type", "meal")),
            description=str(it.get("description", "")),
            ingredients=_strlist(it.get("ingredients")),
            pantry_used=_strlist(it.get("pantry_used")),
            missing_items=_strlist(it.get("missing_items")),
            calories=_num(it.get("calories")),
            protein_g=_num(it.get("protein_g")),
            carbs_g=_num(it.get("carbs_g")),
            fat_g=_num(it.get("fat_g")),
            rationale=str(it.get("rationale", "")),
        ))
    return out


@router.post("/meal-suggestions", response_model=MealSuggestionsResponse)
async def generate_meal_suggestions(
    request: MealSuggestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Personalised meal suggestions from the patient's medical history, current
    state (labs/conditions/meds), preferences and on-hand pantry — with shopping
    recommendations for any missing ingredients. The pantry list is saved to the
    user's profile for reuse."""
    ctx = await _gather_planner_context(current_user.id, db)

    # Persist the submitted pantry to the profile, then assemble the on-hand list
    submitted = _parse_pantry_text(request.pantry_items)
    try:
        pantry_saved = await _save_pantry_items(db, current_user.id, submitted)
    except Exception:
        pantry_saved = 0
    pantry_names = submitted or [p.name for p in ctx.get("pantry", [])]

    try:
        suggestions = await _generate_meal_suggestions(current_user, ctx, request, pantry_names)
    except ALAFIAModelError as exc:
        # Name the reason. "Unavailable right now" sent the operator looking for
        # a down service when the model was actually up and answering — it was
        # just slower than the client's timeout.
        logger.error("Meal suggestions failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"The AI meal engine could not complete this request: {exc}",
        )
    if not suggestions:
        # Distinct from the failure above: the model answered, but nothing
        # usable could be parsed out of it.
        raise HTTPException(
            status_code=502,
            detail="The AI meal engine returned no usable suggestions. Please try again.",
        )

    # A suggestion naming a food the patient reacts to must not be shown. The
    # name, description and the ingredient list are all checked: the allergen
    # is as likely to be an ingredient as it is to be in the title.
    forbidden = ctx.get("forbidden") or []
    blocked: list[str] = []
    if forbidden:
        kept = []
        for sg in suggestions:
            text = " ".join([
                sg.name or "",
                sg.description or "",
                " ".join(sg.ingredients or []),
                " ".join(sg.missing_items or []),
            ])
            hits = food_safety.violations(text, forbidden)
            if hits:
                blocked.append(f"{sg.name} ({hits[0].reason})")
            else:
                kept.append(sg)
        suggestions = kept

    if blocked:
        logger.warning(
            "Planner: blocked %d unsafe suggestion(s) for user %s: %s",
            len(blocked), current_user.id, "; ".join(blocked),
        )
    if not suggestions:
        # Every suggestion was unsafe. Saying "no suggestions" here would be the
        # empty state hiding a real finding — the patient is owed the reason.
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Every suggestion returned contained something you react to, "
                           "so none could be shown. Please try again.",
                "blocked": blocked,
            },
        )

    # Aggregate unique missing items into one shopping list
    shopping: list[str] = []
    seen: set[str] = set()
    for s in suggestions:
        for item in s.missing_items:
            if item.lower() not in seen:
                seen.add(item.lower())
                shopping.append(item)

    advice = (
        f"{len(suggestions)} suggestions tuned to your goals"
        + (f" ({len(blocked)} removed for your allergies)" if blocked else "")
        + (" and active conditions" if ctx["conditions"] else "")
        + ". Items you already have are used first; the shopping list covers what's missing."
    )
    return MealSuggestionsResponse(
        goals=request.health_goals,
        suggestions=suggestions,
        shopping_list=shopping,
        advice=advice,
        used_ai=True,
        pantry_saved=pantry_saved,
    )


# ── Route handlers ────────────────────────────────────────────────────────────


@router.post("/meal-plan", response_model=MealPlanResponse)
async def generate_meal_plan(
    request: MealPlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a personalized 7-day meal plan via AI with deterministic template fallback."""
    ctx = await _gather_planner_context(current_user.id, db)
    pattern = _detect_diet_pattern(ctx["conditions"], request.dietary_pattern)

    # Attempt AI-generated plan
    weekly_plan = await _ollama_generate_meal_plan(current_user, ctx, pattern)
    used_ai = weekly_plan is not None

    # Fall back to template
    if not weekly_plan:
        tmpl = MEAL_TEMPLATES.get(pattern) or MEAL_TEMPLATES["balanced"]
        # deepcopy: the templates are module-level singletons, and sanitising
        # in place would permanently delete a meal from every future patient's
        # plan for the lifetime of the process.
        weekly_plan = [d.model_copy(deep=True) for d in tmpl.values()]

    forbidden = ctx.get("forbidden") or []
    weekly_plan, removed = _sanitize_week(weekly_plan, forbidden)
    if removed:
        # The model was handed an explicit FORBIDDEN list and used one anyway
        # (or the static template did). Worth a log line either way.
        logger.warning(
            "Planner: removed %d unsafe meal(s) for user %s: %s",
            len(removed), current_user.id, "; ".join(removed),
        )

    shopping = [
        item for item in SHOPPING_LISTS.get(pattern, SHOPPING_LISTS["balanced"])
        if food_safety.is_safe(item, forbidden)
    ]
    avg_cal = sum(
        (d.breakfast.calories or 0) + (d.lunch.calories or 0) + (d.dinner.calories or 0)
        for d in weekly_plan
        if d.breakfast and d.lunch and d.dinner
    ) / max(len(weekly_plan), 1)

    start = date.today()
    end = start + timedelta(days=request.days - 1)
    plan_name = f"{'AI-Personalized' if used_ai else pattern.replace('_', ' ').title()} Meal Plan"

    advice_parts = [f"This {pattern} meal plan averages ~{avg_cal:.0f} calories/day."]
    if pattern == "renal":
        advice_parts.append(
            "Low potassium, phosphorus, and sodium for renal health. "
            "Consult your dietitian before making changes."
        )
    elif pattern == "diabetic":
        advice_parts.append("Low glycemic index focus. Spread carbohydrates evenly across meals.")
    else:
        advice_parts.append("Adjust portions based on your daily calorie goals.")
    if used_ai:
        advice_parts.append(
            "This plan was personalised by AI based on your health conditions and medications."
        )
    if removed:
        advice_parts.append(
            f"{len(removed)} suggested item(s) were removed because they contain "
            f"something you react to: " + "; ".join(removed) + ". "
            "Those meal slots are empty for that reason, not by mistake."
        )

    plan_obj = MealPlanModel(
        user_id=current_user.id,
        plan_name=plan_name,
        dietary_pattern=pattern,
        start_date=start,
        end_date=end,
        plan_data=json.dumps([d.model_dump() for d in weekly_plan]),
        shopping_list=json.dumps(shopping),
        advice=" ".join(advice_parts),
        total_daily_calories=avg_cal,
    )
    db.add(plan_obj)
    await db.flush()
    await db.refresh(plan_obj)

    return MealPlanResponse(
        id=plan_obj.id, plan_name=plan_name, dietary_pattern=pattern,
        start_date=start, end_date=end, weekly_plan=weekly_plan,
        shopping_list=shopping, advice=" ".join(advice_parts),
        total_daily_calories=avg_cal, created_at=plan_obj.created_at,
    )


@router.get("/meal-plans", response_model=list[MealPlanResponse])
async def list_meal_plans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MealPlanModel)
        .where(MealPlanModel.user_id == current_user.id)
        .order_by(desc(MealPlanModel.created_at))
        .limit(10)
    )
    plans = result.scalars().all()
    out = []
    for p in plans:
        out.append(MealPlanResponse(
            id=p.id, plan_name=p.plan_name, dietary_pattern=p.dietary_pattern,
            start_date=p.start_date, end_date=p.end_date,
            weekly_plan=json.loads(p.plan_data) if p.plan_data else [],
            shopping_list=json.loads(p.shopping_list) if p.shopping_list else [],
            advice=p.advice, total_daily_calories=p.total_daily_calories,
            created_at=p.created_at,
        ))
    return out


@router.post("/exercise-plan", response_model=ExercisePlanResponse)
async def generate_exercise_plan(
    request: ExercisePlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a personalized 7-day exercise plan via AI with deterministic template fallback."""
    ctx = await _gather_planner_context(current_user.id, db)
    level = request.fitness_level if request.fitness_level in EXERCISE_TEMPLATES else "moderate"

    # Safety cap: ESRD/dialysis patients should not do advanced exercise
    has_renal = any(
        any(kw in (c.name or "").lower() for kw in _DIET_KEYWORDS["renal"])
        for c in ctx["conditions"]
    )
    if has_renal and level == "advanced":
        level = "moderate"

    # Attempt AI-generated plan
    weekly_plan = await _ollama_generate_exercise_plan(current_user, ctx, level)
    used_ai = weekly_plan is not None

    if not weekly_plan:
        weekly_plan = EXERCISE_TEMPLATES.get(level, EXERCISE_TEMPLATES["moderate"])

    total_mins = sum(d.total_minutes or 0 for d in weekly_plan)
    start = date.today()
    end = start + timedelta(days=request.days - 1)
    plan_name = f"{'AI-Personalized' if used_ai else level.title()} Exercise Plan"

    advice_parts = [f"This {level}-level plan includes ~{total_mins} minutes of exercise per week."]
    if has_renal:
        advice_parts.append(
            "Modified for kidney health: light-to-moderate intensity. "
            "Avoid heavy lifting to protect vascular access."
        )
    elif level == "beginner":
        advice_parts.append("Focus on form and consistency. Increase intensity gradually.")
    elif level == "advanced":
        advice_parts.append("Ensure adequate recovery. Adjust weights to maintain proper form.")
    else:
        advice_parts.append("Balance challenge and recovery for optimal results.")
    if used_ai:
        advice_parts.append(
            "This plan was personalised by AI based on your health profile and dialysis schedule."
        )

    plan_obj = ExercisePlanModel(
        user_id=current_user.id,
        plan_name=plan_name,
        fitness_level=level,
        start_date=start,
        end_date=end,
        plan_data=json.dumps([d.model_dump() for d in weekly_plan]),
        advice=" ".join(advice_parts),
        weekly_minutes_target=total_mins,
    )
    db.add(plan_obj)
    await db.flush()
    await db.refresh(plan_obj)

    return ExercisePlanResponse(
        id=plan_obj.id, plan_name=plan_name, fitness_level=level,
        start_date=start, end_date=end, weekly_plan=weekly_plan,
        advice=" ".join(advice_parts), weekly_minutes_target=total_mins,
        created_at=plan_obj.created_at,
    )


@router.delete("/exercise-plans/{plan_id}", status_code=204)
async def delete_exercise_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one of this user's exercise plans.

    The web planner has always had a delete button and it always 404'd: the
    route did not exist. Plans ARE persisted (`ExercisePlanModel`), so the
    button was right and the backend was simply missing.

    Scoped by `user_id` as well as id, so a valid plan id belonging to somebody
    else is a 404 rather than a delete — ownership is part of the lookup, never
    a separate check that can be forgotten.
    """
    plan = (await db.execute(
        select(ExercisePlanModel).where(
            ExercisePlanModel.id == plan_id,
            ExercisePlanModel.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Exercise plan not found")
    await db.delete(plan)
    return None


@router.get("/exercise-plans", response_model=list[ExercisePlanResponse])
async def list_exercise_plans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExercisePlanModel)
        .where(ExercisePlanModel.user_id == current_user.id)
        .order_by(desc(ExercisePlanModel.created_at))
        .limit(10)
    )
    plans = result.scalars().all()
    out = []
    for p in plans:
        out.append(ExercisePlanResponse(
            id=p.id, plan_name=p.plan_name, fitness_level=p.fitness_level,
            start_date=p.start_date, end_date=p.end_date,
            weekly_plan=json.loads(p.plan_data) if p.plan_data else [],
            advice=p.advice, weekly_minutes_target=p.weekly_minutes_target,
            created_at=p.created_at,
        ))
    return out
