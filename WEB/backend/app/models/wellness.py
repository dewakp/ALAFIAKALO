"""Wellness models — scores, plans, and cached AI results."""

from datetime import datetime, timezone, date
from sqlalchemy import String, Float, DateTime, Date, ForeignKey, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class WellnessScore(Base):
    __tablename__ = "wellness_scores"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    # NULL when nothing could be measured. The score used to default absent
    # domains to 50, so a patient with no data still got a number; removing that
    # default made None a real outcome, and the column has to allow it or the
    # endpoint 500s for every new user.
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100

    # Sub-scores  
    nutrition_score: Mapped[float | None] = mapped_column(Float)
    fitness_score: Mapped[float | None] = mapped_column(Float)
    sleep_score: Mapped[float | None] = mapped_column(Float)
    mood_score: Mapped[float | None] = mapped_column(Float)
    vitals_score: Mapped[float | None] = mapped_column(Float)
    medication_adherence_score: Mapped[float | None] = mapped_column(Float)

    explanation: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str | None] = mapped_column(Text)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="wellness_scores")


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dietary_pattern: Mapped[str] = mapped_column(String(50), default="balanced")  # balanced, plant_forward, renal, glucose
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    plan_data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: 7-day plan with meals
    shopping_list: Mapped[str | None] = mapped_column(Text)  # JSON
    advice: Mapped[str | None] = mapped_column(Text)
    total_daily_calories: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="meal_plans")


class ExercisePlan(Base):
    __tablename__ = "exercise_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    fitness_level: Mapped[str] = mapped_column(String(30), default="moderate")  # beginner, moderate, advanced
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    plan_data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: 7-day plan with workouts
    advice: Mapped[str | None] = mapped_column(Text)
    weekly_minutes_target: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="exercise_plans")
