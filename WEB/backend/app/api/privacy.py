"""
Privacy and Compliance API Endpoints
GDPR, HIPAA, and healthcare data privacy
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.core.database import get_sync_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.privacy_service import PrivacyService
from app.services.i18n_service import I18nService
from app.models.privacy import (
    ConsentType,
    DataAccessPurpose,
    ExportStatus,
)


router = APIRouter(prefix="/privacy", tags=["privacy"])


# ==================== REQUEST/RESPONSE SCHEMAS ====================

class ConsentRequest(BaseModel):
    """Request to grant or withdraw consent"""
    consent_type: ConsentType
    consent_granted: bool
    consent_version: str = Field(..., description="Version of terms/policy")
    language: str = Field(default="en", description="Language of consent")


class ConsentResponse(BaseModel):
    """Consent record response"""
    id: int
    consent_type: str
    consent_granted: bool
    consent_version: str
    granted_at: datetime
    expires_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class PrivacySettingsUpdate(BaseModel):
    """Update privacy settings"""
    allow_anonymized_analytics: Optional[bool] = None
    allow_collective_insights: Optional[bool] = None
    allow_research_participation: Optional[bool] = None
    allow_marketing_emails: Optional[bool] = None
    allow_product_updates: Optional[bool] = None
    allow_health_reminders: Optional[bool] = None
    ai_coaching_enabled: Optional[bool] = None
    ai_memory_enabled: Optional[bool] = None
    ai_explainability_level: Optional[str] = None
    allow_third_party_integrations: Optional[bool] = None
    data_retention_days: Optional[int] = None
    auto_delete_old_data: Optional[bool] = None
    allow_location_tracking: Optional[bool] = None
    allow_usage_analytics: Optional[bool] = None
    profile_visibility: Optional[str] = None
    require_biometric_auth: Optional[bool] = None
    session_timeout_minutes: Optional[int] = None


class PrivacySettingsResponse(BaseModel):
    """Privacy settings response"""
    user_id: int
    allow_anonymized_analytics: bool
    allow_collective_insights: bool
    allow_research_participation: bool
    allow_marketing_emails: bool
    allow_product_updates: bool
    allow_health_reminders: bool
    ai_coaching_enabled: bool
    ai_memory_enabled: bool
    ai_explainability_level: str
    require_biometric_auth: bool
    session_timeout_minutes: int
    gdpr_applies: bool
    hipaa_applies: bool

    class Config:
        from_attributes = True

    # These columns are nullable in the DB (added in a later migration without a
    # backfill). Coerce any NULL to the model default so the mobile client — which
    # decodes them as non-optional — never gets a null and the endpoint never 500s.
    @field_validator(
        "allow_product_updates", "allow_health_reminders",
        "ai_explainability_level", "require_biometric_auth",
        "session_timeout_minutes", mode="before",
    )
    @classmethod
    def _default_if_null(cls, v, info):
        if v is None:
            return {
                "allow_product_updates": True,
                "allow_health_reminders": True,
                "ai_explainability_level": "standard",
                "require_biometric_auth": False,
                "session_timeout_minutes": 60,
            }[info.field_name]
        return v


class DataAccessLogResponse(BaseModel):
    """Data access log response"""
    id: int
    access_type: str
    resource_type: str
    purpose: str
    accessed_at: datetime
    ip_address: Optional[str] = None
    
    class Config:
        from_attributes = True


class ExportRequestResponse(BaseModel):
    """Data export request response"""
    id: int
    status: str
    export_format: str
    requested_at: datetime
    processed_at: Optional[datetime] = None
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    file_size_bytes: Optional[int] = None
    
    class Config:
        from_attributes = True


class DeletionRequestResponse(BaseModel):
    """Data deletion request response"""
    id: int
    status: str
    requested_at: datetime
    reviewed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retention_required: bool = False
    retention_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class TranslationResponse(BaseModel):
    """Translation response"""
    key: str
    value: str
    language_code: str
    
    class Config:
        from_attributes = True


# ==================== CONSENT MANAGEMENT ====================

@router.post("/consent", response_model=ConsentResponse)
def record_consent(
    consent_request: ConsentRequest,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record user consent (GDPR Article 7)
    
    - **consent_type**: Type of consent (terms, privacy_policy, data_sharing, etc.)
    - **consent_granted**: True to grant, False to withdraw
    - **consent_version**: Version of document user consented to
    """
    privacy_service = PrivacyService(db)
    
    # Get IP and user agent
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    consent = privacy_service.record_consent(
        user_id=current_user.id,
        consent_type=consent_request.consent_type,
        consent_granted=consent_request.consent_granted,
        consent_version=consent_request.consent_version,
        ip_address=ip_address,
        user_agent=user_agent,
        language=consent_request.language,
    )
    
    return consent


@router.get("/consent", response_model=List[ConsentResponse])
def get_consents(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all active consents for current user
    Shows what user has consented to
    """
    privacy_service = PrivacyService(db)
    consents = privacy_service.get_active_consents(current_user.id)
    return consents


@router.get("/consent/{consent_type}/status")
def check_consent(
    consent_type: ConsentType,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check if user has active consent for specific type
    Returns: {"has_consent": true/false}
    """
    privacy_service = PrivacyService(db)
    has_consent = privacy_service.check_consent(current_user.id, consent_type)
    return {"has_consent": has_consent, "consent_type": consent_type.value}


# ==================== PRIVACY SETTINGS ====================

@router.get("/settings", response_model=PrivacySettingsResponse)
def get_privacy_settings(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Get user's privacy settings"""
    privacy_service = PrivacyService(db)
    settings = privacy_service.get_or_create_privacy_settings(current_user.id)
    return settings


@router.put("/settings", response_model=PrivacySettingsResponse)
def update_privacy_settings(
    settings_update: PrivacySettingsUpdate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update privacy settings
    Granular control over data usage and sharing
    """
    privacy_service = PrivacyService(db)
    
    # Convert to dict, excluding None values
    update_dict = {k: v for k, v in settings_update.dict().items() if v is not None}
    
    settings = privacy_service.update_privacy_settings(current_user.id, update_dict)
    return settings


# ==================== DATA ACCESS LOGS (GDPR Article 15) ====================

@router.get("/access-logs", response_model=List[DataAccessLogResponse])
def get_access_logs(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    purpose: Optional[DataAccessPurpose] = None,
    limit: int = 100,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get data access logs (GDPR Article 15)
    
    Shows who accessed your data, when, and why.
    Part of right of access - users can audit access to their PHI/PII.
    
    - **start_date**: Filter from this date
    - **end_date**: Filter until this date
    - **purpose**: Filter by access purpose
    - **limit**: Maximum number of logs to return (default: 100)
    """
    privacy_service = PrivacyService(db)
    logs = privacy_service.get_access_logs(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        purpose=purpose,
        limit=limit,
    )
    return logs


# ==================== DATA EXPORT (GDPR Article 20) ====================

@router.post("/export", response_model=ExportRequestResponse)
def request_data_export(
    export_format: str = "json",
    include_attachments: bool = True,
    request: Request = None,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Request data export (GDPR Article 20 - Right to data portability)
    
    Export all your data in machine-readable format.
    Processing may take a few minutes. You'll receive a download link when ready.
    
    - **export_format**: Format (json, csv, pdf)
    - **include_attachments**: Include files and images
    """
    privacy_service = PrivacyService(db)
    
    ip_address = request.client.host if request and request.client else None
    
    export_request = privacy_service.request_data_export(
        user_id=current_user.id,
        export_format=export_format,
        include_attachments=include_attachments,
        ip_address=ip_address,
    )
    
    # In production, trigger background job to generate export
    # For now, generate synchronously (should be async in production)
    if export_request.status == ExportStatus.PENDING:
        try:
            privacy_service.generate_data_export(export_request.id)
            db.refresh(export_request)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Export generation failed: {str(e)}"
            )
    
    return export_request


@router.get("/export/{request_id}", response_model=ExportRequestResponse)
def get_export_status(
    request_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get status of data export request
    Check if export is ready for download
    """
    export_request = db.query(DataExportRequest).filter(
        DataExportRequest.id == request_id,
        DataExportRequest.user_id == current_user.id,
    ).first()
    
    if not export_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export request not found"
        )
    
    return export_request


@router.get("/export/{request_id}/download")
def download_export(
    request_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Download exported data
    Only available when status is READY
    """
    from fastapi.responses import FileResponse
    
    export_request = db.query(DataExportRequest).filter(
        DataExportRequest.id == request_id,
        DataExportRequest.user_id == current_user.id,
    ).first()
    
    if not export_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export request not found"
        )
    
    if export_request.status != ExportStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export not ready. Current status: {export_request.status}"
        )
    
    # Check expiration
    if export_request.expires_at and export_request.expires_at < datetime.utcnow():
        export_request.status = ExportStatus.EXPIRED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Export has expired. Please request a new export."
        )
    
    # Update download count
    export_request.downloaded_at = datetime.utcnow()
    export_request.download_count += 1
    db.commit()
    
    # Return file
    return FileResponse(
        path=export_request.file_path,
        filename=f"alafia_data_export_{current_user.id}.{export_request.export_format}",
        media_type="application/json",
    )


# ==================== RIGHT TO BE FORGOTTEN (GDPR Article 17) ====================

@router.post("/delete-account", response_model=DeletionRequestResponse)
def request_account_deletion(
    reason: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Request account and data deletion (GDPR Article 17 - Right to be forgotten)
    
    ⚠️ This will permanently delete all your data.
    Request requires manual review and may take 7-30 days to process.
    
    - **reason**: Optional reason for deletion
    """
    privacy_service = PrivacyService(db)
    
    ip_address = request.client.host if request and request.client else None
    
    deletion_request = privacy_service.request_data_deletion(
        user_id=current_user.id,
        reason=reason,
        ip_address=ip_address,
    )
    
    return deletion_request


@router.get("/delete-account/status", response_model=DeletionRequestResponse)
def get_deletion_status(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check status of account deletion request
    """
    deletion_request = db.query(DataDeletionRequest).filter(
        DataDeletionRequest.user_id == current_user.id
    ).order_by(DataDeletionRequest.requested_at.desc()).first()
    
    if not deletion_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No deletion request found"
        )
    
    return deletion_request


# ==================== TRANSLATIONS (i18n) ====================

@router.get("/translations/{language_code}")
def get_translations(
    language_code: str,
    category: Optional[str] = None,
    platform: Optional[str] = None,
    db: Session = Depends(get_sync_db),
):
    """
    Get all translations for a language
    Used by mobile apps to load language packs
    
    - **language_code**: ISO 639-1 language code (en, es, fr, etc.)
    - **category**: Optional category filter (ui, email, notification)
    - **platform**: Optional platform filter (web, ios, android)
    """
    i18n_service = I18nService(db)
    
    translations = i18n_service.get_all_translations_for_language(
        language_code=language_code,
        category=category,
        platform=platform,
    )
    
    return {
        "language_code": language_code,
        "translations": translations,
        "is_rtl": i18n_service.is_rtl_language(language_code),
    }


@router.get("/languages")
def get_supported_languages(
    accept_language: Optional[str] = Header(None),
    db: Session = Depends(get_sync_db),
):
    """
    Get list of supported languages
    Returns language codes and names
    """
    i18n_service = I18nService(db)
    
    # Detect preferred language from header
    preferred = i18n_service.detect_language_from_accept_header(accept_language)
    
    languages = []
    for lang_code in i18n_service.SUPPORTED_LANGUAGES:
        languages.append({
            "code": lang_code,
            "name": i18n_service.get_language_name(lang_code, lang_code),  # Native name
            "name_english": i18n_service.get_language_name(lang_code, "en"),
            "is_rtl": i18n_service.is_rtl_language(lang_code),
        })
    
    return {
        "supported_languages": languages,
        "preferred_language": preferred,
    }


from app.models.privacy import DataExportRequest, DataDeletionRequest
