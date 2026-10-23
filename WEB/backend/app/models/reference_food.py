# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Food-composition authorities beyond USDA (migration av001).

One row per food in a published table — WAFCT 2019 first — in ALAFIA's
nutrient keys, per 100 g edible portion. The table ships EMPTY: rows come from
`scripts/load_reference_foods.py`, which is the licence gate (WAFCT is
CC BY-NC-SA 3.0 IGO; production is loaded when FAO's permission arrives).
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReferenceFood(Base):
    __tablename__ = "reference_foods"
    __table_args__ = (
        UniqueConstraint("source", "code", name="uq_reference_foods_source_code"),
        Index("ix_reference_foods_name_en", text("lower(name_en)")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_en: Mapped[str] = mapped_column(String(400), nullable=False)
    name_fr: Mapped[str | None] = mapped_column(String(400), nullable=True)
    scientific_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    food_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nutrients: Mapped[dict] = mapped_column(JSON, nullable=False)
    imputed: Mapped[list | None] = mapped_column(JSON, nullable=True)
    biblio: Mapped[str | None] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        default=lambda: datetime.now(timezone.utc))
