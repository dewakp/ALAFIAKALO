"""Advanced Directives model — healthcare agents, organ donation, life-sustaining treatment."""

from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AdvancedDirective(Base):
    __tablename__ = "advanced_directives"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True, index=True)

    # Primary Healthcare Agent
    primary_agent_name: Mapped[str | None] = mapped_column(String(255))
    primary_agent_relationship: Mapped[str | None] = mapped_column(String(100))
    primary_agent_phone: Mapped[str | None] = mapped_column(String(50))
    primary_agent_email: Mapped[str | None] = mapped_column(String(255))
    primary_agent_address: Mapped[str | None] = mapped_column(Text)

    # Alternate Healthcare Agent
    alternate_agent_name: Mapped[str | None] = mapped_column(String(255))
    alternate_agent_relationship: Mapped[str | None] = mapped_column(String(100))
    alternate_agent_phone: Mapped[str | None] = mapped_column(String(50))
    alternate_agent_email: Mapped[str | None] = mapped_column(String(255))
    alternate_agent_address: Mapped[str | None] = mapped_column(Text)

    # Organ Donation
    organ_donation_preference: Mapped[str | None] = mapped_column(String(50))  # any_purpose, transplant_only, research_only, no, undecided
    specific_organs_to_donate: Mapped[str | None] = mapped_column(Text)  # JSON list
    specific_organs_not_to_donate: Mapped[str | None] = mapped_column(Text)  # JSON list

    # Life-Sustaining Treatment
    life_support_preference: Mapped[str | None] = mapped_column(String(100))  # full_treatment, limited, comfort_only, undecided
    cpr_preference: Mapped[str | None] = mapped_column(String(50))  # yes, no, undecided
    ventilator_preference: Mapped[str | None] = mapped_column(String(50))
    feeding_tube_preference: Mapped[str | None] = mapped_column(String(50))
    dialysis_preference: Mapped[str | None] = mapped_column(String(50))
    blood_transfusion_preference: Mapped[str | None] = mapped_column(String(50))
    additional_instructions: Mapped[str | None] = mapped_column(Text)

    # Document
    document_signed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    document_date: Mapped[str | None] = mapped_column(String(20))
    witness_name: Mapped[str | None] = mapped_column(String(255))
    notarized: Mapped[bool | None] = mapped_column(Boolean, default=False)
    document_location: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="advanced_directive")
