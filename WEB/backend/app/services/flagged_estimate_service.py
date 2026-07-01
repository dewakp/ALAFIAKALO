"""Records nutrient estimates that failed the believability (category-band) check.

The self-correcting estimator returns a low-confidence value when no source fits
the food's expected calorie band. Rather than lose that signal, we log it here
(deduped by normalized food name) so it can be reviewed and promoted into the
learning model (`learned_food_nutrients`). This closes the loop the plan calls
for: "record the miss to a lightweight flagged_estimates log for review + future
learning."
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flagged_estimate import FlaggedEstimate
from app.services import nutrition_reference

logger = logging.getLogger(__name__)


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


async def record_flagged(
    db: AsyncSession,
    food_name: str,
    candidate: dict,
    *,
    reason: str = "out_of_band",
    user_id: int | None = None,
) -> None:
    """Log (or bump) a flagged estimate. Never raises — flagging must not break estimation."""
    try:
        norm = _normalize(food_name)
        if not norm:
            return
        nutrients = dict(candidate.get("nutrients") or {})
        try:
            kcal = float(nutrients.get("calories"))
        except (TypeError, ValueError):
            kcal = None
        lo, hi = nutrition_reference.expected_kcal_band(food_name)
        category = nutrition_reference.classify(food_name)

        row = (await db.execute(
            select(FlaggedEstimate).where(
                FlaggedEstimate.food_name_normalized == norm,
                FlaggedEstimate.reviewed.is_(False),
            )
        )).scalar_one_or_none()

        if row is None:
            db.add(FlaggedEstimate(
                food_name=food_name.strip()[:512],
                food_name_normalized=norm,
                nutrients=nutrients,
                kcal_per_100g=kcal,
                category=category,
                expected_kcal_low=lo,
                expected_kcal_high=hi,
                reason=reason,
                source=candidate.get("source"),
                confidence=candidate.get("confidence"),
                created_by_user_id=user_id,
                occurrences=1,
            ))
        else:
            # Same miss seen again — refresh the candidate + bump the counter.
            row.occurrences += 1
            row.nutrients = nutrients
            row.kcal_per_100g = kcal
            row.source = candidate.get("source")
            row.confidence = candidate.get("confidence")
        await db.flush()
        logger.info("flagged estimate for '%s' (reason=%s, kcal=%s, band=%s-%s)",
                    norm, reason, kcal, lo, hi)
    except Exception as exc:  # defensive: logging a flag must never fail a request
        logger.warning("could not record flagged estimate for '%s': %s", food_name, exc)
