"""Pantry / Refrigerator inventory models."""

from datetime import datetime, timezone, date
from enum import Enum as PyEnum

from sqlalchemy import String, Float, DateTime, Date, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StorageLocation(str, PyEnum):
    REFRIGERATOR = "refrigerator"
    FREEZER = "freezer"
    PANTRY = "pantry"


class ItemCategory(str, PyEnum):
    PRODUCE = "produce"
    DAIRY = "dairy"
    MEAT = "meat"
    SEAFOOD = "seafood"
    GRAINS = "grains"
    CANNED = "canned"
    FROZEN = "frozen"
    BEVERAGES = "beverages"
    CONDIMENTS = "condiments"
    SNACKS = "snacks"
    BAKING = "baking"
    SPICES = "spices"
    OTHER = "other"


class PantryItem(Base):
    """Tracks items in the user's pantry, refrigerator, or freezer."""
    __tablename__ = "pantry_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="other")  # ItemCategory
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str] = mapped_column(String(50), default="pieces")  # pieces, lbs, oz, kg, g, liters, ml, cups, gallons
    location: Mapped[str] = mapped_column(String(50), default="pantry")  # StorageLocation
    expiration_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    # Future: auto-replenish via grocer integration
    # TODO: Connect to third-party grocer APIs (Instacart, Kroger, Walmart, etc.)
    #       to power automatic replenishment when items run low.
    auto_replenish: Mapped[bool] = mapped_column(Boolean, default=False)
    low_threshold: Mapped[float | None] = mapped_column(Float)  # trigger replenish when qty drops below
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="pantry_items")
