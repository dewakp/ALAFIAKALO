"""Meal & Exercise Planner endpoints — AI-powered 7-day plans with deterministic fallback."""

import json
import httpx
from datetime import date, timedelta
from fastapi import APIRouter, Depends
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
from app.schemas.wellness import (
    MealPlanRequest, MealPlanResponse, MealItem, DayMeals,
    ExercisePlanRequest, ExercisePlanResponse, ExerciseItem, DayWorkout,
)

router = APIRouter()

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
        name_lc = (cond.condition_name or "").lower()
        for pattern, kws in _DIET_KEYWORDS.items():
            if any(kw in name_lc for kw in kws):
                return pattern
    return user_requested or "balanced"


async def _gather_planner_context(user_id: int, db: AsyncSession) -> dict:
    """Query the DB for data needed to personalise a plan."""
    cond_rows = (await db.execute(
        select(ChronicCondition)
        .where(ChronicCondition.user_id == user_id, ChronicCondition.is_active == True)  # noqa: E712
        .limit(10)
    )).scalars().all()

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
        .order_by(desc(TherapySession.session_date))
        .limit(12)
    )).scalars().all()

    return {
        "conditions": cond_rows,
        "medications": med_rows,
        "nutrition_logs": nutrition_rows,
        "therapy_sessions": therapy_rows,
    }


_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


async def _ollama_generate_meal_plan(
    user: "User",
    ctx: dict,
    pattern: str,
) -> "list[DayMeals] | None":
    """Ask Ollama to generate a personalised 7-day meal plan. Returns None on any failure."""
    conditions_str = "; ".join(c.condition_name for c in ctx["conditions"]) or "None reported"
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
    prompt = (
        f"You are a clinical dietitian. Generate a personalized 7-day meal plan.\n\n"
        f"PATIENT: {user.full_name or 'Patient'}\n"
        f"CHRONIC CONDITIONS: {conditions_str}\n"
        f"ACTIVE MEDICATIONS: {meds_str}\n"
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
        f"6. Respect all allergies and restrictions listed above.\n"
        f"7. Personalise based on recent foods the patient eats.\n\n"
        f"Output only the JSON array:"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            raw = (resp.json().get("response") or "").strip()
    except Exception:
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


async def _ollama_generate_exercise_plan(
    user: "User",
    ctx: dict,
    level: str,
) -> "list[DayWorkout] | None":
    """Ask Ollama to generate a personalised 7-day exercise plan. Returns None on any failure."""
    conditions_str = "; ".join(c.condition_name for c in ctx["conditions"]) or "None reported"

    dialysis_days: list[str] = []
    for ts in ctx["therapy_sessions"]:
        dw = getattr(ts, "day_of_week", None)
        if dw and dw not in dialysis_days:
            dialysis_days.append(dw)
    dialysis_str = ", ".join(dialysis_days) if dialysis_days else "none detected"

    ex_schema = '{"name":"Push-ups","type":"strength","sets":3,"reps":10}'
    day_schema = f'{{"day":"Monday","focus":"upper_body","total_minutes":45,"exercises":[{ex_schema}]}}'
    prompt = (
        f"You are a certified exercise physiologist. Generate a personalized 7-day exercise plan.\n\n"
        f"PATIENT: {user.full_name or 'Patient'}\n"
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

    try:
        async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            raw = (resp.json().get("response") or "").strip()
    except Exception:
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
        weekly_plan = list(tmpl.values())

    shopping = SHOPPING_LISTS.get(pattern, SHOPPING_LISTS["balanced"])
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
        any(kw in (c.condition_name or "").lower() for kw in _DIET_KEYWORDS["renal"])
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
