"""What a food IS, remembered on its own terms.

Kept apart from `food_nutrient_cache` deliberately: that table's `nutrients` is
the nutrient answer, and writing a category-only row into it would put an empty
nutrient result in front of a real lookup — the "all-zero row counted as a hit"
fault of canon 3c.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FoodCategoryCache(Base):
    __tablename__ = "food_category_cache"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    food_name_normalized: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True)

    #: The authority's own wording, kept verbatim so a taxonomy change is
    #: visible rather than silently re-derived.
    usda_food_category: Mapped[str | None] = mapped_column(String(120))
    band_category: Mapped[str] = mapped_column(String(40), nullable=False)
    #: "usda" | "keyword" | "user".
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
