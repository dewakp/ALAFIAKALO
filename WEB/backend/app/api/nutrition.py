"""Nutrition CRUD endpoints with USDA FoodData Central + AI nutrient estimation."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.notification_engine import notify_nutrition_restriction
from app.core.nutrition_data import (
    search_usda_foods,
    get_usda_food_detail,
    get_nutrient_catalog,
    compute_rda_percentages,
    DB_COLUMN_KEYS,
)
from app.models.user import User
from app.models.nutrition import NutritionLog
from app.models.med_nutrient import MedicationDoseLog
from app.models.chronic_conditions import ChronicCondition
from app.models.conditions import HealthCondition
from app.schemas.nutrition import (
    NutritionLogCreate,
    NutritionLogUpdate,
    NutritionLogResponse,
    USDAFoodResult,
    USDAFoodDetail,
    NutrientCatalogItem,
    NutrientCatalogPage,
    DailySummary,
    NutrientEstimateRequest,
    NutrientEstimateResponse,
    MealEstimateRequest,
    MealEstimateResponse,
    MealComponentResult,
    DialysisBalance,
    DialysisDaySummary,
    GoalProgressResponse,
    NutrientGoalProgress,
)
from app.services.nutrient_estimator import estimate_nutrients, estimate_meal_nutrients
from app.services.nutrient_enrichment import enrich_log
from app.services.nutrient_goals_service import compute_goals
from app.services import dialysis_context
from app.services.dialysis_day_adjustment import apply_to_totals
from app.services.learned_nutrient_service import (
    record_correction, per_100g_from_total, get_learned,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# Ceiling for in-save nutrient estimation. The web client gives up at 30s, so the
# server must finish well inside that and still have room to commit.
NUTRIENT_ESTIMATE_BUDGET_SECONDS = 15.0


# ── Nutrition learning model — user corrections ───────────────────────────────

class LearnFoodRequest(BaseModel):
    """Teach the estimator a food's correct nutrients.

    Provide either a per-100 g profile, or an absolute total + the grams it covers
    (the per-100 g profile is derived). At minimum include 'calories'.
    """
    food_name: str
    nutrients_per_100g: dict[str, float] | None = None
    nutrients_total: dict[str, float] | None = None
    total_grams: float | None = None
    serving_weight_g: float | None = None


@router.post("/learn")
async def learn_food(
    body: LearnFoodRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a user correction so future estimates for this food are accurate.

    Corrections for the same food are merged into a running average (the learning
    model converges as more feedback arrives) and consulted FIRST by the estimator.
    """
    per100 = body.nutrients_per_100g
    if not per100 and body.nutrients_total and body.total_grams:
        per100 = per_100g_from_total(body.nutrients_total, body.total_grams)
    if not per100:
        raise HTTPException(
            422, "Provide nutrients_per_100g, or nutrients_total + total_grams.")
    if per100.get("calories") is None:
        raise HTTPException(422, "Correction must include 'calories'.")

    row = await record_correction(
        db, body.food_name, per100,
        serving_weight_g=body.serving_weight_g, user_id=current_user.id,
    )
    await db.commit()
    return {
        "ok": True,
        "food_name": row.food_name_original,
        "sample_count": row.sample_count,
        "confidence": row.confidence,
        "nutrients": row.nutrients,
    }


@router.get("/learn/{food_name}")
async def get_learned_food(
    food_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the learned profile for a food (404 if none learned yet)."""
    learned = await get_learned(db, food_name)
    if not learned:
        raise HTTPException(404, "No learned value for this food yet.")
    return learned


async def _aggregate_daily_nutrients(
    db: AsyncSession, user_id: int, target_date: date
) -> tuple[dict[str, float], int, list[dict]]:
    """Sum all food logs + resolved medication-dose nutrients for a date.

    Returns (aggregated nutrient totals, food-log count, med contributions).
    Shared by the daily-summary and goal-progress endpoints.
    """
    result = await db.execute(
        select(NutritionLog).where(
            NutritionLog.user_id == user_id,
            NutritionLog.log_date == target_date,
        )
    )
    logs = result.scalars().all()

    aggregated: dict[str, float] = {}
    for log in logs:
        for key in DB_COLUMN_KEYS:
            val = getattr(log, key, None)
            if val is not None:
                aggregated[key] = aggregated.get(key, 0) + val
        if log.extended_nutrients:
            for key, val in log.extended_nutrients.items():
                if isinstance(val, (int, float)):
                    aggregated[key] = aggregated.get(key, 0) + val

    med_result = await db.execute(
        select(MedicationDoseLog).where(
            MedicationDoseLog.user_id == user_id,
            MedicationDoseLog.log_date == target_date,
            MedicationDoseLog.nutrients_resolved.is_(True),
        )
    )
    med_contributions: list[dict] = []
    for dose in med_result.scalars().all():
        if dose.nutrients_contributed:
            for key, val in dose.nutrients_contributed.items():
                if isinstance(val, (int, float)):
                    aggregated[key] = aggregated.get(key, 0) + val
            med_contributions.append({
                "medication_name": dose.medication_name,
                "dose": f"{dose.dose_amount} {dose.dose_unit}",
                "nutrients": dose.nutrients_contributed,
            })

    return aggregated, len(logs), med_contributions


# ── Nutrient estimation (Cache → USDA → AI) ──


@router.post("/estimate-nutrients", response_model=NutrientEstimateResponse)
async def estimate_food_nutrients(
    body: NutrientEstimateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estimate nutrients for any food.

    Pipeline: local cache → USDA FoodData Central → AI (Ollama / OpenAI).
    AI results are cached for reuse across the entire app.
    """
    result = await estimate_nutrients(db, body.food_name, body.serving_size)
    return NutrientEstimateResponse(**result)


@router.post("/estimate-meal", response_model=MealEstimateResponse)
async def estimate_meal(
    body: MealEstimateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Parse a free-text meal description and return aggregate 150+ nutrients.

    NLM Pipeline:
      1. NLM meal parser extracts (food_name, qty_g) pairs — handles fractions,
         parenthetical recipe ingredients, ethnic/regional food names.
         e.g. "1.5 cup beef suya(peanut butter, pepper, salt, ginger, turmeric)"
         → beef 170 g, peanut butter 16 g, pepper 2.5 g, salt 2.85 g …
      2. Per-item nutrient lookup: Cache → USDA FoodData Central → AI fallback.
         All results are expressed per 100 g.
      3. Scale each item's 100 g profile to its actual gram weight.
      4. Sum scaled nutrients across all items → meal-level aggregate.

    If ``log_date`` and ``meal_type`` are provided the aggregated result is
    saved as a ``NutritionLog`` and ``log_id`` is returned in the response.
    """
    result = await estimate_meal_nutrients(
        db, body.description,
        country=current_user.country,
        preferred_units=current_user.preferred_units,
        locale=current_user.locale,
    )

    log_id: int | None = None

    # Optionally persist as a NutritionLog
    if body.log_date and body.meal_type:
        agg = result["aggregate_nutrients"]
        log_data: dict = {
            "user_id": current_user.id,
            "log_date": body.log_date,
            "meal_type": body.meal_type,
            "food_name": body.description[:500],
            "serving_size": f"composite meal ({result['total_weight_g']:.0f} g total)",
            # The status is what the clients render, NOT whether calories is
            # null: §3c has all three showing "estimating…"/"unavailable" from
            # this field. Re-analyze wrote the nutrients and left the status at
            # whatever the failed background pass had set, so a meal that now
            # resolved kept reporting "unavailable" with correct numbers sitting
            # in the row underneath.
            "nutrient_status": "done" if result.get("aggregate_nutrients") else "failed",
        }
        for key in DB_COLUMN_KEYS:
            if key in agg:
                log_data[key] = agg[key]
        extended = {k: v for k, v in agg.items() if k not in set(DB_COLUMN_KEYS)}
        if extended:
            log_data["extended_nutrients"] = extended

        # Get-or-update: avoid creating a duplicate row when this meal was
        # already logged (e.g. synced from Firebase as an unresolved shell, or
        # previously estimated). Match on (user, date, meal_type, food_name) and
        # update that row with the freshly resolved nutrients instead of
        # inserting a second row.
        existing_q = await db.execute(
            select(NutritionLog).where(
                NutritionLog.user_id == current_user.id,
                NutritionLog.log_date == body.log_date,
                NutritionLog.meal_type == body.meal_type,
                NutritionLog.food_name == body.description[:500],
            )
        )
        log = existing_q.scalars().first()
        if log is not None:
            for field, value in log_data.items():
                if field in ("user_id", "log_date", "meal_type", "food_name"):
                    continue
                setattr(log, field, value)
        else:
            log = NutritionLog(**log_data)
            db.add(log)
        await db.flush()
        await db.refresh(log)
        log_id = log.id

        # Notify on key nutrient limit breaches (same thresholds as single-food log)
        _LIMITS = {
            "sodium_mg": ("Sodium", 2300, "mg"),
            "potassium_mg": ("Potassium", 4700, "mg"),
            "phosphorus_mg": ("Phosphorus", 1000, "mg"),
            "sugar_g": ("Sugar", 50, "g"),
        }
        for field, (label, limit, unit) in _LIMITS.items():
            val = agg.get(field)
            if val is not None and val > limit:
                await notify_nutrition_restriction(
                    db, user_id=current_user.id, nutrient=label,
                    logged_value=f"{val:.1f} {unit}", limit_value=f"{limit} {unit}",
                    log_id=log_id,
                )

    return MealEstimateResponse(
        description=result["description"],
        components=[MealComponentResult(**c) for c in result["components"]],
        aggregate_nutrients=result["aggregate_nutrients"],
        total_weight_g=result["total_weight_g"],
        log_id=log_id,
    )


# ── USDA search & reference endpoints (placed BEFORE /{log_id} routes) ──


@router.get("/food-search", response_model=list[USDAFoodResult])
async def search_foods(
    q: str = Query(..., min_length=2, description="Search query"),
    page_size: int = Query(25, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    """Search USDA FoodData Central for foods. Returns nutrient profiles per 100g."""
    try:
        results = await search_usda_foods(q, page_size=page_size)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDA API error: {str(e)}")
    return results


@router.get("/food/{fdc_id}", response_model=USDAFoodDetail)
async def get_food_detail(
    fdc_id: int,
    current_user: User = Depends(get_current_user),
):
    """Get full nutrient breakdown for a USDA food by FDC ID."""
    try:
        detail = await get_usda_food_detail(fdc_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDA API error: {str(e)}")
    if not detail:
        raise HTTPException(status_code=404, detail="Food not found in USDA database")
    # Compute %DV breakdown
    breakdown = compute_rda_percentages(detail["nutrients"])
    detail["nutrient_breakdown"] = breakdown
    return detail


@router.get("/nutrient-catalog", response_model=NutrientCatalogPage)
async def list_nutrient_catalog(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    category: str | None = Query(None, description="Filter to one category"),
    search: str | None = Query(None, description="Match on nutrient name or key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The nutrient reference catalog, paginated, with this patient's own goals.

    116 nutrients across 11 categories, each carrying its USDA FoodData Central
    id — the same catalog the estimator fills from, so there is ONE list rather
    than a second one maintained by hand. The meals diary previously rendered 15
    nutrients from a literal in the page, with fixed colour thresholds
    (`phosphorus danger: 1000`) applied to every patient regardless of whether
    they were on dialysis.

    `goal`/`goal_kind` come from `compute_goals`, so the figure a nutrient is
    judged against is the patient's own — the same one the Nutrition screen and
    the health score use.
    """
    from app.services.nutrient_goals_service import compute_goals
    from app.services import clinical_sources as sources

    items = get_nutrient_catalog()

    # This patient's goals, keyed the same way the catalog is. `compute_goals`
    # already emits canonical nutrient keys (`potassium_mg`, `protein_g`), so
    # no translation table is needed — and one that existed was silently
    # dropping potassium.
    goals_by_key: dict[str, dict] = {}
    try:
        conditions = list(await sources.conditions(db, current_user.id, active_only=True))
        payload = compute_goals(
            date_of_birth=str(current_user.date_of_birth) if current_user.date_of_birth else None,
            sex=current_user.gender,
            height_cm=current_user.height_cm,
            current_weight_kg=current_user.current_weight_kg,
            target_weight_kg=current_user.target_weight_kg,
            activity_level=current_user.activity_level,
            conditions=conditions,
        )
        for g in payload.get("goals") or []:
            key = str(g.get("key") or "").strip()
            if key:
                goals_by_key[key] = g
    except Exception:  # noqa: BLE001 - a missing goal must not hide the catalog
        logger.warning("Could not compute nutrient goals for the catalog", exc_info=True)

    categories = sorted({i["category"] for i in items if i.get("category")})

    if category:
        items = [i for i in items if (i.get("category") or "").lower() == category.lower()]
    if search:
        needle = search.strip().lower()
        items = [i for i in items
                 if needle in i["name"].lower() or needle in i["key"].lower()]

    total = len(items)
    start = (page - 1) * page_size
    window = items[start:start + page_size]

    enriched = []
    for i in window:
        goal = goals_by_key.get(i["key"])
        enriched.append({
            **i,
            "goal": goal.get("goal") if goal else None,
            "goal_kind": goal.get("kind") if goal else None,
        })

    return {
        "items": enriched,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, -(-total // page_size)),
        "categories": categories,
    }


@router.get("/daily-summary", response_model=DailySummary)
async def get_daily_summary(
    target_date: date = Query(..., alias="date"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate all nutrition logs + medication dose nutrients for a date.

    Includes nutrients contributed by medications logged via the
    /medications/dose-logs endpoint (e.g. Calcitriol → vitamin D,
    Tums → calcium, Fish Oil → omega-3).
    """
    aggregated, log_count, med_nutrient_contributions = await _aggregate_daily_nutrients(
        db, current_user.id, target_date
    )
    breakdown = compute_rda_percentages(aggregated)

    return DailySummary(
        date=target_date,
        total_calories=aggregated.get("calories", 0),
        total_protein_g=aggregated.get("protein_g", 0),
        total_carbs_g=aggregated.get("carbs_g", 0),
        total_fat_g=aggregated.get("fat_g", 0),
        meal_count=log_count,
        nutrients=breakdown,
        medication_nutrient_contributions=med_nutrient_contributions,
    )


@router.get("/goal-progress", response_model=GoalProgressResponse)
async def get_goal_progress(
    target_date: date = Query(..., alias="date"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Running daily nutrient totals vs. personalized goals/limits.

    Goals are derived from the patient's biology (age, height, weight, target
    weight, sex, activity) and active chronic conditions, grounded in NIH/USDA
    DRIs and clinical guidance (e.g. CKD patients get protein / potassium /
    phosphorus / sodium limits rather than generic targets).
    """
    # Day's running totals (food + medication-derived nutrients)
    aggregated, _, _ = await _aggregate_daily_nutrients(db, current_user.id, target_date)

    # Active conditions from both the chronic-conditions and health-conditions tables
    cc = (await db.execute(
        select(ChronicCondition).where(
            ChronicCondition.user_id == current_user.id,
            ChronicCondition.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    hc = (await db.execute(
        select(HealthCondition).where(
            HealthCondition.user_id == current_user.id,
            HealthCondition.status != "resolved",
        )
    )).scalars().all()
    conditions = list(cc) + list(hc)

    def _json_list(val):
        """Profile fields are stored as JSON arrays (or CSV) of strings."""
        if not val:
            return []
        try:
            import json
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except (ValueError, TypeError):
            return [s.strip() for s in str(val).split(",") if s.strip()]

    computed = compute_goals(
        date_of_birth=current_user.date_of_birth,
        sex=current_user.gender_at_birth or current_user.gender,
        height_cm=current_user.height_cm,
        current_weight_kg=current_user.current_weight_kg,
        target_weight_kg=current_user.target_weight_kg,
        activity_level=current_user.activity_level,
        conditions=conditions,
        fitness_goals=_json_list(current_user.fitness_goals),
        dietary_preferences=_json_list(current_user.dietary_preferences),
        dietary_restrictions=_json_list(current_user.dietary_restrictions),
        allergies=_json_list(current_user.allergies),
    )

    # Attach the day's intake to each goal so the dialysis layer can work out
    # the balance without re-querying.
    goal_dicts = [
        {**g, "current": round(float(aggregated.get(g["key"], 0) or 0), 1)}
        for g in computed["goals"]
    ]

    # A treatment does not move a limit — KDOQI's figures already assume the
    # patient is on dialysis. It moves the day's balance: solute eaten and then
    # cleared, and calcium crossing in from the bath that was never eaten.
    day_summary = None
    try:
        sessions = await dialysis_context.sessions_for_day(db, current_user.id, target_date)
        if sessions:
            serum = await dialysis_context.latest_serum(db, current_user.id, target_date)
            coefficients = await dialysis_context.coefficients_for(db, current_user.id)
            goal_dicts, day = apply_to_totals(
                goal_dicts, sessions, serum, coefficients, target_date
            )
            day_summary = DialysisDaySummary(
                had_dialysis=day.had_dialysis,
                session_count=day.session_count,
                modelled_mg={k: round(v, 1) for k, v in day.modelled.items()},
                notes=day.notes,
            )
    except Exception:  # noqa: BLE001
        # The nutrient page must still render if the model fails. Losing the
        # dialysis annotation is a degraded view; a 500 is a blank one.
        logger.exception("Dialysis balance could not be applied")

    progress: list[NutrientGoalProgress] = []
    for g in goal_dicts:
        current = g["current"]
        goal = g["goal"] or 0
        pct = round((current / goal * 100), 0) if goal else 0
        if g["kind"] == "limit":
            status = "over" if pct > 100 else ("warning" if pct >= 80 else "ok")
        else:  # target
            status = "over" if pct > 110 else ("ok" if pct >= 80 else "low")
        balance = g.get("dialysis_balance")
        progress.append(NutrientGoalProgress(
            key=g["key"], name=g["name"], unit=g["unit"],
            current=current, goal=goal, kind=g["kind"], pct=pct,
            status=status, priority=g["priority"], rationale=g["rationale"],
            dialysis_balance=DialysisBalance(**balance) if balance else None,
        ))

    active_flags = [k for k, v in computed["flags"].items() if v]
    return GoalProgressResponse(
        date=target_date,
        profile_complete=computed["profile_complete"],
        energy_kcal=computed["energy_kcal"],
        conditions=active_flags,
        goals=progress,
        dialysis=day_summary,
    )


# ── Standard CRUD ──


@router.get("/", response_model=list[NutritionLogResponse])
async def list_nutrition_logs(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    meal_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List nutrition logs with optional date/meal filters."""
    query = select(NutritionLog).where(NutritionLog.user_id == current_user.id)
    if start_date:
        query = query.where(NutritionLog.log_date >= start_date)
    if end_date:
        query = query.where(NutritionLog.log_date <= end_date)
    if meal_type:
        query = query.where(NutritionLog.meal_type == meal_type)
    query = query.order_by(NutritionLog.log_date.desc(), NutritionLog.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=NutritionLogResponse, status_code=201)
async def create_nutrition_log(
    log_in: NutritionLogCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a nutrition log. If fdc_id is provided and nutrient fields are empty,
    auto-populate from USDA FoodData Central.
    If no fdc_id and no calories, auto-estimate via Cache → USDA → AI pipeline."""
    data = log_in.model_dump()

    # Auto-populate from USDA if fdc_id given and no calories specified
    if data.get("fdc_id") and data.get("calories") is None:
        try:
            detail = await get_usda_food_detail(data["fdc_id"])
            if detail:
                usda_nutrients = detail["nutrients"]
                # Fill DB columns
                for key in DB_COLUMN_KEYS:
                    if data.get(key) is None and key in usda_nutrients:
                        data[key] = usda_nutrients[key]
                # Fill extended nutrients
                extended = data.get("extended_nutrients") or {}
                for key, val in usda_nutrients.items():
                    if key not in DB_COLUMN_KEYS and key not in extended:
                        extended[key] = val
                if extended:
                    data["extended_nutrients"] = extended
        except Exception:
            pass  # Non-critical — just skip auto-population

    # Nutrients are NOT looked up here.
    #
    # The lookup costs seconds (USDA per item, branded, then an LLM fallback).
    # Doing it inline meant the user waited for all of it, and a 10-item meal
    # exceeded the web client's 30s timeout — and because the request had not
    # committed, the meal they had typed was LOST.
    #
    # The log is saved and returned immediately instead, and enrichment runs in
    # the background. `nutrient_status` tells the client whether values are still
    # coming, so it can poll or show a placeholder rather than a wrong zero.
    needs_enrichment = bool(
        not data.get("fdc_id") and data.get("calories") is None and data.get("food_name")
    )
    data["nutrient_status"] = "pending" if needs_enrichment else "skipped"

    log = NutritionLog(**data, user_id=current_user.id)
    db.add(log)
    await db.flush()
    await db.refresh(log)

    if needs_enrichment:
        # Queued AFTER the response is sent, with its own DB session — the
        # request's session is closed by then.
        background_tasks.add_task(enrich_log, log.id)

    # Notification: check key nutrients against common clinical limits
    _LIMITS = {
        "sodium_mg": ("Sodium", 2300, "mg"),
        "potassium_mg": ("Potassium", 4700, "mg"),
        "phosphorus_mg": ("Phosphorus", 1000, "mg"),
        "sugar_g": ("Sugar", 50, "g"),
    }
    for field, (label, limit, unit) in _LIMITS.items():
        val = getattr(log, field, None)
        if val is not None and val > limit:
            await notify_nutrition_restriction(
                db, user_id=current_user.id, nutrient=label,
                logged_value=f"{val} {unit}", limit_value=f"{limit} {unit}",
                log_id=log.id,
            )

    return log


@router.get("/{log_id}", response_model=NutritionLogResponse)
async def get_nutrition_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific nutrition log."""
    result = await db.execute(
        select(NutritionLog).where(NutritionLog.id == log_id, NutritionLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Nutrition log not found")
    return log


@router.get("/{log_id}/breakdown")
async def get_log_nutrient_breakdown(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute %DV nutrient breakdown from a stored nutrition log's data."""
    result = await db.execute(
        select(NutritionLog).where(NutritionLog.id == log_id, NutritionLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Nutrition log not found")

    # Collect all stored nutrients
    nutrients: dict[str, float] = {}
    for key in DB_COLUMN_KEYS:
        val = getattr(log, key, None)
        if val is not None:
            nutrients[key] = val
    if log.extended_nutrients:
        for key, val in log.extended_nutrients.items():
            if isinstance(val, (int, float)):
                nutrients[key] = val

    breakdown = compute_rda_percentages(nutrients)
    return {
        "log_id": log.id,
        "food_name": log.food_name,
        "meal_type": log.meal_type,
        "serving_size": log.serving_size,
        "fdc_id": log.fdc_id,
        "nutrient_breakdown": breakdown,
    }


#: Every column the enricher fills, derived FROM THE MODEL rather than typed
#: out. A hand-written list goes stale the moment a nutrient is added, and the
#: stale one would be the value left sitting on an edited row — the exact
#: failure this clearing exists to prevent.
_NON_NUTRIENT_COLUMNS = {
    "id", "user_id", "log_date", "meal_type", "food_name", "serving_size",
    "fdc_id", "notes", "created_at", "start_time", "end_time",
    "pre_meal_weight_kg", "post_meal_weight_kg", "recipe_url",
    "food_image_uris", "nutrient_status", "extended_nutrients",
}
_ENRICHED_NUTRIENT_COLUMNS = tuple(
    c.name for c in NutritionLog.__table__.columns
    if c.name not in _NON_NUTRIENT_COLUMNS
)


@router.patch("/{log_id}", response_model=NutritionLogResponse)
async def update_nutrition_log(
    log_id: int,
    updates: NutritionLogUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a nutrition log, re-estimating when the food itself changed.

    This used to apply the fields and stop, so editing the DESCRIPTION left the
    previous nutrients attached to it. A patient who corrected

        "1 ripe plantain, 2 eggs, 4 olives …"        413 kcal

    to a quarter portion

        "0.25 x (1 ripe plantain, 2 eggs, 4 olives …)"

    saw the same 413 kcal, 697 mg of potassium and 372 mg of cholesterol — the
    old meal's numbers, displayed against the new text as though they had been
    recalculated. Stale values that look computed are worse than none, and on a
    dialysis patient a 4x overstatement of potassium is a clinical error.

    Server-side on purpose: web, iOS and Android all PATCH this route, so the
    guarantee belongs here rather than in three clients (canon 3).
    """
    result = await db.execute(
        select(NutritionLog).where(NutritionLog.id == log_id, NutritionLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Nutrition log not found")

    fields = updates.model_dump(exclude_unset=True)
    previous_name = log.food_name

    for field, value in fields.items():
        setattr(log, field, value)

    # Did the food itself change, without the caller supplying fresh numbers?
    new_name = fields.get("food_name")
    name_changed = bool(new_name) and (new_name or "").strip() != (previous_name or "").strip()
    supplied_nutrients = any(
        fields.get(k) is not None for k in ("calories", "protein_g", "carbs_g", "fat_g")
    )

    if name_changed and not supplied_nutrients and not fields.get("fdc_id"):
        # Clear what no longer describes this row rather than leaving it to be
        # read as fact. `pending` is what the clients already render as
        # "estimating…", so this reuses the path the create flow established
        # instead of inventing a second one.
        for column in _ENRICHED_NUTRIENT_COLUMNS:
            if hasattr(log, column):
                setattr(log, column, None)
        log.nutrient_status = "pending"

    await db.flush()
    await db.refresh(log)

    if log.nutrient_status == "pending":
        background_tasks.add_task(enrich_log, log.id)

    return log


@router.delete("/{log_id}", status_code=204)
async def delete_nutrition_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a nutrition log."""
    result = await db.execute(
        select(NutritionLog).where(NutritionLog.id == log_id, NutritionLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Nutrition log not found")
    raise HTTPException(
        status_code=403,
        detail="Nutrition entries cannot be deleted. You can modify this entry instead.",
    )


# ── Believability review queue (admin) ────────────────────────────────────────
# Estimates that failed the category-band check are logged to `flagged_estimates`
# by the self-correcting estimator. These endpoints let an admin/dietitian review
# them and promote a corrected value into the learning model.

@router.get("/admin/flagged-estimates")
async def list_flagged_estimates(
    include_reviewed: bool = Query(False),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List nutrient estimates flagged as out-of-band (admin)."""
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(403, "Administrator privileges required")
    from app.models.flagged_estimate import FlaggedEstimate
    stmt = select(FlaggedEstimate)
    if not include_reviewed:
        stmt = stmt.where(FlaggedEstimate.reviewed.is_(False))
    stmt = stmt.order_by(FlaggedEstimate.occurrences.desc(),
                         FlaggedEstimate.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [{
        "id": r.id,
        "food_name": r.food_name,
        "category": r.category,
        "kcal_per_100g": r.kcal_per_100g,
        "expected_kcal_low": r.expected_kcal_low,
        "expected_kcal_high": r.expected_kcal_high,
        "reason": r.reason,
        "source": r.source,
        "confidence": r.confidence,
        "occurrences": r.occurrences,
        "reviewed": r.reviewed,
        "nutrients": r.nutrients,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.post("/admin/flagged-estimates/{flag_id}/resolve")
async def resolve_flagged_estimate(
    flag_id: int,
    payload: dict | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a flagged estimate reviewed; optionally promote a corrected per-100 g
    profile into the learning model so future lookups are authoritative (admin).

    Body (optional): {"nutrients": {per-100 g profile}, "serving_weight_g": 100}
    """
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(403, "Administrator privileges required")
    from app.models.flagged_estimate import FlaggedEstimate
    row = (await db.execute(
        select(FlaggedEstimate).where(FlaggedEstimate.id == flag_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Flagged estimate not found")

    promoted = False
    corrected = (payload or {}).get("nutrients")
    if corrected:
        from app.services.learned_nutrient_service import record_correction
        await record_correction(
            db, row.food_name, corrected,
            serving_weight_g=(payload or {}).get("serving_weight_g"),
            user_id=current_user.id, source="user_correction",
        )
        promoted = True

    row.reviewed = True
    await db.flush()
    return {"id": row.id, "reviewed": True, "promoted_to_learning": promoted}


# ── Recipe URL analysis (third meal input: URL / description / photo) ────────


class RecipeAnalyzeRequest(BaseModel):
    url: str
    servings: int | None = None      # override the page's stated yield


class RecipeAnalyzeResponse(BaseModel):
    name: str
    url: str
    servings: int
    ingredients: list[str]
    per_serving: dict                # calories / protein_g / carbs_g / fat_g …
    total: dict                      # whole recipe
    total_weight_g: float
    source: str                      # "published" (page nutrition) | "estimated"
    learned: bool                    # dish recorded into learned_food_nutrients
    components: list[dict]           # per-ingredient estimates


@router.post("/recipe-analyze", response_model=RecipeAnalyzeResponse)
async def analyze_recipe_url(
    body: RecipeAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze a recipe URL: parse its schema.org Recipe data, price the
    ingredient list through the believability pipeline, and return per-serving
    nutrition.

    Learning: when the page publishes its own nutrition, that authoritative
    per-serving profile is converted to per-100 g and recorded under the dish
    name (`learned_food_nutrients`, source="recipe") — future descriptions and
    photo labels naming this dish resolve from it.
    """
    from app.services import plausibility
    from app.services.recipe_ingest import RecipeError, fetch_recipe

    try:
        recipe = await fetch_recipe(body.url.strip())
    except RecipeError as e:
        raise HTTPException(status_code=422, detail=str(e))

    servings = body.servings or recipe["servings"]
    servings = max(1, min(int(servings), 64))

    # Price the ingredient list (same estimator as text descriptions).
    description = "; ".join(recipe["ingredients"])
    meal = await estimate_meal_nutrients(
        db, description,
        country=current_user.country,
        preferred_units=current_user.preferred_units,
        locale=current_user.locale,
    )
    total = {k: round(float(v), 2) for k, v in (meal.get("aggregate_nutrients") or {}).items()
             if isinstance(v, (int, float))}
    total_weight = float(meal.get("total_weight_g") or 0)
    components = [
        {"name": c.get("food_name"), "qty_g": c.get("qty_g"),
         "calories": round(float((c.get("nutrients_scaled") or {}).get("calories") or 0), 1)}
        for c in meal.get("components", [])
    ]

    estimated_per_serving = {k: round(v / servings, 2) for k, v in total.items()}

    published = recipe.get("nutrition")
    learned = False
    if published:
        # Published nutrition wins for display; learn it under the dish name.
        per_serving = {**estimated_per_serving, **{k: round(float(v), 2) for k, v in published.items()}}
        serving_g = total_weight / servings if total_weight > 0 and servings else 0
        if serving_g >= 30:      # need a credible serving weight to normalize
            per100 = per_100g_from_total(published, serving_g)
            corrected, _warnings, believable = plausibility.review(recipe["name"], per100)
            if believable:
                await record_correction(
                    db, recipe["name"], corrected,
                    serving_weight_g=round(serving_g, 1),
                    user_id=current_user.id, source="recipe",
                )
                learned = True
        source = "published"
    else:
        per_serving = estimated_per_serving
        source = "estimated"

    return RecipeAnalyzeResponse(
        name=recipe["name"],
        url=body.url.strip(),
        servings=servings,
        ingredients=recipe["ingredients"],
        per_serving=per_serving,
        total=total,
        total_weight_g=round(total_weight, 1),
        source=source,
        learned=learned,
        components=components,
    )
