"""Nutrition CRUD endpoints with USDA FoodData Central + AI nutrient estimation."""

from fastapi import APIRouter, Depends, HTTPException, Query
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
    DailySummary,
    NutrientEstimateRequest,
    NutrientEstimateResponse,
    MealEstimateRequest,
    MealEstimateResponse,
    MealComponentResult,
    GoalProgressResponse,
    NutrientGoalProgress,
)
from app.services.nutrient_estimator import estimate_nutrients, estimate_meal_nutrients
from app.services.nutrient_goals_service import compute_goals
from app.services.learned_nutrient_service import (
    record_correction, per_100g_from_total, get_learned,
)
from pydantic import BaseModel

router = APIRouter()


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


@router.get("/nutrient-catalog", response_model=list[NutrientCatalogItem])
async def list_nutrient_catalog(
    current_user: User = Depends(get_current_user),
):
    """Return the full 150+ nutrient reference catalog with RDAs."""
    return get_nutrient_catalog()


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

    progress: list[NutrientGoalProgress] = []
    for g in computed["goals"]:
        current = round(float(aggregated.get(g["key"], 0) or 0), 1)
        goal = g["goal"] or 0
        pct = round((current / goal * 100), 0) if goal else 0
        if g["kind"] == "limit":
            status = "over" if pct > 100 else ("warning" if pct >= 80 else "ok")
        else:  # target
            status = "over" if pct > 110 else ("ok" if pct >= 80 else "low")
        progress.append(NutrientGoalProgress(
            key=g["key"], name=g["name"], unit=g["unit"],
            current=current, goal=goal, kind=g["kind"], pct=pct,
            status=status, priority=g["priority"], rationale=g["rationale"],
        ))

    active_flags = [k for k, v in computed["flags"].items() if v]
    return GoalProgressResponse(
        date=target_date,
        profile_complete=computed["profile_complete"],
        energy_kcal=computed["energy_kcal"],
        conditions=active_flags,
        goals=progress,
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

    # Auto-estimate if no fdc_id AND no calories — use Cache → USDA → AI pipeline
    elif not data.get("fdc_id") and data.get("calories") is None and data.get("food_name"):
        try:
            est = await estimate_nutrients(db, data["food_name"], data.get("serving_size"))
            if est.get("nutrients"):
                nutrients = est["nutrients"]
                for key in DB_COLUMN_KEYS:
                    if data.get(key) is None and key in nutrients:
                        data[key] = nutrients[key]
                # Fill extended nutrients
                extended = data.get("extended_nutrients") or {}
                for key, val in nutrients.items():
                    if key not in DB_COLUMN_KEYS and key not in extended:
                        extended[key] = val
                if extended:
                    data["extended_nutrients"] = extended
                # Store fdc_id if from USDA
                if est.get("fdc_id") and not data.get("fdc_id"):
                    data["fdc_id"] = est["fdc_id"]
        except Exception:
            pass  # Non-critical — log without nutrients

    log = NutritionLog(**data, user_id=current_user.id)
    db.add(log)
    await db.flush()
    await db.refresh(log)

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


@router.patch("/{log_id}", response_model=NutritionLogResponse)
async def update_nutrition_log(
    log_id: int,
    updates: NutritionLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a nutrition log."""
    result = await db.execute(
        select(NutritionLog).where(NutritionLog.id == log_id, NutritionLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Nutrition log not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(log, field, value)
    await db.flush()
    await db.refresh(log)
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
