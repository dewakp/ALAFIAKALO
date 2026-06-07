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
)
from app.services.nutrient_estimator import estimate_nutrients, estimate_meal_nutrients

router = APIRouter()


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
    result = await estimate_meal_nutrients(db, body.description)

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
    # ── Food logs ──
    query = select(NutritionLog).where(
        NutritionLog.user_id == current_user.id,
        NutritionLog.log_date == target_date,
    )
    result = await db.execute(query)
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

    # ── Medication dose nutrients ──
    med_result = await db.execute(
        select(MedicationDoseLog).where(
            MedicationDoseLog.user_id == current_user.id,
            MedicationDoseLog.log_date == target_date,
            MedicationDoseLog.nutrients_resolved.is_(True),
        )
    )
    dose_logs = med_result.scalars().all()
    med_nutrient_contributions: list[dict] = []
    for dose in dose_logs:
        if dose.nutrients_contributed:
            for key, val in dose.nutrients_contributed.items():
                if isinstance(val, (int, float)):
                    aggregated[key] = aggregated.get(key, 0) + val
            med_nutrient_contributions.append({
                "medication_name": dose.medication_name,
                "dose": f"{dose.dose_amount} {dose.dose_unit}",
                "nutrients": dose.nutrients_contributed,
            })

    breakdown = compute_rda_percentages(aggregated)

    return DailySummary(
        date=target_date,
        total_calories=aggregated.get("calories", 0),
        total_protein_g=aggregated.get("protein_g", 0),
        total_carbs_g=aggregated.get("carbs_g", 0),
        total_fat_g=aggregated.get("fat_g", 0),
        meal_count=len(logs),
        nutrients=breakdown,
        medication_nutrient_contributions=med_nutrient_contributions,
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
