"""Fill in a meal's nutrients after it has already been saved.

Nutrient lookup costs seconds — USDA per item, a branded lookup, and an LLM
fallback. Running it inside the save meant the user waited for all of it, and a
10-item meal blew past the web client's 30s timeout. Because the request never
committed, the meal they had typed was lost.

So the write is split: the log is persisted and returned immediately with
`nutrient_status="pending"`, and this runs afterwards.

Two rules this module exists to enforce:

  * It gets its OWN database session. The request's session is closed the moment
    the response is sent; reusing it here raises on first use.
  * It never lets a failure escape. The meal is already saved and correct — a
    nutrient lookup dying must not surface as an error, only as
    `nutrient_status="failed"`, which the client can offer to retry.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.database import async_session
from app.models.nutrition import NutritionLog

logger = logging.getLogger(__name__)

# Generous: nothing is waiting on this, so the only job of the ceiling is to stop
# a wedged dependency pinning a worker forever.
ENRICHMENT_TIMEOUT_SECONDS = 120.0


async def enrich_log(log_id: int) -> None:
    """Estimate and store nutrients for an already-saved log. Never raises."""
    try:
        await asyncio.wait_for(_enrich(log_id), timeout=ENRICHMENT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("Nutrient enrichment timed out for log %s", log_id)
        await _mark(log_id, "failed")
    except Exception:
        logger.exception("Nutrient enrichment failed for log %s", log_id)
        await _mark(log_id, "failed")


async def _enrich(log_id: int) -> None:
    from app.core.nutrition_data import DB_COLUMN_KEYS
    from app.services.nlm_food_extractor import extract_food_items_nlm
    from app.services.nutrient_estimator import estimate_meal_nutrients, estimate_nutrients

    async with async_session() as db:
        log = (await db.execute(
            select(NutritionLog).where(NutritionLog.id == log_id)
        )).scalar_one_or_none()
        if log is None:
            logger.info("Log %s vanished before enrichment", log_id)
            return
        if not log.food_name:
            log.nutrient_status = "skipped"
            await db.commit()
            return

        # Multi-item meals go to the meal estimator, which scales each item by its
        # gram weight and sums to a TOTAL. The single-food path merges per-100 g
        # densities, which for a list produces an impossible number.
        if len(extract_food_items_nlm(log.food_name)) > 1:
            meal = await estimate_meal_nutrients(db, log.food_name)
            nutrients = meal.get("aggregate_nutrients") or {}
            fdc_id = None
        else:
            est = await estimate_nutrients(db, log.food_name, log.serving_size)
            nutrients = est.get("nutrients") or {}
            fdc_id = est.get("fdc_id")

        if not nutrients:
            log.nutrient_status = "failed"
            await db.commit()
            logger.info("No nutrients resolved for log %s (%r)", log_id, log.food_name[:60])
            return

        # Only fill blanks: anything the user typed themselves outranks an estimate.
        column_keys = set(DB_COLUMN_KEYS)
        for key in column_keys:
            if getattr(log, key, None) is None and key in nutrients:
                setattr(log, key, nutrients[key])

        extended = dict(log.extended_nutrients or {})
        for key, value in nutrients.items():
            if key not in column_keys and key not in extended:
                extended[key] = value
        if extended:
            log.extended_nutrients = extended

        if fdc_id and not log.fdc_id:
            log.fdc_id = fdc_id

        log.nutrient_status = "done"
        await db.commit()
        logger.info("Enriched log %s: calories=%s", log_id, getattr(log, "calories", None))


async def _mark(log_id: int, status: str) -> None:
    """Record a terminal status. Best-effort — never raises."""
    try:
        async with async_session() as db:
            log = (await db.execute(
                select(NutritionLog).where(NutritionLog.id == log_id)
            )).scalar_one_or_none()
            if log is not None:
                log.nutrient_status = status
                await db.commit()
    except Exception:
        logger.exception("Could not mark log %s as %s", log_id, status)
