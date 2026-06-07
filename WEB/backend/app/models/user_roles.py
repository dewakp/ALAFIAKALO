"""User roles & professional profiles — multi-persona support.

Every user is a **patient** at the core.  Users may additionally hold one or
more professional roles (physician, nurse, administrator, etc.).  A separate
``ProfessionalProfile`` table stores credential / practice details for each
role a user claims.
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Text,
    Integer,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Comprehensive medical-practitioner classification enum ────────────

class UserRole(str, PyEnum):
    # Core
    patient = "patient"

    # Physicians
    physician = "physician"
    physician_assistant = "physician_assistant"
    resident = "resident"
    fellow = "fellow"
    attending_physician = "attending_physician"

    # Surgeons
    surgeon = "surgeon"
    general_surgeon = "general_surgeon"
    orthopedic_surgeon = "orthopedic_surgeon"
    neurosurgeon = "neurosurgeon"
    cardiothoracic_surgeon = "cardiothoracic_surgeon"
    plastic_surgeon = "plastic_surgeon"
    vascular_surgeon = "vascular_surgeon"

    # Medical Specialists
    specialist = "specialist"
    cardiologist = "cardiologist"
    dermatologist = "dermatologist"
    endocrinologist = "endocrinologist"
    gastroenterologist = "gastroenterologist"
    hematologist = "hematologist"
    infectious_disease_specialist = "infectious_disease_specialist"
    nephrologist = "nephrologist"
    neurologist = "neurologist"
    oncologist = "oncologist"
    ophthalmologist = "ophthalmologist"
    otolaryngologist = "otolaryngologist"
    pathologist = "pathologist"
    pulmonologist = "pulmonologist"
    radiologist = "radiologist"
    rheumatologist = "rheumatologist"
    urologist = "urologist"
    allergist = "allergist"
    anesthesiologist = "anesthesiologist"
    geriatrician = "geriatrician"
    neonatologist = "neonatologist"
    obstetrician_gynecologist = "obstetrician_gynecologist"
    pediatrician = "pediatrician"
    physiatrist = "physiatrist"
    sports_medicine_physician = "sports_medicine_physician"
    emergency_medicine_physician = "emergency_medicine_physician"
    intensivist = "intensivist"
    palliative_care_physician = "palliative_care_physician"
    pain_management_specialist = "pain_management_specialist"
    nuclear_medicine_physician = "nuclear_medicine_physician"
    preventive_medicine_physician = "preventive_medicine_physician"

    # Nursing
    nurse = "nurse"
    registered_nurse = "registered_nurse"
    nurse_practitioner = "nurse_practitioner"
    licensed_practical_nurse = "licensed_practical_nurse"
    clinical_nurse_specialist = "clinical_nurse_specialist"
    nurse_anesthetist = "nurse_anesthetist"
    nurse_midwife = "nurse_midwife"
    charge_nurse = "charge_nurse"
    nurse_educator = "nurse_educator"
    nurse_administrator = "nurse_administrator"

    # Therapy & Rehabilitation
    physiotherapist = "physiotherapist"
    physical_therapist = "physical_therapist"
    occupational_therapist = "occupational_therapist"
    speech_language_pathologist = "speech_language_pathologist"
    respiratory_therapist = "respiratory_therapist"
    recreational_therapist = "recreational_therapist"
    art_therapist = "art_therapist"
    music_therapist = "music_therapist"

    # Mental Health
    psychologist = "psychologist"
    psychiatrist = "psychiatrist"
    psychotherapist = "psychotherapist"
    clinical_psychologist = "clinical_psychologist"
    counseling_psychologist = "counseling_psychologist"
    school_psychologist = "school_psychologist"
    neuropsychologist = "neuropsychologist"
    licensed_professional_counselor = "licensed_professional_counselor"
    marriage_family_therapist = "marriage_family_therapist"
    addiction_counselor = "addiction_counselor"
    behavioral_analyst = "behavioral_analyst"

    # Social Work
    social_worker = "social_worker"
    clinical_social_worker = "clinical_social_worker"
    mental_health_social_worker = "mental_health_social_worker"
    medical_social_worker = "medical_social_worker"
    school_social_worker = "school_social_worker"

    # Dental
    dentist = "dentist"
    orthodontist = "orthodontist"
    periodontist = "periodontist"
    endodontist = "endodontist"
    oral_surgeon = "oral_surgeon"
    dental_hygienist = "dental_hygienist"

    # Pharmacy
    pharmacist = "pharmacist"
    clinical_pharmacist = "clinical_pharmacist"
    pharmacy_technician = "pharmacy_technician"

    # Diagnostics & Lab
    medical_laboratory_scientist = "medical_laboratory_scientist"
    medical_laboratory_technician = "medical_laboratory_technician"
    radiologic_technologist = "radiologic_technologist"
    ultrasound_technician = "ultrasound_technician"
    nuclear_medicine_technologist = "nuclear_medicine_technologist"

    # Emergency & Paramedic
    paramedic = "paramedic"
    emergency_medical_technician = "emergency_medical_technician"
    flight_nurse = "flight_nurse"
    flight_paramedic = "flight_paramedic"

    # Allied Health
    dietitian = "dietitian"
    nutritionist = "nutritionist"
    athletic_trainer = "athletic_trainer"
    exercise_physiologist = "exercise_physiologist"
    genetic_counselor = "genetic_counselor"
    audiologist = "audiologist"
    optometrist = "optometrist"
    podiatrist = "podiatrist"
    chiropractor = "chiropractor"
    acupuncturist = "acupuncturist"
    massage_therapist = "massage_therapist"
    certified_nursing_assistant = "certified_nursing_assistant"
    home_health_aide = "home_health_aide"
    medical_assistant = "medical_assistant"
    surgical_technologist = "surgical_technologist"
    perfusionist = "perfusionist"
    orthotist_prosthetist = "orthotist_prosthetist"
    biomedical_engineer = "biomedical_engineer"
    health_information_technician = "health_information_technician"
    medical_coder = "medical_coder"

    # Public Health
    public_health_professional = "public_health_professional"
    epidemiologist = "epidemiologist"
    health_educator = "health_educator"
    community_health_worker = "community_health_worker"
    environmental_health_specialist = "environmental_health_specialist"
    biostatistician = "biostatistician"
    health_policy_analyst = "health_policy_analyst"
    infection_control_specialist = "infection_control_specialist"

    # Administration
    clinic_administrator = "clinic_administrator"
    hospital_administrator = "hospital_administrator"
    practice_manager = "practice_manager"
    health_services_manager = "health_services_manager"
    medical_director = "medical_director"
    chief_medical_officer = "chief_medical_officer"
    chief_nursing_officer = "chief_nursing_officer"
    department_head = "department_head"
    quality_improvement_officer = "quality_improvement_officer"
    patient_safety_officer = "patient_safety_officer"
    compliance_officer = "compliance_officer"

    # Research & Education
    medical_researcher = "medical_researcher"
    clinical_research_coordinator = "clinical_research_coordinator"
    medical_professor = "medical_professor"
    residency_director = "residency_director"

    # Traditional / Complementary
    naturopathic_doctor = "naturopathic_doctor"
    traditional_medicine_practitioner = "traditional_medicine_practitioner"
    herbalist = "herbalist"
    homeopath = "homeopath"
    osteopath = "osteopath"

    # Midwifery
    midwife = "midwife"
    certified_midwife = "certified_midwife"
    doula = "doula"

    # Other
    veterinarian = "veterinarian"
    medical_interpreter = "medical_interpreter"
    patient_advocate = "patient_advocate"
    care_coordinator = "care_coordinator"
    case_manager = "case_manager"
    health_coach = "health_coach"


class VerificationStatus(str, PyEnum):
    unverified = "unverified"
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    expired = "expired"


# ── Role categories (helper, not persisted) ───────────────────────────

ROLE_CATEGORIES = {
    "physician": [
        "physician", "physician_assistant", "resident", "fellow",
        "attending_physician", "specialist", "cardiologist", "dermatologist",
        "endocrinologist", "gastroenterologist", "hematologist",
        "infectious_disease_specialist", "nephrologist", "neurologist",
        "oncologist", "ophthalmologist", "otolaryngologist", "pathologist",
        "pulmonologist", "radiologist", "rheumatologist", "urologist",
        "allergist", "anesthesiologist", "geriatrician", "neonatologist",
        "obstetrician_gynecologist", "pediatrician", "physiatrist",
        "sports_medicine_physician", "emergency_medicine_physician",
        "intensivist", "palliative_care_physician", "pain_management_specialist",
        "nuclear_medicine_physician", "preventive_medicine_physician",
    ],
    "surgeon": [
        "surgeon", "general_surgeon", "orthopedic_surgeon", "neurosurgeon",
        "cardiothoracic_surgeon", "plastic_surgeon", "vascular_surgeon",
        "oral_surgeon",
    ],
    "nursing": [
        "nurse", "registered_nurse", "nurse_practitioner",
        "licensed_practical_nurse", "clinical_nurse_specialist",
        "nurse_anesthetist", "nurse_midwife", "charge_nurse",
        "nurse_educator", "nurse_administrator", "flight_nurse",
    ],
    "therapy": [
        "physiotherapist", "physical_therapist", "occupational_therapist",
        "speech_language_pathologist", "respiratory_therapist",
        "recreational_therapist", "art_therapist", "music_therapist",
    ],
    "mental_health": [
        "psychologist", "psychiatrist", "psychotherapist",
        "clinical_psychologist", "counseling_psychologist",
        "school_psychologist", "neuropsychologist",
        "licensed_professional_counselor", "marriage_family_therapist",
        "addiction_counselor", "behavioral_analyst",
        "mental_health_social_worker",
    ],
    "social_work": [
        "social_worker", "clinical_social_worker", "medical_social_worker",
        "school_social_worker",
    ],
    "dental": [
        "dentist", "orthodontist", "periodontist", "endodontist",
        "oral_surgeon", "dental_hygienist",
    ],
    "pharmacy": [
        "pharmacist", "clinical_pharmacist", "pharmacy_technician",
    ],
    "diagnostics": [
        "medical_laboratory_scientist", "medical_laboratory_technician",
        "radiologic_technologist", "ultrasound_technician",
        "nuclear_medicine_technologist",
    ],
    "emergency": [
        "paramedic", "emergency_medical_technician",
        "flight_nurse", "flight_paramedic",
    ],
    "public_health": [
        "public_health_professional", "epidemiologist", "health_educator",
        "community_health_worker", "environmental_health_specialist",
        "biostatistician", "health_policy_analyst",
        "infection_control_specialist",
    ],
    "administration": [
        "clinic_administrator", "hospital_administrator", "practice_manager",
        "health_services_manager", "medical_director",
        "chief_medical_officer", "chief_nursing_officer", "department_head",
        "quality_improvement_officer", "patient_safety_officer",
        "compliance_officer",
    ],
    "allied_health": [
        "dietitian", "nutritionist", "athletic_trainer",
        "exercise_physiologist", "genetic_counselor", "audiologist",
        "optometrist", "podiatrist", "chiropractor", "acupuncturist",
        "massage_therapist", "certified_nursing_assistant",
        "home_health_aide", "medical_assistant", "surgical_technologist",
        "perfusionist", "orthotist_prosthetist", "biomedical_engineer",
        "health_information_technician", "medical_coder",
    ],
    "research": [
        "medical_researcher", "clinical_research_coordinator",
        "medical_professor", "residency_director",
    ],
    "traditional_complementary": [
        "naturopathic_doctor", "traditional_medicine_practitioner",
        "herbalist", "homeopath", "osteopath",
    ],
    "midwifery": [
        "midwife", "certified_midwife", "doula",
    ],
    "other": [
        "veterinarian", "medical_interpreter", "patient_advocate",
        "care_coordinator", "case_manager", "health_coach",
    ],
}


def role_display_name(role: str) -> str:
    """Human-readable label for a role value."""
    return role.replace("_", " ").title()


def role_category(role: str) -> str | None:
    """Return the category a role belongs to, or None."""
    for cat, members in ROLE_CATEGORIES.items():
        if role in members:
            return cat
    return None


# ── ORM Models ────────────────────────────────────────────────────────

class UserRoleAssignment(Base):
    """Join table: one user may hold many roles."""
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_user_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="role_assignments")
    professional_profiles = relationship("ProfessionalProfile", back_populates="role_assignment", cascade="all, delete-orphan")


class ProfessionalProfile(Base):
    """Extended professional details for a specific role assignment."""
    __tablename__ = "professional_profiles"
    __table_args__ = (
        UniqueConstraint("role_assignment_id", name="uq_profile_per_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    role_assignment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_role_assignments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Credentials
    license_number: Mapped[str | None] = mapped_column(String(100))
    license_state: Mapped[str | None] = mapped_column(String(100))
    license_country: Mapped[str | None] = mapped_column(String(100))
    license_expiry: Mapped[str | None] = mapped_column(String(20))
    npi_number: Mapped[str | None] = mapped_column(String(20))  # US National Provider ID
    dea_number: Mapped[str | None] = mapped_column(String(20))  # DEA registration
    board_certifications: Mapped[str | None] = mapped_column(Text)  # JSON array

    # Education
    medical_school: Mapped[str | None] = mapped_column(String(255))
    degree: Mapped[str | None] = mapped_column(String(100))  # MD, DO, DNP, PhD, etc.
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    residency_program: Mapped[str | None] = mapped_column(String(255))
    fellowship_program: Mapped[str | None] = mapped_column(String(255))

    # Practice
    specialty: Mapped[str | None] = mapped_column(String(200))
    sub_specialty: Mapped[str | None] = mapped_column(String(200))
    years_of_experience: Mapped[int | None] = mapped_column(Integer)
    practice_name: Mapped[str | None] = mapped_column(String(255))
    practice_type: Mapped[str | None] = mapped_column(String(100))  # private, hospital, clinic, academic
    practice_address: Mapped[str | None] = mapped_column(Text)
    practice_phone: Mapped[str | None] = mapped_column(String(30))
    practice_email: Mapped[str | None] = mapped_column(String(255))
    practice_website: Mapped[str | None] = mapped_column(String(500))
    accepting_patients: Mapped[bool | None] = mapped_column(Boolean)

    # Hospital affiliations
    hospital_affiliations: Mapped[str | None] = mapped_column(Text)  # JSON array
    department: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))  # job title

    # Languages spoken (clinical)
    clinical_languages: Mapped[str | None] = mapped_column(Text)  # JSON array

    # Telemedicine
    telemedicine_available: Mapped[bool] = mapped_column(Boolean, default=False)
    telemedicine_platforms: Mapped[str | None] = mapped_column(Text)  # JSON array

    # Verification
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    verification_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_notes: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[int | None] = mapped_column(Integer)  # admin user id

    # Bio
    professional_bio: Mapped[str | None] = mapped_column(Text)
    publications: Mapped[str | None] = mapped_column(Text)  # JSON array
    research_interests: Mapped[str | None] = mapped_column(Text)  # JSON array

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    role_assignment = relationship("UserRoleAssignment", back_populates="professional_profiles")
