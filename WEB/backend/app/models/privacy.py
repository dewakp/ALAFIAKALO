"""
Privacy and Compliance Models
Supports HIPAA, GDPR, and healthcare data privacy requirements
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.core.database import Base


class ConsentType(str, enum.Enum):
    """Types of consent that can be granted"""
    TERMS_OF_SERVICE = "terms_of_service"
    PRIVACY_POLICY = "privacy_policy"
    DATA_PROCESSING = "data_processing"
    DATA_SHARING_ANONYMIZED = "data_sharing_anonymized"  # For collective insights
    DATA_SHARING_RESEARCH = "data_sharing_research"
    MARKETING_COMMUNICATIONS = "marketing_communications"
    AI_COACHING = "ai_coaching"
    THIRD_PARTY_INTEGRATIONS = "third_party_integrations"
    COOKIES_ANALYTICS = "cookies_analytics"


class DataAccessPurpose(str, enum.Enum):
    """Purpose for accessing patient data (HIPAA minimum necessary)"""
    TREATMENT = "treatment"  # Direct patient care
    AI_RECOMMENDATION = "ai_recommendation"  # AI-generated insights
    ANALYTICS_AGGREGATED = "analytics_aggregated"  # Anonymized analytics
    EXPORT_REQUEST = "export_request"  # Patient data export (GDPR)
    SUPPORT_REQUEST = "support_request"  # Customer support
    LEGAL_COMPLIANCE = "legal_compliance"  # Legal/regulatory requirement
    SECURITY_AUDIT = "security_audit"  # Security investigation
    RESEARCH_ANONYMIZED = "research_anonymized"  # De-identified research
    SYSTEM_MAINTENANCE = "system_maintenance"  # Technical operations


class ExportStatus(str, enum.Enum):
    """Status of data export request"""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    DOWNLOADED = "downloaded"
    EXPIRED = "expired"
    FAILED = "failed"


class DeletionStatus(str, enum.Enum):
    """Status of data deletion request (GDPR right to be forgotten)"""
    PENDING = "pending"
    IN_REVIEW = "in_review"  # Manual review for legal holds
    APPROVED = "approved"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"


class ConsentRecord(Base):
    """
    User consent tracking for GDPR compliance
    Records all consents and withdrawals with timestamps
    """
    __tablename__ = "consent_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Consent details
    consent_type = Column(SQLEnum(ConsentType), nullable=False, index=True)
    consent_version = Column(String(50), nullable=False)  # e.g., "1.0", "2023-05-15"
    consent_granted = Column(Boolean, nullable=False)  # True = granted, False = withdrawn
    
    # Metadata
    consent_text = Column(Text, nullable=True)  # Full text of what user consented to
    consent_language = Column(String(10), default="en")  # Language of consent (ISO 639-1)
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6 for audit trail
    user_agent = Column(String(500), nullable=True)  # Browser/app info
    
    # Timestamps
    granted_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True)  # Optional expiration (e.g., research consent)
    
    # Relationships
    user = relationship("User", back_populates="consent_records")
    
    def __repr__(self):
        return f"<ConsentRecord(user_id={self.user_id}, type={self.consent_type}, granted={self.consent_granted})>"


class DataAccessLog(Base):
    """
    Audit log for all PHI/PII access (HIPAA/GDPR requirement)
    Tracks who accessed what data, when, and why
    """
    __tablename__ = "data_access_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Access details
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    accessed_by_user_id = Column(Integer, nullable=True, index=True)  # Admin/support user ID
    accessed_by_system = Column(String(100), nullable=True)  # System component (e.g., "ai_engine", "export_job")
    
    # What was accessed
    access_type = Column(String(100), nullable=False, index=True)  # e.g., "view_profile", "export_data", "ai_recommendation"
    resource_type = Column(String(100), nullable=False)  # e.g., "User", "NutritionLog", "LabResult"
    resource_id = Column(Integer, nullable=True)  # Specific record ID
    purpose = Column(SQLEnum(DataAccessPurpose), nullable=False, index=True)
    
    # Access context
    data_accessed = Column(JSON, nullable=True)  # Fields accessed (not full data, for privacy)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # Timestamps
    accessed_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="data_access_logs")
    
    def __repr__(self):
        return f"<DataAccessLog(user_id={self.user_id}, type={self.access_type}, purpose={self.purpose})>"


class DataExportRequest(Base):
    """
    GDPR Article 20: Right to data portability
    Users can request all their data in machine-readable format
    """
    __tablename__ = "data_export_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Request details
    status = Column(SQLEnum(ExportStatus), default=ExportStatus.PENDING, nullable=False, index=True)
    export_format = Column(String(20), default="json")  # json, csv, pdf
    include_attachments = Column(Boolean, default=True)  # Include files, images
    
    # Processing
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    processed_at = Column(DateTime, nullable=True)
    file_path = Column(String(500), nullable=True)  # Secure storage path
    file_size_bytes = Column(Integer, nullable=True)
    download_url = Column(String(1000), nullable=True)  # Signed URL with expiration
    
    # Security
    downloaded_at = Column(DateTime, nullable=True)
    download_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True)  # Auto-delete after 7 days (GDPR best practice)
    
    # Metadata
    ip_address = Column(String(45), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="data_export_requests")
    
    def __repr__(self):
        return f"<DataExportRequest(user_id={self.user_id}, status={self.status})>"


class DataDeletionRequest(Base):
    """
    GDPR Article 17: Right to be forgotten
    Users can request complete deletion of their data
    """
    __tablename__ = "data_deletion_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # User info (preserved even after deletion for audit)
    user_email = Column(String(255), nullable=False)
    user_full_name = Column(String(255), nullable=True)
    
    # Request details
    status = Column(SQLEnum(DeletionStatus), default=DeletionStatus.PENDING, nullable=False, index=True)
    reason = Column(Text, nullable=True)  # Optional: why user is deleting
    
    # Processing
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_user_id = Column(Integer, nullable=True)  # Admin who reviewed
    approved_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Retention exceptions
    retention_required = Column(Boolean, default=False)  # Legal/regulatory hold
    retention_reason = Column(Text, nullable=True)  # e.g., "Pending litigation"
    retention_until = Column(DateTime, nullable=True)
    
    # Audit trail
    deletion_log = Column(JSON, nullable=True)  # Record of what was deleted
    anonymization_log = Column(JSON, nullable=True)  # What was anonymized vs deleted
    
    # Metadata
    ip_address = Column(String(45), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="data_deletion_requests")
    
    def __repr__(self):
        return f"<DataDeletionRequest(user_email={self.user_email}, status={self.status})>"


class PrivacySettings(Base):
    """
    User privacy preferences and settings
    Granular control over data usage
    """
    __tablename__ = "privacy_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Data sharing preferences
    allow_anonymized_analytics = Column(Boolean, default=True)  # For platform improvement
    allow_collective_insights = Column(Boolean, default=False)  # For cross-user AI learning
    allow_research_participation = Column(Boolean, default=False)  # De-identified research
    
    # Communication preferences
    allow_marketing_emails = Column(Boolean, default=False)
    allow_product_updates = Column(Boolean, default=True)
    allow_health_reminders = Column(Boolean, default=True)
    
    # AI preferences
    ai_coaching_enabled = Column(Boolean, default=True)
    ai_memory_enabled = Column(Boolean, default=True)  # Personal AI learning
    ai_explainability_level = Column(String(20), default="standard")  # minimal, standard, detailed
    
    # Third-party integrations
    allow_third_party_integrations = Column(Boolean, default=False)
    approved_third_parties = Column(JSON, nullable=True)  # List of approved integrations
    
    # Data retention
    data_retention_days = Column(Integer, nullable=True)  # Custom retention (null = default 7 years)
    auto_delete_old_data = Column(Boolean, default=False)
    
    # Location & tracking
    allow_location_tracking = Column(Boolean, default=False)
    allow_usage_analytics = Column(Boolean, default=True)
    allow_crash_reporting = Column(Boolean, default=True)
    
    # Visibility
    profile_visibility = Column(String(20), default="private")  # private, connections, public
    health_data_visibility = Column(String(20), default="private")
    
    # Security
    require_biometric_auth = Column(Boolean, default=False)  # Mobile biometric lock
    session_timeout_minutes = Column(Integer, default=60)
    
    # Compliance
    gdpr_applies = Column(Boolean, default=False)  # User is in EU/EEA
    hipaa_applies = Column(Boolean, default=False)  # User is in US with covered entity
    data_residency_preference = Column(String(50), nullable=True)  # Preferred data region
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="privacy_settings")
    
    def __repr__(self):
        return f"<PrivacySettings(user_id={self.user_id}, gdpr={self.gdpr_applies})>"


class Translation(Base):
    """
    Multi-language content storage
    Supports i18n for global audience
    """
    __tablename__ = "translations"

    id = Column(Integer, primary_key=True, index=True)
    
    # Translation key
    key = Column(String(255), nullable=False, index=True)  # e.g., "dashboard.welcome_message"
    language_code = Column(String(10), nullable=False, index=True)  # ISO 639-1 (en, es, fr, de, ar, zh, etc.)
    
    # Content
    value = Column(Text, nullable=False)
    description = Column(String(500), nullable=True)  # Context for translators
    
    # Metadata
    category = Column(String(100), nullable=True, index=True)  # e.g., "ui", "email", "notification", "ai_response"
    platform = Column(String(20), nullable=True)  # web, ios, android, all
    
    # Version control
    version = Column(String(50), default="1.0")
    is_active = Column(Boolean, default=True, index=True)
    
    # Quality
    is_machine_translated = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)  # Verified by native speaker
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<Translation(key={self.key}, lang={self.language_code})>"
