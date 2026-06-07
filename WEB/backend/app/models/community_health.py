"""Community Health models — alerts, recalls, advisories, reports, guidelines."""

from datetime import datetime, timezone, date
from enum import Enum as PyEnum

from sqlalchemy import String, Integer, Float, DateTime, Date, ForeignKey, Text, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums ──────────────────────────────────────────────────────────────

class AlertSeverity(str, PyEnum):
    """Severity levels for health alerts/advisories."""
    info = "info"
    low = "low"
    moderate = "moderate"
    high = "high"
    critical = "critical"


class AlertCategory(str, PyEnum):
    """Categorization of community health alerts."""
    pandemic = "pandemic"
    epidemic = "epidemic"
    outbreak = "outbreak"
    recall_drug = "recall_drug"
    recall_food = "recall_food"
    recall_device = "recall_device"
    advisory = "advisory"
    poison = "poison"
    environmental = "environmental"
    natural_disaster = "natural_disaster"
    bioterrorism = "bioterrorism"
    vaccination = "vaccination"
    guideline_update = "guideline_update"
    travel_health = "travel_health"
    water_safety = "water_safety"
    air_quality = "air_quality"
    other = "other"


class AlertSource(str, PyEnum):
    """Authoritative sources for community health data."""
    who = "who"                   # World Health Organization
    cdc = "cdc"                   # US Centers for Disease Control
    ecdc = "ecdc"                 # European Centre for Disease Prevention
    fda = "fda"                   # US Food & Drug Administration
    ema = "ema"                   # European Medicines Agency
    health_canada = "health_canada"
    mhra = "mhra"                 # UK Medicines & Healthcare products
    tga = "tga"                   # Australia Therapeutic Goods Admin
    phac = "phac"                 # Public Health Agency of Canada
    paho = "paho"                 # Pan American Health Organization
    africa_cdc = "africa_cdc"
    poison_control = "poison_control"
    local_health = "local_health"
    state_health = "state_health"
    national_health = "national_health"
    other = "other"


class ReportType(str, PyEnum):
    """Types of community health reports users can file."""
    symptom_cluster = "symptom_cluster"
    foodborne_illness = "foodborne_illness"
    waterborne_illness = "waterborne_illness"
    environmental_exposure = "environmental_exposure"
    adverse_drug_reaction = "adverse_drug_reaction"
    vaccine_side_effect = "vaccine_side_effect"
    poisoning = "poisoning"
    animal_bite = "animal_bite"
    disease_contact = "disease_contact"
    other = "other"


class GuidelineCategory(str, PyEnum):
    """Categories for clinical/public health guidelines."""
    infection_prevention = "infection_prevention"
    vaccination = "vaccination"
    chronic_disease = "chronic_disease"
    maternal_child = "maternal_child"
    nutrition = "nutrition"
    mental_health = "mental_health"
    environmental = "environmental"
    emergency = "emergency"
    travel = "travel"
    screening = "screening"
    antimicrobial = "antimicrobial"
    ncd = "ncd"                   # Non-communicable diseases
    other = "other"


# ── Models ──────────────────────────────────────────────────────────────

class CommunityHealthAlert(Base):
    """
    Centralized alert/recall/advisory from WHO, CDC, FDA, EMA,
    Health Canada, poison control, etc.
    """
    __tablename__ = "community_health_alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Classification
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_reference_id: Mapped[str | None] = mapped_column(String(200))

    # Geographic scope
    affected_countries: Mapped[str | None] = mapped_column(Text)         # JSON array
    affected_regions: Mapped[str | None] = mapped_column(Text)           # JSON array
    is_global: Mapped[bool] = mapped_column(Boolean, default=False)

    # Dates
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)

    # For recalls
    product_name: Mapped[str | None] = mapped_column(String(500))
    product_type: Mapped[str | None] = mapped_column(String(100))        # drug, food, device
    manufacturer: Mapped[str | None] = mapped_column(String(300))
    lot_numbers: Mapped[str | None] = mapped_column(Text)               # JSON array
    reason_for_recall: Mapped[str | None] = mapped_column(Text)
    recall_class: Mapped[str | None] = mapped_column(String(20))         # I, II, III

    # For disease outbreaks / pandemics
    disease_name: Mapped[str | None] = mapped_column(String(200))
    pathogen: Mapped[str | None] = mapped_column(String(200))
    confirmed_cases: Mapped[int | None] = mapped_column(Integer)
    deaths: Mapped[int | None] = mapped_column(Integer)

    # For advisories
    recommended_actions: Mapped[str | None] = mapped_column(Text)        # JSON array
    target_population: Mapped[str | None] = mapped_column(Text)          # JSON array

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_date: Mapped[date | None] = mapped_column(Date)
    resolution_notes: Mapped[str | None] = mapped_column(Text)

    # Tags / searchability
    tags: Mapped[str | None] = mapped_column(Text)                       # JSON array

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CommunityHealthReport(Base):
    """User-submitted community health reports (crowd-sourced surveillance)."""
    __tablename__ = "community_health_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    report_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Location
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_name: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(200))

    # Details
    symptoms_reported: Mapped[str | None] = mapped_column(Text)          # JSON array
    number_affected: Mapped[int | None] = mapped_column(Integer)
    onset_date: Mapped[date | None] = mapped_column(Date)
    product_involved: Mapped[str | None] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20), default="moderate")

    # Verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[str | None] = mapped_column(String(200))
    verified_date: Mapped[date | None] = mapped_column(Date)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="community_reports")


class HealthGuideline(Base):
    """
    Clinical / public-health guidelines from WHO, CDC, etc.
    e.g. vaccination schedules, screening recommendations, hand-hygiene protocols.
    """
    __tablename__ = "health_guidelines"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    full_text: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(String(50))

    # When it applies
    effective_date: Mapped[date | None] = mapped_column(Date)
    superseded_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Target
    target_population: Mapped[str | None] = mapped_column(Text)         # JSON array
    applicable_countries: Mapped[str | None] = mapped_column(Text)       # JSON array
    applicable_conditions: Mapped[str | None] = mapped_column(Text)      # JSON array

    # Recommendations (JSON array of structured recommendations)
    recommendations: Mapped[str | None] = mapped_column(Text)

    tags: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UserAlertSubscription(Base):
    """User preferences for which alert categories / regions to follow."""
    __tablename__ = "user_alert_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Subscription preferences (JSON arrays)
    categories: Mapped[str | None] = mapped_column(Text)                 # which alert categories
    sources: Mapped[str | None] = mapped_column(Text)                    # which sources
    countries: Mapped[str | None] = mapped_column(Text)                  # which countries to track
    severities: Mapped[str | None] = mapped_column(Text)                 # minimum severity

    # Notification
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="alert_subscriptions")


class AlertReadStatus(Base):
    """Track which alerts a user has read/dismissed."""
    __tablename__ = "alert_read_status"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("community_health_alerts.id"), nullable=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=True)
    is_bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="alert_read_statuses")
    alert = relationship("CommunityHealthAlert")
