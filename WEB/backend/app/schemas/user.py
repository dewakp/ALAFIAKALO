"""User schemas."""

from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    date_of_birth: str | None = None
    gender: str | None = None
    gender_at_birth: str | None = None
    blood_type: str | None = None
    insurance_id: str | None = None
    insurance_provider: str | None = None
    insurance_country: str | None = None
    # Location & culture (drive the default measurement system at signup)
    locale: str | None = None  # en-US, fr-FR, etc.
    timezone: str | None = None
    country: str | None = None
    preferred_units: str | None = None  # metric | imperial (defaults from locale)
    preferred_language: str | None = None


# ── Fields that can NEVER be changed once set ──────────────────────────
IMMUTABLE_FIELDS = {"date_of_birth", "gender_at_birth", "blood_type"}


class UserUpdate(BaseModel):
    # Identity (mutable)
    full_name: str | None = None
    gender: str | None = None  # gender identity — can evolve
    profile_picture_url: str | None = None

    # Immutable / set-once (backend enforces)
    date_of_birth: str | None = None
    gender_at_birth: str | None = None
    blood_type: str | None = None

    # Insurance (mutable)
    insurance_id: str | None = None
    insurance_provider: str | None = None
    insurance_country: str | None = None

    # Physical (mutable)
    height_cm: float | None = None
    current_weight_kg: float | None = None
    target_weight_kg: float | None = None

    # Location & Culture (mutable)
    locale: str | None = None
    timezone: str | None = None
    country: str | None = None
    preferred_units: str | None = None
    preferred_language: str | None = None

    # Health Profile (mutable)
    allergies: str | None = None
    food_intolerances: str | None = None
    dietary_restrictions: str | None = None
    dietary_preferences: str | None = None
    family_history: str | None = None

    # Fitness (mutable)
    activity_level: str | None = None
    fitness_goals: str | None = None
    preferred_activities: str | None = None
    exercise_frequency_per_week: int | None = None

    # Lifestyle (mutable)
    smoking_status: str | None = None
    alcohol_consumption: str | None = None
    sleep_schedule: str | None = None
    occupation: str | None = None
    stress_level: str | None = None

    # AI Preferences (mutable)
    ai_coaching_enabled: bool | None = None
    ai_notification_preferences: str | None = None
    ai_persona: str | None = None  # babalawo, dibia, boka
    ai_personality_preference: str | None = None
    ai_language_complexity: str | None = None

    # Privacy & Consent (mutable)
    data_sharing_consent: bool | None = None
    ai_training_consent: bool | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str

    # Demographics
    date_of_birth: str | None = None
    gender: str | None = None
    gender_at_birth: str | None = None
    profile_picture_url: str | None = None
    blood_type: str | None = None

    # Insurance
    insurance_id: str | None = None
    insurance_provider: str | None = None
    insurance_country: str | None = None

    # Physical
    height_cm: float | None = None
    current_weight_kg: float | None = None
    target_weight_kg: float | None = None

    # Location & Culture
    locale: str | None = None
    timezone: str | None = None
    country: str | None = None
    preferred_units: str | None = None
    preferred_language: str | None = None

    # Health Profile
    allergies: str | None = None
    food_intolerances: str | None = None
    dietary_restrictions: str | None = None
    dietary_preferences: str | None = None
    family_history: str | None = None

    # Fitness
    activity_level: str | None = None
    fitness_goals: str | None = None
    preferred_activities: str | None = None
    exercise_frequency_per_week: int | None = None

    # Lifestyle
    smoking_status: str | None = None
    alcohol_consumption: str | None = None
    sleep_schedule: str | None = None
    occupation: str | None = None
    stress_level: str | None = None

    # AI Preferences
    ai_coaching_enabled: bool | None = None
    ai_notification_preferences: str | None = None
    ai_persona: str | None = None  # babalawo, dibia, boka
    ai_personality_preference: str | None = None
    ai_language_complexity: str | None = None

    # Privacy & Consent
    data_sharing_consent: bool | None = None
    ai_training_consent: bool | None = None

    # System
    is_active: bool
    created_at: datetime

    # Persona info (populated after load)
    primary_role: str | None = None
    active_roles: list[str] | None = None
    is_healthcare_professional: bool | None = None

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class TokenData(BaseModel):
    user_id: int | None = None
