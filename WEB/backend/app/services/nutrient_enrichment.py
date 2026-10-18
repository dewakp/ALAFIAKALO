# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

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
    from app.services.meal_parser import extract_nutrition_facts
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
        # A printed panel may arrive in EITHER free-text field. `notes` has been
        # read as label text since the estimator was written; `serving_size` was
        # not, and on the row that exposed this the patient had typed the label
        # into both — the obvious places to put "190 Calories, 16 g of Protein".
        # A field a patient fills that nothing reads is a dead control (§3ar),
        # and here it was a dead control on the authoritative source.
        #
        # `notes` keeps precedence: it is the longer field, so it carries the
        # full panel where `serving_size` is usually truncated to what fits.
        # Only text that actually yields a panel is considered, so an ordinary
        # "1 cup" or "composite meal" changes nothing.
        label_text = log.notes
        if not extract_nutrition_facts(label_text or ""):
            if extract_nutrition_facts(log.serving_size or ""):
                label_text = log.serving_size
        meal = await estimate_meal_nutrients(db, log.food_name, notes=label_text)
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

        # The estimator ALREADY judges its own output — `review_meal` for energy
        # density and `review` per component against its category band — and
        # this writer ignored the verdict. So a flagged estimate was stored as
        # fact: one meal came out at 3,892 kcal with 394 g of fat, more fat than
        # the meal weighed, because "1 can of Titus Sardines" parsed as a 355 g
        # BEVERAGE can and the sardines resolved to ~997 kcal/100 g — above pure
        # fat. The estimator said so; nothing read it.
        #
        # Storing an impossible number is worse than storing none: it is
        # indistinguishable from food the patient ate, and it inflates every
        # daily total and every answer built on them.
        # A partial total must never pass unremarked. The meal is stored, which
        # is right — the alternative was discarding every sound component beside
        # the flagged one — but a number that omits an item reads as the whole
        # meal, so the omission is logged with the row id and the names.
        # Store it on the row, not only in a log line. The patient is the one
        # who needs to know their total is partial, and a log reaches nobody
        # who can act on it (§3ar — the readiness message that only the wrong
        # audience ever saw).
        #
        # Written on EVERY path, including the empty case: a re-estimate that
        # finds nothing excluded must CLEAR a caveat left by an earlier run, or
        # the row keeps warning about an omission that no longer exists.
        excluded = [str(name) for name in (meal.get("excluded_components") or [])]
        log.nutrients_excluded = excluded or None

        if excluded:
            logger.warning(
                "Log %s stores a PARTIAL total for %r — not counted: %s",
                log_id, (log.food_name or "")[:60], ", ".join(excluded)[:200])

        if meal.get("believable") is False:
            log.nutrient_status = "failed"
            await db.commit()
            logger.warning("Implausible estimate REJECTED for log %s (%r): %s",
                           log_id, (log.food_name or "")[:60],
                           "; ".join(meal.get("warnings") or [])[:300])
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

        # NOW the figures exist, so now the record can answer. The nutrient
        # limit check used to live in the endpoint, which runs BEFORE this task:
        # it read None for every nutrient and so never fired for any meal that
        # needed estimating — which is most of them.
        #
        # Deliberately AFTER the commit above. The meal and its nutrients are
        # already durable at this point, so an evaluation failure cannot roll
        # back the clinical write, and the log keeps its `done` status whatever
        # happens here. Losing an alert beats losing the meal (§3ah).
        try:
            from app.models.user import User
            from app.services import active_response

            user = (await db.execute(
                select(User).where(User.id == log.user_id)
            )).scalar_one_or_none()
            if user is not None:
                await active_response.evaluate_nutrition_log(db, log, user)
                await db.commit()
        except Exception:
            logger.exception("Post-enrichment evaluation failed for log %s", log_id)


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
