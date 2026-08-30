"""Medication → Nutrient mapping models.

Two tables:
  - med_nutrient_profiles   (global, app-wide cache — maps medication names to
                             per-dose-unit nutrient contributions)
  - medication_dose_logs    (per-user, per-date — records actual doses taken and
                             the pre-computed nutrients contributed that day)
"""

from datetime import datetime, timezone, date, time

from sqlalchemy import (
    String, Float, Integer, DateTime, Date, Time, ForeignKey, Text, Boolean, JSON, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MedNutrientProfile(Base):
    """Global medication → nutrient lookup table.

    Stores how much of each nutrient ONE unit of the medication delivers.
    Scaling: actual_nutrient = nutrients_per_dose_unit[key] * dose_amount.

    Examples
    --------
    Calcitriol 0.5 mcg:
        dose_unit_canonical = "mcg"
        nutrients_per_dose_unit = {"vitamin_d_iu": 40.0}
        → 0.5 × 40 = 20 IU vitamin D

    Calcium Carbonate (Tums Regular) 500 mg:
        dose_unit_canonical = "mg"
        nutrients_per_dose_unit = {"calcium_mg": 0.4}
        → 500 × 0.4 = 200 mg elemental calcium

    Fish Oil capsule 1000 mg:
        dose_unit_canonical = "mg"
        nutrients_per_dose_unit = {"omega3_g": 0.0003}
        → 1000 × 0.0003 = 0.3 g omega-3
    """

    __tablename__ = "med_nutrient_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    med_name_normalized: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    med_name_original: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_names: Mapped[str | None] = mapped_column(Text)          # comma-separated
    rxnorm_code: Mapped[str | None] = mapped_column(String(30))
    active_ingredient: Mapped[str | None] = mapped_column(String(255))

    # Canonical dose unit expected when querying (mg, mcg, IU, g, tablet, capsule, mL, mEq)
    dose_unit_canonical: Mapped[str] = mapped_column(String(50), nullable=False)

    # {nutrient_key: amount_per_1_canonical_dose_unit}
    # Keys match NutritionLog column names (calcium_mg, vitamin_d_iu, omega3_g, etc.)
    nutrients_per_dose_unit: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # "seeded" | "rxnorm_api" | "openfda_api" | "ai_discovered" | "manual"
    source: Mapped[str] = mapped_column(String(50), default="seeded")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # back-ref
    dose_logs: Mapped[list["MedicationDoseLog"]] = relationship(
        "MedicationDoseLog", back_populates="med_profile"
    )


class MedicationDoseLog(Base):
    """Per-user dose events — records each time a user takes a medication.

    nutrients_contributed is computed at write time by scaling
    MedNutrientProfile.nutrients_per_dose_unit * dose_amount and stored for
    fast aggregation in the daily-summary endpoint.
    """

    __tablename__ = "medication_dose_logs"

    __table_args__ = (
        # log_time is part of the key so a user can log the same medication+dose
        # more than once a day (e.g. morning + evening). Identical dose *events*
        # (same date+time+med+dose) still dedupe — which the Firebase sync relies on.
        UniqueConstraint(
            "user_id", "log_date", "log_time", "medication_name", "dose_amount", "dose_unit",
            name="uq_dose_log_per_user_date_med_dose",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Optional FK to the existing medications table (user's prescription record)
    medication_id: Mapped[int | None] = mapped_column(
        ForeignKey("medications.id"), nullable=True
    )
    # FK to global nutrient profile (resolved at log time; nullable for unknown meds)
    med_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("med_nutrient_profiles.id"), nullable=True
    )

    medication_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # A dose the guard refused, recorded anyway because the patient confirmed it.
    #
    # `acknowledge_unusual` used to be a request flag only — nothing persisted —
    # so a clinician reading the chart could not tell a force-logged dose from a
    # routine one. The guard fires on provable contradictions (a unit the drug is
    # not measured in, a dose above the largest marketed strength, a name RxNorm
    # does not know), so overriding one is a clinical statement and belongs in
    # the record with its reason.
    override_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # The findings as they stood when it was overridden, verbatim. Stored rather
    # than recomputed: RxNorm's answer changes over time, and what matters is
    # what the patient was shown when they pressed "log it anyway".
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    log_time: Mapped[time | None] = mapped_column(Time)
    dose_amount: Mapped[float] = mapped_column(Float, nullable=False)
    dose_unit: Mapped[str] = mapped_column(String(50), nullable=False)

    # Pre / post medication vitals (optional, matches the intake form)
    pre_systolic_bp: Mapped[int | None] = mapped_column(Integer)
    pre_diastolic_bp: Mapped[int | None] = mapped_column(Integer)
    pre_heart_rate: Mapped[int | None] = mapped_column(Integer)
    post_systolic_bp: Mapped[int | None] = mapped_column(Integer)
    post_diastolic_bp: Mapped[int | None] = mapped_column(Integer)
    post_heart_rate: Mapped[int | None] = mapped_column(Integer)
    pre_temperature_c: Mapped[float | None] = mapped_column(Float)
    post_temperature_c: Mapped[float | None] = mapped_column(Float)

    # Pre-computed nutrients contributed by this single dose event
    # {nutrient_key: absolute_amount} — already scaled, ready to sum
    nutrients_contributed: Mapped[dict | None] = mapped_column(JSON)

    # True when nutrients_contributed is populated and confirmed
    nutrients_resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="medication_dose_logs")
    med_profile: Mapped["MedNutrientProfile | None"] = relationship(
        "MedNutrientProfile", back_populates="dose_logs"
    )
