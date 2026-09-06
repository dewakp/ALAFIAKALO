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

from app.core.config import settings
from app.core.database import async_session
from app.models.nutrition import NutritionLog

logger = logging.getLogger(__name__)

# Generous: nothing is waiting on this, so the only job of the ceiling is to stop
# a wedged dependency pinning a worker forever.
def _enrichment_timeout() -> float:
    """Read the rung at call time so it cannot drift from the ladder in config.

    Was a hardcoded 120.0 while OLLAMA_TIMEOUT was 290 in production — an outer
    rung SHORTER than the inner one, which is the §3ae failure exactly: the inner
    limit becomes unreachable and every cold-model call dies at the wrapper.
    """
    return float(settings.NUTRIENT_ENRICHMENT_TIMEOUT)


async def enrich_log(log_id: int, *, overwrite_zeros: bool = False) -> None:
    """Estimate and store nutrients for an already-saved log. Never raises.

    `overwrite_zeros` is for the one-off repair pass only (see
    `scripts/reestimate_nutrition.py`) and defaults OFF. On the live path a
    stored value always outranks an estimate; but a row left at 0.0 by an
    estimation that failed is not a value the patient chose, and treating it as
    one is why 58 meals on a single record could never heal: the estimate was
    computed each time and then discarded, and the row was stamped `done`.
    """
    try:
        await asyncio.wait_for(_enrich(log_id, overwrite_zeros=overwrite_zeros),
                               timeout=_enrichment_timeout())
    except asyncio.TimeoutError:
        logger.warning("Nutrient enrichment timed out for log %s", log_id)
        await _mark(log_id, "failed")
    except Exception:
        logger.exception("Nutrient enrichment failed for log %s", log_id)
        await _mark(log_id, "failed")


async def _enrich(log_id: int, *, overwrite_zeros: bool = False) -> None:
    from app.core.nutrition_data import DB_COLUMN_KEYS
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

        # EVERY description goes through the meal estimator — including a single
        # item — because it is the only path that scales by the quantity the user
        # actually typed. `estimate_nutrients` returns a per-100 g/mL profile, and
        # storing that unscaled reported "8 Fl oz Boost Glucose Control" as
        # 80 kcal / 6.75 g protein instead of 190 / 16: every value divided by
        # 2.37, the 237 mL serving over 100 mL. For a dialysis patient that
        # understates phosphorus and potassium by the same factor, so it is worse
        # than the "unavailable" the multi-item meals showed — it looks right.
        #
        # (Multi-item still MUST NOT use the single path: that one merges per-100 g
        # densities, which for a list produces an impossible number — CLAUDE.md §3c.)
        meal = await estimate_meal_nutrients(db, log.food_name, notes=log.notes)
        nutrients = meal.get("aggregate_nutrients") or {}
        components = meal.get("components") or []
        # Keep the USDA provenance link when the meal resolved to one known food.
        fdc_id = components[0].get("fdc_id") if len(components) == 1 else None

        if not nutrients:
            # Nothing parsed as a portion (a bare food name, an unusual phrasing).
            # Fall back to the per-100 profile rather than storing nothing.
            est = await estimate_nutrients(db, log.food_name, log.serving_size)
            nutrients = est.get("nutrients") or {}
            fdc_id = est.get("fdc_id")

        if not nutrients:
            log.nutrient_status = "failed"
            await db.commit()
            logger.info("No nutrients resolved for log %s (%r)", log_id, log.food_name[:60])
            return

        # Only fill blanks: anything the user typed themselves outranks an estimate.
        # A repair pass may also replace a stored 0.0 — see `overwrite_zeros`.
        column_keys = set(DB_COLUMN_KEYS)
        for key in column_keys:
            if key not in nutrients:
                continue
            current = getattr(log, key, None)
            if current is None or (overwrite_zeros and current == 0):
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
