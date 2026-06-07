"""Notification models."""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class NotificationCategory(str, enum.Enum):
    """High-level notification categories."""

    THERAPY_SESSION = "therapy_session"
    CALENDAR = "calendar"
    LAB_ANOMALY = "lab_anomaly"
    TREATMENT_ANOMALY = "treatment_anomaly"
    MEDICATION_CONFLICT = "medication_conflict"
    NUTRITION_ALERT = "nutrition_alert"
    SYSTEM = "system"
    # Pharmacy
    PRESCRIPTION_CREATED = "prescription_created"
    PRESCRIPTION_READY = "prescription_ready"
    DISPENSE_COMPLETE = "dispense_complete"
    ADHERENCE_ALERT = "adherence_alert"
    REFILL_REMINDER = "refill_reminder"


class NotificationPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"


class Notification(Base):
    """In-app notification delivered to a specific user."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(Enum(NotificationCategory, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    priority = Column(Enum(NotificationPriority, values_callable=lambda x: [e.value for e in x]), nullable=False, default=NotificationPriority.MEDIUM)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    # Optional deep-link target (e.g. "/labs/42", "/medications/7")
    action_url = Column(String(512), nullable=True)
    # JSON metadata for structured payloads
    extra_data = Column("metadata", Text, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="notifications")


class NotificationPreference(Base):
    """Per-user per-category notification preferences."""

    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(Enum(NotificationCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    in_app = Column(Boolean, default=True, nullable=False)
    push = Column(Boolean, default=True, nullable=False)
    email = Column(Boolean, default=False, nullable=False)
    sms = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="notification_preferences")
