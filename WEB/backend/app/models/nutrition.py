"""Nutrition tracking models."""

from datetime import datetime, timezone, date, time

from sqlalchemy import String, Float, Integer, DateTime, Date, ForeignKey, Text, JSON, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class NutritionLog(Base):
    __tablename__ = "nutrition_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(50), nullable=False)  # breakfast, lunch, dinner, snack
    food_name: Mapped[str] = mapped_column(Text, nullable=False)
    serving_size: Mapped[str | None] = mapped_column(Text)
    fdc_id: Mapped[int | None] = mapped_column(Integer)  # USDA FoodData Central ID
    
    # Macronutrients
    calories: Mapped[float | None] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    fiber_g: Mapped[float | None] = mapped_column(Float)
    sugar_g: Mapped[float | None] = mapped_column(Float)
    
    # Fat breakdown
    saturated_fat_g: Mapped[float | None] = mapped_column(Float)
    trans_fat_g: Mapped[float | None] = mapped_column(Float)
    monounsaturated_fat_g: Mapped[float | None] = mapped_column(Float)
    polyunsaturated_fat_g: Mapped[float | None] = mapped_column(Float)
    omega3_g: Mapped[float | None] = mapped_column(Float)
    omega6_g: Mapped[float | None] = mapped_column(Float)
    cholesterol_mg: Mapped[float | None] = mapped_column(Float)
    
    # Minerals
    sodium_mg: Mapped[float | None] = mapped_column(Float)
    potassium_mg: Mapped[float | None] = mapped_column(Float)
    calcium_mg: Mapped[float | None] = mapped_column(Float)
    iron_mg: Mapped[float | None] = mapped_column(Float)
    magnesium_mg: Mapped[float | None] = mapped_column(Float)
    zinc_mg: Mapped[float | None] = mapped_column(Float)
    phosphorus_mg: Mapped[float | None] = mapped_column(Float)
    copper_mg: Mapped[float | None] = mapped_column(Float)
    manganese_mg: Mapped[float | None] = mapped_column(Float)
    selenium_mcg: Mapped[float | None] = mapped_column(Float)
    iodine_mcg: Mapped[float | None] = mapped_column(Float)
    
    # Vitamins
    vitamin_a_iu: Mapped[float | None] = mapped_column(Float)
    vitamin_c_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_d_iu: Mapped[float | None] = mapped_column(Float)
    vitamin_e_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_k_mcg: Mapped[float | None] = mapped_column(Float)
    vitamin_b1_thiamine_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_b2_riboflavin_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_b3_niacin_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_b5_pantothenic_acid_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_b6_mg: Mapped[float | None] = mapped_column(Float)
    vitamin_b7_biotin_mcg: Mapped[float | None] = mapped_column(Float)
    vitamin_b9_folate_mcg: Mapped[float | None] = mapped_column(Float)
    vitamin_b12_mcg: Mapped[float | None] = mapped_column(Float)
    choline_mg: Mapped[float | None] = mapped_column(Float)
    
    # Other nutrients
    water_ml: Mapped[float | None] = mapped_column(Float)
    caffeine_mg: Mapped[float | None] = mapped_column(Float)
    alcohol_g: Mapped[float | None] = mapped_column(Float)
    
    # Extended nutrients (amino acids, fatty acids, carotenoids, etc.) stored as JSON
    extended_nutrients: Mapped[dict | None] = mapped_column(JSON)

    # Meal timing and pre/post weights (from Firebase)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    pre_meal_weight_kg: Mapped[float | None] = mapped_column(Float)
    post_meal_weight_kg: Mapped[float | None] = mapped_column(Float)
    food_image_uris: Mapped[str | None] = mapped_column(Text)
    recipe_url: Mapped[str | None] = mapped_column(Text)

    notes: Mapped[str | None] = mapped_column(Text)

    # Nutrient enrichment state.
    #
    # The log is saved and returned immediately; nutrient lookup (USDA per item,
    # branded, AI fallback) runs afterwards in the background because it costs
    # seconds, not milliseconds, and used to hold the whole request — a 10-item
    # meal exceeded the client's 30s timeout and the entry was lost.
    #
    #   pending  — queued/running; values will appear shortly
    #   done     — enrichment finished (values may still be partial)
    #   failed   — lookup errored or timed out; the meal itself is intact
    #   skipped  — nothing to do (nutrients supplied, or a USDA item was linked)
    nutrient_status: Mapped[str] = mapped_column(
        String(16), default="skipped", nullable=False, server_default="skipped"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="nutrition_logs")
