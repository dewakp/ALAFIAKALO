"""User-labeled food photo (perceptual hash + ground-truth foods, no image bytes)."""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LabeledFoodImage(Base):
    __tablename__ = "labeled_food_images"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 64-bit dHash stored as string (avoids BigInteger sign issues across DBs)
    phash: Mapped[str] = mapped_column(String(32), index=True)
    labels: Mapped[str] = mapped_column(Text)          # "beans in palm oil; grilled chicken; fried plantain"
    source: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))
