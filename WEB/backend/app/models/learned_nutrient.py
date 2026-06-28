"""Learned food→nutrient values — the nutrition learning model.

User corrections (and verified seeds) of a food's per-100 g nutrient profile are
stored here and consulted FIRST by the estimator, so the system gets more accurate
over time from real feedback. Multiple corrections for the same food are aggregated
into a running (sample-weighted) average — a simple online-learning update.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Float, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LearnedFoodNutrient(Base):
    __tablename__ = "learned_food_nutrients"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Lookup key — lowercased, stripped, brand-free food name.
    food_name_normalized: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True)
    food_name_original: Mapped[str] = mapped_column(String(512), nullable=False)

    # Verified per-100 g nutrient profile (keys = DB_COLUMN_KEYS + extended).
    nutrients: Mapped[dict] = mapped_column(JSON, nullable=False)
    serving_weight_g: Mapped[float | None] = mapped_column(Float)

    # "user_correction" | "verified_seed"
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="user_correction")
    # Number of corrections aggregated into this row (online-average weight).
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.95)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
