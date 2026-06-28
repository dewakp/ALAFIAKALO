"""Nutrition learning model — learns correct food→nutrient values from feedback.

When a user corrects an estimate (or a verified seed is added), the per-100 g
profile is stored in ``learned_food_nutrients`` and consulted FIRST by the
estimator. Repeated corrections for the same food are merged into a running,
sample-weighted average — a simple online-learning update that converges on the
truth as more feedback arrives.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learned_nutrient import LearnedFoodNutrient

logger = logging.getLogger(__name__)


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


async def get_learned(db: AsyncSession, food_name: str) -> dict | None:
    """Return a learned per-100 g profile for ``food_name`` (highest authority), else None."""
    norm = _normalize(food_name)
    if not norm:
        return None
    row = (await db.execute(
        select(LearnedFoodNutrient).where(
            LearnedFoodNutrient.food_name_normalized == norm)
    )).scalar_one_or_none()
    if row is None:
        return None
    return {
        "source": "learned",
        "fdc_id": None,
        "ai_model": None,
        "food_name": row.food_name_original,
        "serving_size": (f"{row.serving_weight_g:.0f} g" if row.serving_weight_g else "100 g"),
        "serving_weight_g": row.serving_weight_g or 100.0,
        "confidence": row.confidence,
        "nutrients": dict(row.nutrients or {}),
        "cached": True,
    }


def _merge(old: dict, old_n: int, new: dict) -> dict:
    """Sample-weighted running average of two per-100 g nutrient maps."""
    merged = dict(old)
    keys = set(old) | set(new)
    for k in keys:
        nv = new.get(k)
        if not isinstance(nv, (int, float)):
            continue
        ov = old.get(k)
        if isinstance(ov, (int, float)):
            merged[k] = round((ov * old_n + nv) / (old_n + 1), 4)
        else:
            merged[k] = nv
    return merged


async def record_correction(
    db: AsyncSession,
    food_name: str,
    nutrients_per_100g: dict,
    *,
    serving_weight_g: float | None = None,
    user_id: int | None = None,
    source: str = "user_correction",
) -> LearnedFoodNutrient:
    """Upsert a learned food. New corrections are averaged into the existing row."""
    norm = _normalize(food_name)
    clean = {k: float(v) for k, v in (nutrients_per_100g or {}).items()
             if isinstance(v, (int, float))}
    row = (await db.execute(
        select(LearnedFoodNutrient).where(
            LearnedFoodNutrient.food_name_normalized == norm)
    )).scalar_one_or_none()

    if row is None:
        row = LearnedFoodNutrient(
            food_name_normalized=norm,
            food_name_original=food_name.strip(),
            nutrients=clean,
            serving_weight_g=serving_weight_g,
            source=source,
            sample_count=1,
            confidence=0.95 if source == "user_correction" else 0.99,
            created_by_user_id=user_id,
        )
        db.add(row)
    else:
        row.nutrients = _merge(row.nutrients or {}, row.sample_count, clean)
        row.sample_count += 1
        if serving_weight_g:
            row.serving_weight_g = serving_weight_g
        # Confidence rises with corroborating samples (caps at 0.99).
        row.confidence = min(0.99, 0.9 + 0.02 * row.sample_count)
    await db.flush()
    logger.info("learned nutrient for '%s' (samples=%s, source=%s)",
                norm, row.sample_count, source)
    return row


def per_100g_from_total(nutrients_total: dict, total_grams: float) -> dict:
    """Convert an absolute nutrient total for ``total_grams`` to a per-100 g profile."""
    if not total_grams or total_grams <= 0:
        return {}
    factor = 100.0 / total_grams
    return {k: round(float(v) * factor, 4)
            for k, v in (nutrients_total or {}).items()
            if isinstance(v, (int, float))}
