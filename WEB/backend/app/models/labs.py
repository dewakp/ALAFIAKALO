"""Lab results / EHR-compliant models."""

from datetime import datetime, timezone, date

from sqlalchemy import String, Float, DateTime, Date, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LabResult(Base):
    """EHR-friendly lab result storage (aligned with FHIR Observation resource)."""
    __tablename__ = "lab_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    test_date: Mapped[date] = mapped_column(Date, nullable=False)
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    loinc_code: Mapped[str | None] = mapped_column(String(20))  # LOINC standard code
    category: Mapped[str | None] = mapped_column(String(100))  # hematology, chemistry, etc.
    value: Mapped[float | None] = mapped_column(Float)
    value_string: Mapped[str | None] = mapped_column(String(255))  # for non-numeric results
    unit: Mapped[str | None] = mapped_column(String(50))
    reference_range_low: Mapped[float | None] = mapped_column(Float)
    reference_range_high: Mapped[float | None] = mapped_column(Float)
    is_abnormal: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), default="final")  # registered, partial, final, amended
    ordering_provider: Mapped[str | None] = mapped_column(String(255))
    performing_lab: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="lab_results")
