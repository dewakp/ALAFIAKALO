"""User schemas."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    # Two fields. The old single `full_name` forced `auth.register` to guess
    # which word was the surname, and it sent the literal "XXX" to the identity
    # service whenever someone entered one word.
    #
    # min_length=3 is the specified rule ("longer than 2 letters"). It is
    # enforced here, at the boundary, so web, iOS and Android cannot disagree.
    first_name: str | None = Field(default=None, min_length=3, max_length=100)
    last_name: str | None = Field(default=None, min_length=3, max_length=100)
    full_name: str | None = None
    @model_validator(mode="after")
    def _reconcile_names(self):
        """Keep the two forms in step, whichever the client sent.

        Builds already shipped (TestFlight 1.5, the distributed APK) post
        `full_name` alone. Refusing them would break signup for every user who
        has not updated, so a single-field client is split here instead — the
        same guess as before, but now confined to the compatibility path rather
        than being how the field works.
        """
        if self.first_name and self.last_name:
            self.first_name = self.first_name.strip()
            self.last_name = self.last_name.strip()
            if not self.full_name:
                self.full_name = f"{self.first_name} {self.last_name}".strip()
            return self

        if self.full_name and self.full_name.strip():
            # Compatibility only: guess, exactly as `auth.register` used to,
            # but keep the guess here instead of letting "XXX" reach identity.
            parts = self.full_name.split()
            self.first_name = self.first_name or parts[0]
            self.last_name = self.last_name or (parts[-1] if len(parts) > 1 else parts[0])
            return self

        raise ValueError("First name and last name are required.")

    phone: str | None = None  # E.164 — enables phone/password login (PostgreSQL IdP)
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
    first_name: str | None = Field(default=None, min_length=3, max_length=100)
    last_name: str | None = Field(default=None, min_length=3, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    name_prefix: str | None = Field(default=None, max_length=20)
    name_suffix: str | None = Field(default=None, max_length=20)
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

    # Physical (mutable).
    #
    # The column names carry the canonical unit, but the patient reads their
    # weight off whatever scale is in front of them — so the client may name
    # the unit the value is in and the backend converts (app/core/units.py).
    # Bounds are enforced on the CANONICAL value after conversion, in the
    # endpoint: a bare unbounded float is how 70 inches became a 70 cm adult.
    height_cm: float | None = None
    current_weight_kg: float | None = None
    target_weight_kg: float | None = None
    # "cm"/"in" and "kg"/"lb" (spellings in units._INTAKE_ALIASES). Omit to
    # send the canonical unit the field name already states.
    height_unit: str | None = None
    weight_unit: str | None = None
    # Record a value the plausibility check calls impossible. Some patients
    # genuinely are outside it (severe skeletal dysplasia), and a guard with no
    # route forward blocks a true clinical record — canon §3aj, same name as
    # the dose guard's escape hatch.
    acknowledge_unusual: bool | None = None

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
    # The parts. `full_name` stays for display and for rows that predate the
    # split; these are what a list sorts and greets by.
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    name_prefix: str | None = None
    name_suffix: str | None = None
    # A data: URI, or None. Named `_url` because that is what a renderer needs
    # it to be — <img src> takes either.
    profile_picture_url: str | None = None

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

    # Physical (always canonical — cm and kg)
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
