"""Flagged nutrient estimates — the review/learning queue.

When the self-correcting estimator cannot find any source whose calorie density
fits the food's category band (see `nutrition_reference`), it still returns the
best candidate but marks it low-confidence/out-of-band. Each such miss is logged
here so it can be (a) reviewed by an admin/dietitian, and (b) turned into a
verified correction in `learned_food_nutrients` — closing the believability loop
instead of silently shipping an implausible value.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Float, Integer, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FlaggedEstimate(Base):
    __tablename__ = "flagged_estimates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # What was estimated.
    food_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    food_name_normalized: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    # The (implausible) candidate that was returned, per-100 g.
    nutrients: Mapped[dict] = mapped_column(JSON, nullable=False)
    kcal_per_100g: Mapped[float | None] = mapped_column(Float)

    # Why it was flagged: the category band it violated.
    category: Mapped[str | None] = mapped_column(String(64))
    expected_kcal_low: Mapped[float | None] = mapped_column(Float)
    expected_kcal_high: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="out_of_band")

    # Provenance of the flagged candidate (usda | branded | ai | …) + confidence.
    source: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[float | None] = mapped_column(Float)

    # Review workflow.
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    # How many times we've seen this same miss (deduped by normalized name).
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
