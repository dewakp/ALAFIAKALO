"""Ground-truth overlays (Basis req #3): genetic data + environmental/social factors.

These are the slow-moving "ground truths" the collected day-to-day data is overlaid
on. Genetics is static per user; environmental/social factors are logged over time
(so their numeric fields feed the relationship/forecast engines as signals).
"""

from datetime import datetime, timezone, date

from sqlalchemy import String, Integer, Float, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class GeneticMarker(Base):
    """A single genetic finding for a user (one row per gene/variant).

    Static ground truth — consumed by the AI context and (later) HEBCS, not by
    the daily time-series engines.
    """
    __tablename__ = "genetic_markers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    gene: Mapped[str] = mapped_column(String(100), nullable=False)        # e.g. APOL1, MTHFR
    variant: Mapped[str | None] = mapped_column(String(100))             # rsID / allele, e.g. rs73885319
    genotype: Mapped[str | None] = mapped_column(String(50))             # e.g. G1/G1
    risk_allele: Mapped[str | None] = mapped_column(String(50))
    associated_condition: Mapped[str | None] = mapped_column(String(255))  # e.g. CKD / FSGS
    risk_level: Mapped[str | None] = mapped_column(String(50))           # protective | neutral | increased | high
    source: Mapped[str | None] = mapped_column(String(100))             # 23andMe, clinical panel, etc
    interpretation: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="genetic_markers")


class EnvSocialLog(Base):
    """Environmental + social factors logged over time (Basis ground truth).

    Numeric daily fields (AQI, temperature, stress, social support) are surfaced
    as signals to the relationship/forecast engines.
    """
    __tablename__ = "env_social_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Environmental
    location: Mapped[str | None] = mapped_column(String(255))
    air_quality_index: Mapped[int | None] = mapped_column(Integer)       # AQI
    ambient_temp_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    noise_level: Mapped[str | None] = mapped_column(String(50))          # quiet | moderate | loud
    pollen_level: Mapped[str | None] = mapped_column(String(50))

    # Social
    household_size: Mapped[int | None] = mapped_column(Integer)
    occupation: Mapped[str | None] = mapped_column(String(255))
    work_stress_level: Mapped[int | None] = mapped_column(Integer)        # 1-10
    financial_stress_level: Mapped[int | None] = mapped_column(Integer)   # 1-10
    social_support_level: Mapped[int | None] = mapped_column(Integer)     # 1-10
    major_life_event: Mapped[str | None] = mapped_column(Text)

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="env_social_logs")
