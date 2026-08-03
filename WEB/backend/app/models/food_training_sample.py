"""Append-only corpus of meal photos, model predictions, and user corrections.

This is the training set for ALAFIAModel Vision Phase 5 (on-device food
classifier). It exists because nothing was accumulating one: `LabeledFoodImage`
stores a 64-bit perceptual hash and throws the image away, which is right for
"have I seen this meal before?" and useless for training a CNN.

Separation of concerns:

  LabeledFoodImage    per-user recall index, UPSERTED (one row per meal)
  FoodTrainingSample  the corpus, APPEND-ONLY (one row per analysis)

Each row is a (photo, prediction, correction) triple. A row whose
`corrected_items` is set is a supervised example: the model said X, the human
said Y. Those are the rows worth the most at training time.

Image bytes are retained only with consent
(`PrivacySettings.allow_collective_insights`). Without it the row is still
recorded — prediction, correction and metrics stay useful for measuring
accuracy — but `media_asset_id` is NULL and no photo is kept.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FoodTrainingSample(Base):
    __tablename__ = "food_training_samples"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # Content hash of the photo. Deduplicates re-analysis of the same image and
    # lets a correction be attached without re-uploading it.
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    # 64-bit dHash, so the corpus can be grouped by near-duplicate meal.
    phash: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)

    # The retained photo. NULL when consent was not granted.
    media_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True, index=True)
    image_retained: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # How many photos were analysed together for this sample (one plate,
    # several angles — see the multi-image path in the vision capability).
    image_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # What produced the prediction, e.g. "vision-ollama:llava", "learned-recall".
    source_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # [{"name", "estimated_portion", "estimated_grams", "confidence"}, ...]
    predicted_items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    predicted_nutrition: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # The user's ground truth, same shape. NULL until they correct it.
    corrected_items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # none | accepted | item | quantity | both
    correction_kind: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
