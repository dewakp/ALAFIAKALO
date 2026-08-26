"""User model."""

from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Text, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Basic Demographics
    date_of_birth: Mapped[str | None] = mapped_column(String(10))
    gender: Mapped[str | None] = mapped_column(String(20))  # current gender identity
    gender_at_birth: Mapped[str | None] = mapped_column(String(20))  # biological sex at birth
    profile_picture_url: Mapped[str | None] = mapped_column(Text)

    # Insurance
    insurance_id: Mapped[str | None] = mapped_column(String(100))
    insurance_provider: Mapped[str | None] = mapped_column(String(100))
    insurance_country: Mapped[str | None] = mapped_column(String(100))
    
    # Physical Characteristics
    height_cm: Mapped[float | None] = mapped_column(Float)
    current_weight_kg: Mapped[float | None] = mapped_column(Float)
    target_weight_kg: Mapped[float | None] = mapped_column(Float)
    blood_type: Mapped[str | None] = mapped_column(String(10))  # A+, O-, etc.
    
    # Location & Culture
    locale: Mapped[str | None] = mapped_column(String(10))  # en-US, fr-FR, etc.
    timezone: Mapped[str | None] = mapped_column(String(50))  # America/New_York
    country: Mapped[str | None] = mapped_column(String(100))
    preferred_units: Mapped[str | None] = mapped_column(String(20))  # metric, imperial
    preferred_language: Mapped[str | None] = mapped_column(String(10))  # en, es, fr
    
    # Health Profile
    allergies: Mapped[str | None] = mapped_column(Text)  # JSON array: food, medication, environmental
    food_intolerances: Mapped[str | None] = mapped_column(Text)  # JSON array: lactose, gluten, etc.
    dietary_restrictions: Mapped[str | None] = mapped_column(Text)  # JSON array: vegetarian, vegan, halal, kosher, etc.
    dietary_preferences: Mapped[str | None] = mapped_column(Text)  # JSON array: low-carb, keto, mediterranean, etc.
    chronic_conditions: Mapped[str | None] = mapped_column(Text)  # JSON array of condition IDs
    family_history: Mapped[str | None] = mapped_column(Text)  # JSON: hereditary conditions
    
    # Fitness Profile
    activity_level: Mapped[str | None] = mapped_column(String(50))  # sedentary, lightly_active, moderately_active, very_active, extremely_active
    fitness_goals: Mapped[str | None] = mapped_column(Text)  # JSON array: weight_loss, muscle_gain, endurance, flexibility
    preferred_activities: Mapped[str | None] = mapped_column(Text)  # JSON array: running, yoga, swimming, weightlifting
    exercise_frequency_per_week: Mapped[int | None] = mapped_column(Integer)
    
    # Lifestyle Factors
    smoking_status: Mapped[str | None] = mapped_column(String(50))  # never, former, current
    alcohol_consumption: Mapped[str | None] = mapped_column(String(50))  # none, occasional, moderate, heavy
    sleep_schedule: Mapped[str | None] = mapped_column(String(50))  # early_bird, night_owl, shift_worker
    occupation: Mapped[str | None] = mapped_column(String(100))
    stress_level: Mapped[str | None] = mapped_column(String(50))  # low, moderate, high
    
    # AI Personalization Settings
    ai_coaching_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_notification_preferences: Mapped[str | None] = mapped_column(Text)  # JSON: what types of notifications
    ai_persona: Mapped[str | None] = mapped_column(String(50))  # babalawo, dibia, boka
    ai_personality_preference: Mapped[str | None] = mapped_column(String(50))  # supportive, motivational, clinical, casual
    ai_language_complexity: Mapped[str | None] = mapped_column(String(50))  # simple, moderate, technical
    
    # Privacy & Consent
    data_sharing_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_training_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # System
    firebase_uid: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True,
        comment="Firebase Auth UID for migrated users",
    )
    auth_provider: Mapped[str | None] = mapped_column(
        String(50), default="local",
        comment="Auth provider: local, firebase, google, apple, phone",
    )
    phone_number: Mapped[str | None] = mapped_column(
        String(30), unique=True, nullable=True, index=True,
        comment="E.164 phone number for phone (OTP) sign-in",
    )
    system_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True,
        comment="255-char immutable System Identifier (SID)",
    )
    identity_uid: Mapped[str | None] = mapped_column(
        String(36), unique=True, nullable=True, index=True,
        comment="UUID of the shared 6IGMA Identity user (reference key; zero duplication)",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    # Last successful authentication, from any path (password, Firebase, SSO).
    # NULL means the account has never signed in since this column shipped —
    # which is different from "never signed in", and the admin console says so.
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # When this user opted out of MARKETING email. NULL = still eligible.
    # Never consult this for transactional mail (password reset, verification,
    # payment failure) — opting out of announcements must not lock someone out
    # of their own account recovery.
    marketing_opt_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    nutrition_logs = relationship("NutritionLog", back_populates="user", cascade="all, delete-orphan")
    fitness_logs = relationship("FitnessLog", back_populates="user", cascade="all, delete-orphan")
    lab_results = relationship("LabResult", back_populates="user", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="user", cascade="all, delete-orphan")
    medication_dose_logs = relationship("MedicationDoseLog", back_populates="user", cascade="all, delete-orphan")
    mood_entries = relationship("MoodEntry", back_populates="user", cascade="all, delete-orphan")
    lifestyle_entries = relationship("LifestyleEntry", back_populates="user", cascade="all, delete-orphan")
    sleep_logs = relationship("SleepLog", back_populates="user", cascade="all, delete-orphan")
    bowel_movements = relationship("BowelMovement", back_populates="user", cascade="all, delete-orphan")
    urination_logs = relationship("UrinationLog", back_populates="user", cascade="all, delete-orphan")
    vomiting_logs = relationship("VomitingLog", back_populates="user", cascade="all, delete-orphan")
    health_conditions = relationship("HealthCondition", back_populates="user", cascade="all, delete-orphan")
    symptom_logs = relationship("SymptomLog", back_populates="user", cascade="all, delete-orphan")
    illness_logs = relationship("IllnessLog", back_populates="user", cascade="all, delete-orphan")
    vitals_logs = relationship("VitalsLog", back_populates="user", cascade="all, delete-orphan")
    genetic_markers = relationship("GeneticMarker", back_populates="user", cascade="all, delete-orphan")
    env_social_logs = relationship("EnvSocialLog", back_populates="user", cascade="all, delete-orphan")

    # AI Intelligence & Memory
    ai_memories = relationship("UserMemory", back_populates="user", cascade="all, delete-orphan")
    ai_interactions = relationship("AIInteraction", back_populates="user", cascade="all, delete-orphan")
    
    # Privacy & Compliance
    consent_records = relationship("ConsentRecord", back_populates="user", cascade="all, delete-orphan")
    data_access_logs = relationship("DataAccessLog", back_populates="user", foreign_keys="[DataAccessLog.user_id]", cascade="all, delete-orphan")
    data_export_requests = relationship("DataExportRequest", back_populates="user", cascade="all, delete-orphan")
    data_deletion_requests = relationship("DataDeletionRequest", back_populates="user", foreign_keys="[DataDeletionRequest.user_id]", cascade="all, delete-orphan")
    privacy_settings = relationship("PrivacySettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    # Chronic Disease Management
    chronic_conditions = relationship("ChronicCondition", back_populates="user", cascade="all, delete-orphan")
    therapy_sessions = relationship("TherapySession", back_populates="user", foreign_keys="[TherapySession.user_id]", cascade="all, delete-orphan")
    condition_metrics = relationship("ConditionMetric", back_populates="user", cascade="all, delete-orphan")

    # EHR & Media
    ehr_connections = relationship("EHRConnection", back_populates="user", cascade="all, delete-orphan")
    media_assets = relationship("MediaAsset", back_populates="user", cascade="all, delete-orphan")

    # Mental Health
    mental_health_assessments = relationship("MentalHealthAssessment", back_populates="user", cascade="all, delete-orphan")
    breathing_sessions = relationship("BreathingSession", back_populates="user", cascade="all, delete-orphan")
    gratitude_entries = relationship("GratitudeEntry", back_populates="user", cascade="all, delete-orphan")

    # Community Health
    community_reports = relationship("CommunityHealthReport", back_populates="user", cascade="all, delete-orphan")
    alert_subscriptions = relationship("UserAlertSubscription", back_populates="user", cascade="all, delete-orphan")
    alert_read_statuses = relationship("AlertReadStatus", back_populates="user", cascade="all, delete-orphan")

    # Roles & Personas
    role_assignments = relationship("UserRoleAssignment", back_populates="user", cascade="all, delete-orphan")

    # Health Data Sync
    health_sync_connections = relationship("HealthSyncConnection", back_populates="user", cascade="all, delete-orphan")

    # Calendar
    calendar_events = relationship("CalendarEvent", back_populates="user", cascade="all, delete-orphan")
    insurances = relationship("Insurance", back_populates="user", cascade="all, delete-orphan")

    # Notifications
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    notification_preferences = relationship("NotificationPreference", back_populates="user", cascade="all, delete-orphan")

    # Pantry
    pantry_items = relationship("PantryItem", back_populates="user", cascade="all, delete-orphan")
