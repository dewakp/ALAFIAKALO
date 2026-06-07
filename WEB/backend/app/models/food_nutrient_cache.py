"""Cached nutrient estimates for foods — USDA or AI-derived."""

from datetime import datetime, timezone

from sqlalchemy import String, Float, Integer, DateTime, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FoodNutrientCache(Base):
    """
    App-wide cache for food→nutrient mappings.
    Source is either 'usda' (authoritative) or 'ai' (LLM-estimated).
    AI estimates are cached so the same food name never triggers a second LLM call.
    """
    __tablename__ = "food_nutrient_cache"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Lookup key — lowercased, stripped food name
    food_name_normalized: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    # Original food name as submitted
    food_name_original: Mapped[str] = mapped_column(String(512), nullable=False)

    # Source: "usda" or "ai"
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # If USDA, store fdc_id for provenance
    fdc_id: Mapped[int | None] = mapped_column(Integer)
    # AI model used (e.g. "gpt-4-turbo-preview", "gpt-oss:20b")
    ai_model: Mapped[str | None] = mapped_column(String(100))

    # Serving info
    serving_size: Mapped[str | None] = mapped_column(String(100))  # e.g. "1 cup", "100g"
    serving_weight_g: Mapped[float | None] = mapped_column(Float)

    # All nutrients stored as JSON — keys match our DB_COLUMN_KEYS + extended
    nutrients: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Confidence: 1.0 for USDA, 0.0-1.0 for AI self-reported confidence
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # How many times this cache entry was used
    hit_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_food_cache_source", "source"),
    )
