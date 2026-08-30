"""Clinical thresholds as DATA, not constants in the source.

A threshold is a fact about a guideline, a lab, a sex and an age — not about
medicine in general. Written into the engine it applies to everybody: HEBCS's
albumin band said 4.0-5.0 while the reporting lab said 3.2-4.8, and its BUN band
once used 21, the adult FEMALE ceiling, on a male patient.

Across millions of patients a constant is not an approximation, it is wrong for
most of them. So thresholds live here, where they can be corrected for a
population, a lab or a guideline revision without a deploy — and where the
`source` is recorded beside the number.

Resolution order in `hebcs_engine` is: the range this patient's lab REPORTED ->
the range most commonly reported for that analyte -> a row here -> the biomarker
goes UNSCORED. There is no step that invents one.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClinicalThreshold(Base):
    __tablename__ = "clinical_thresholds"
    __table_args__ = (
        UniqueConstraint("analyte", "sex", "age_min", "age_max",
                         name="uq_clinical_threshold_scope"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    #: Canonical biomarker name, as HEBCS knows it.
    analyte: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    #: Trapezoid bounds. NULL means "no penalty on that side".
    crit_low: Mapped[float | None] = mapped_column(Float)
    opt_low: Mapped[float | None] = mapped_column(Float)
    opt_high: Mapped[float | None] = mapped_column(Float)
    crit_high: Mapped[float | None] = mapped_column(Float)

    #: Who this applies to. NULL = everyone, so a general row can be narrowed
    #: later without touching the code that reads it.
    sex: Mapped[str | None] = mapped_column(String(10))
    age_min: Mapped[int | None] = mapped_column(Integer)
    age_max: Mapped[int | None] = mapped_column(Integer)

    #: Where the number came from — a guideline, a lab, a paper. Recorded
    #: because a threshold with no provenance cannot be reviewed or revised.
    source: Mapped[str] = mapped_column(String(200), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))
