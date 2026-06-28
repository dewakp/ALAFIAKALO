"""
Privacy and Compliance Service
Handles GDPR, HIPAA, and healthcare data privacy requirements
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import json
import secrets

import alafia_crypto as _rc  # Rust crypto backend

from app.models.privacy import (
    ConsentRecord,
    DataAccessLog,
    DataExportRequest,
    DataDeletionRequest,
    PrivacySettings,
    ConsentType,
    DataAccessPurpose,
    ExportStatus,
    DeletionStatus,
)
from app.models.user import User


class PrivacyService:
    """Service for managing privacy, consent, and compliance"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== CONSENT MANAGEMENT ====================
    
    def record_consent(
        self,
        user_id: int,
        consent_type: ConsentType,
        consent_granted: bool,
        consent_version: str,
        consent_text: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        language: str = "en",
        expires_at: Optional[datetime] = None,
    ) -> ConsentRecord:
        """
        Record user consent (GDPR Article 7)
        
        Args:
            user_id: User ID
            consent_type: Type of consent
            consent_granted: True = granted, False = withdrawn
            consent_version: Version of terms/policy
            consent_text: Full text of what user consented to
            ip_address: IP address for audit trail
            user_agent: Browser/app user agent
            language: Language of consent
            expires_at: Optional expiration date
            
        Returns:
            ConsentRecord
        """
        consent = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            consent_granted=consent_granted,
            consent_version=consent_version,
            consent_text=consent_text,
            consent_language=language,
            ip_address=ip_address,
            user_agent=user_agent,
            granted_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        
        self.db.add(consent)
        self.db.commit()
        self.db.refresh(consent)
        
        # Update privacy settings based on consent
        self._update_privacy_settings_from_consent(user_id, consent_type, consent_granted)
        
        # Log the consent action
        self.log_data_access(
            user_id=user_id,
            access_type="consent_update",
            resource_type="ConsentRecord",
            resource_id=consent.id,
            purpose=DataAccessPurpose.LEGAL_COMPLIANCE,
            data_accessed={"consent_type": consent_type.value, "granted": consent_granted},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        return consent
    
    def get_active_consents(self, user_id: int) -> List[ConsentRecord]:
        """Get all active (granted and not expired) consents for a user"""
        now = datetime.utcnow()
        return self.db.query(ConsentRecord).filter(
            and_(
                ConsentRecord.user_id == user_id,
                ConsentRecord.consent_granted == True,
                or_(
                    ConsentRecord.expires_at.is_(None),
                    ConsentRecord.expires_at > now
                )
            )
        ).order_by(ConsentRecord.granted_at.desc()).all()
    
    def check_consent(self, user_id: int, consent_type: ConsentType) -> bool:
        """Check if user has active consent for a specific type"""
        now = datetime.utcnow()
        consent = self.db.query(ConsentRecord).filter(
            and_(
                ConsentRecord.user_id == user_id,
                ConsentRecord.consent_type == consent_type,
                ConsentRecord.consent_granted == True,
                or_(
                    ConsentRecord.expires_at.is_(None),
                    ConsentRecord.expires_at > now
                )
            )
        ).order_by(ConsentRecord.granted_at.desc()).first()
        
        return consent is not None
    
    def _update_privacy_settings_from_consent(
        self,
        user_id: int,
        consent_type: ConsentType,
        granted: bool
    ):
        """Update privacy settings based on consent changes"""
        settings = self.get_or_create_privacy_settings(user_id)
        
        # Map consent types to privacy settings
        consent_mapping = {
            ConsentType.DATA_SHARING_ANONYMIZED: "allow_collective_insights",
            ConsentType.DATA_SHARING_RESEARCH: "allow_research_participation",
            ConsentType.MARKETING_COMMUNICATIONS: "allow_marketing_emails",
            ConsentType.AI_COACHING: "ai_coaching_enabled",
            ConsentType.COOKIES_ANALYTICS: "allow_usage_analytics",
        }
        
        if consent_type in consent_mapping:
            setattr(settings, consent_mapping[consent_type], granted)
            self.db.commit()
    
    # ==================== DATA ACCESS LOGGING (HIPAA/GDPR) ====================
    
    def log_data_access(
        self,
        user_id: int,
        access_type: str,
        resource_type: str,
        purpose: DataAccessPurpose,
        resource_id: Optional[int] = None,
        accessed_by_user_id: Optional[int] = None,
        accessed_by_system: Optional[str] = None,
        data_accessed: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> DataAccessLog:
        """
        Log PHI/PII access (HIPAA Security Rule, GDPR Article 30)
        
        Args:
            user_id: User whose data was accessed
            access_type: Type of access (e.g., "view_profile", "export_data")
            resource_type: Type of resource (e.g., "User", "LabResult")
            purpose: Purpose of access (HIPAA minimum necessary)
            resource_id: Specific record ID
            accessed_by_user_id: Admin/support user who accessed
            accessed_by_system: System component that accessed
            data_accessed: Summary of fields accessed (not full data)
            ip_address: IP address
            user_agent: Browser/app user agent
            
        Returns:
            DataAccessLog
        """
        log = DataAccessLog(
            user_id=user_id,
            access_type=access_type,
            resource_type=resource_type,
            resource_id=resource_id,
            purpose=purpose,
            accessed_by_user_id=accessed_by_user_id,
            accessed_by_system=accessed_by_system,
            data_accessed=data_accessed,
            ip_address=ip_address,
            user_agent=user_agent,
            accessed_at=datetime.utcnow(),
        )
        
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        
        return log
    
    def get_access_logs(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        purpose: Optional[DataAccessPurpose] = None,
        limit: int = 100,
    ) -> List[DataAccessLog]:
        """
        Get access logs for a user (GDPR Article 15 - right of access)
        Users can see who accessed their data and why
        """
        query = self.db.query(DataAccessLog).filter(DataAccessLog.user_id == user_id)
        
        if start_date:
            query = query.filter(DataAccessLog.accessed_at >= start_date)
        if end_date:
            query = query.filter(DataAccessLog.accessed_at <= end_date)
        if purpose:
            query = query.filter(DataAccessLog.purpose == purpose)
        
        return query.order_by(DataAccessLog.accessed_at.desc()).limit(limit).all()
    
    # ==================== PRIVACY SETTINGS ====================
    
    def get_or_create_privacy_settings(self, user_id: int) -> PrivacySettings:
        """Get user's privacy settings, create if not exists"""
        settings = self.db.query(PrivacySettings).filter(
            PrivacySettings.user_id == user_id
        ).first()
        
        if not settings:
            # Detect if GDPR applies based on user's country
            user = self.db.query(User).filter(User.id == user_id).first()
            gdpr_countries = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", 
                            "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
                            "PL", "PT", "RO", "SK", "SI", "ES", "SE", "GB", "NO", "IS", "LI"]
            
            settings = PrivacySettings(
                user_id=user_id,
                gdpr_applies=user.country in gdpr_countries if user and user.country else False,
                hipaa_applies=user.country == "US" if user and user.country else False,
            )
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
        
        return settings
    
    def update_privacy_settings(
        self,
        user_id: int,
        settings_update: Dict[str, Any]
    ) -> PrivacySettings:
        """Update user's privacy settings"""
        settings = self.get_or_create_privacy_settings(user_id)
        
        # Update allowed fields
        for key, value in settings_update.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        
        settings.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(settings)
        
        return settings
    
    # ==================== DATA EXPORT (GDPR Article 20) ====================
    
    def request_data_export(
        self,
        user_id: int,
        export_format: str = "json",
        include_attachments: bool = True,
        ip_address: Optional[str] = None,
    ) -> DataExportRequest:
        """
        Request data export (GDPR Article 20 - Right to data portability)
        User receives all their data in machine-readable format
        """
        # Check for existing pending/processing requests
        existing = self.db.query(DataExportRequest).filter(
            and_(
                DataExportRequest.user_id == user_id,
                DataExportRequest.status.in_([ExportStatus.PENDING, ExportStatus.PROCESSING])
            )
        ).first()
        
        if existing:
            return existing  # Return existing request
        
        request = DataExportRequest(
            user_id=user_id,
            status=ExportStatus.PENDING,
            export_format=export_format,
            include_attachments=include_attachments,
            requested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),  # Auto-delete after 7 days
            ip_address=ip_address,
        )
        
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        
        # Log the export request
        self.log_data_access(
            user_id=user_id,
            access_type="export_request",
            resource_type="DataExportRequest",
            resource_id=request.id,
            purpose=DataAccessPurpose.EXPORT_REQUEST,
            ip_address=ip_address,
        )
        
        return request
    
    def generate_data_export(self, request_id: int) -> Dict[str, Any]:
        """
        Generate comprehensive data export
        This should be run as a background job
        """
        request = self.db.query(DataExportRequest).filter(
            DataExportRequest.id == request_id
        ).first()
        
        if not request:
            raise ValueError("Export request not found")
        
        # Update status
        request.status = ExportStatus.PROCESSING
        self.db.commit()
        
        try:
            user = self.db.query(User).filter(User.id == request.user_id).first()
            
            # Collect all user data
            export_data = {
                "export_metadata": {
                    "generated_at": datetime.utcnow().isoformat(),
                    "user_id": user.id,
                    "format": request.export_format,
                    "gdpr_compliant": True,
                },
                "personal_information": {
                    "email": user.email,
                    "full_name": user.full_name,
                    "date_of_birth": user.date_of_birth,
                    "gender": user.gender,
                    "country": user.country,
                    "locale": user.locale,
                    "timezone": user.timezone,
                },
                "health_profile": {
                    "height_cm": user.height_cm,
                    "current_weight_kg": user.current_weight_kg,
                    "blood_type": user.blood_type,
                    "allergies": json.loads(user.allergies) if user.allergies else [],
                    "chronic_conditions": json.loads(user.chronic_conditions) if user.chronic_conditions else [],
                },
                "health_data": {
                    "nutrition_logs": [self._serialize_record(log) for log in user.nutrition_logs],
                    "fitness_logs": [self._serialize_record(log) for log in user.fitness_logs],
                    "lab_results": [self._serialize_record(log) for log in user.lab_results],
                    "medications": [self._serialize_record(log) for log in user.medications],
                    "mood_entries": [self._serialize_record(log) for log in user.mood_entries],
                    "sleep_logs": [self._serialize_record(log) for log in user.sleep_logs],
                    "vitals_logs": [self._serialize_record(log) for log in user.vitals_logs],
                },
                "ai_data": {
                    "memories": [self._serialize_record(mem) for mem in user.ai_memories],
                    "interactions": [self._serialize_record(int) for int in user.ai_interactions],
                },
                "privacy_data": {
                    "consents": [self._serialize_record(c) for c in user.consent_records],
                    "access_logs": [self._serialize_record(log) for log in user.data_access_logs[:100]],  # Last 100
                    "privacy_settings": self._serialize_record(user.privacy_settings) if user.privacy_settings else {},
                },
            }
            
            # Store export data (in production, save to secure storage like S3)
            file_path = f"/tmp/export_{user.id}_{request.id}.json"
            with open(file_path, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            file_size = len(json.dumps(export_data))
            
            # Update request
            request.status = ExportStatus.READY
            request.processed_at = datetime.utcnow()
            request.file_path = file_path
            request.file_size_bytes = file_size
            request.download_url = f"/api/v1/privacy/export/{request.id}/download"  # Signed URL
            
            self.db.commit()
            
            return export_data
            
        except Exception as e:
            request.status = ExportStatus.FAILED
            request.error_message = str(e)
            self.db.commit()
            raise
    
    def _serialize_record(self, record) -> Dict:
        """Convert SQLAlchemy record to dict"""
        if not record:
            return {}
        
        result = {}
        for column in record.__table__.columns:
            value = getattr(record, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result
    
    # ==================== RIGHT TO BE FORGOTTEN (GDPR Article 17) ====================
    
    def request_data_deletion(
        self,
        user_id: int,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> DataDeletionRequest:
        """
        Request account and data deletion (GDPR Article 17)
        Requires manual review for legal holds
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        
        request = DataDeletionRequest(
            user_id=user_id,
            user_email=user.email,
            user_full_name=user.full_name,
            status=DeletionStatus.PENDING,
            reason=reason,
            requested_at=datetime.utcnow(),
            ip_address=ip_address,
        )
        
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        
        # Log the deletion request
        self.log_data_access(
            user_id=user_id,
            access_type="deletion_request",
            resource_type="DataDeletionRequest",
            resource_id=request.id,
            purpose=DataAccessPurpose.LEGAL_COMPLIANCE,
            ip_address=ip_address,
        )
        
        return request
    
    def process_data_deletion(
        self,
        request_id: int,
        reviewed_by_user_id: int,
        approved: bool,
        retention_reason: Optional[str] = None,
        retention_until: Optional[datetime] = None,
    ) -> DataDeletionRequest:
        """
        Process deletion request (admin action)
        
        Args:
            request_id: Deletion request ID
            reviewed_by_user_id: Admin user ID
            approved: Whether to approve deletion
            retention_reason: Reason for retention (if rejected)
            retention_until: Date until retention required
        """
        request = self.db.query(DataDeletionRequest).filter(
            DataDeletionRequest.id == request_id
        ).first()
        
        if not request:
            raise ValueError("Deletion request not found")
        
        request.reviewed_at = datetime.utcnow()
        request.reviewed_by_user_id = reviewed_by_user_id
        
        if approved:
            request.status = DeletionStatus.APPROVED
            # Actual deletion will be done by background job
        else:
            request.status = DeletionStatus.REJECTED
            request.retention_required = True
            request.retention_reason = retention_reason
            request.retention_until = retention_until
        
        self.db.commit()
        self.db.refresh(request)
        
        return request
    
    def execute_data_deletion(self, request_id: int) -> Dict[str, Any]:
        """
        Execute approved deletion (background job)
        Deletes or anonymizes user data
        """
        request = self.db.query(DataDeletionRequest).filter(
            DataDeletionRequest.id == request_id,
            DataDeletionRequest.status == DeletionStatus.APPROVED
        ).first()
        
        if not request:
            raise ValueError("No approved deletion request found")
        
        request.status = DeletionStatus.PROCESSING
        self.db.commit()
        
        deletion_log = {
            "deleted_at": datetime.utcnow().isoformat(),
            "deleted_records": {},
        }
        
        try:
            user = self.db.query(User).filter(User.id == request.user_id).first()
            
            if user:
                # For collective insights, anonymize rather than delete
                anonymization_log = self._anonymize_for_collective_insights(user)
                deletion_log["anonymization"] = anonymization_log
                
                # Delete personal data (cascade will handle relationships)
                deletion_log["deleted_records"]["user_profile"] = True
                deletion_log["deleted_records"]["health_data"] = True
                deletion_log["deleted_records"]["ai_data"] = True
                deletion_log["deleted_records"]["privacy_data"] = True
                
                self.db.delete(user)
                self.db.commit()
            
            request.status = DeletionStatus.COMPLETED
            request.completed_at = datetime.utcnow()
            request.deletion_log = deletion_log
            self.db.commit()
            
            return deletion_log
            
        except Exception as e:
            request.status = DeletionStatus.PENDING
            request.notes = f"Deletion failed: {str(e)}"
            self.db.commit()
            raise
    
    def _anonymize_for_collective_insights(self, user: User) -> Dict[str, Any]:
        """
        Anonymize user data for collective insights before deletion
        Preserves statistical value while removing PII
        """
        # Create anonymized hash of user ID
        anon_id = _rc.sha512_hex(f"{user.id}_{secrets.token_hex(16)}")
        
        anonymization_log = {
            "original_user_id": user.id,
            "anonymized_id": anon_id,
            "preserved_data": {
                "age_range": self._get_age_range(user.date_of_birth),
                "gender_at_birth": user.gender_at_birth,
                "country": user.country,
                "activity_level": user.activity_level,
            },
            "records_anonymized": 0,
            "contributed_insights": [],
        }

        # Fold this user's de-identified footprint into the demographic
        # CollectiveInsight baselines before their PII is deleted. Consent-gated
        # inside the service; failures here must never block account deletion.
        try:
            from app.services.ai_memory_service import AIMemoryService
            memory = AIMemoryService(self.db)
            for category in ("nutrition", "fitness"):
                ci = memory.merge_demographic_baseline(user, category=category)
                if ci is not None:
                    self.db.flush()  # assign an id without committing the pending delete
                    anonymization_log["records_anonymized"] += 1
                    anonymization_log["contributed_insights"].append({
                        "insight_id": ci.id,
                        "category": ci.category,
                        "pattern_type": ci.pattern_type,
                        "sample_size": ci.sample_size,
                    })
        except Exception as exc:  # pragma: no cover - best effort
            anonymization_log["contribution_error"] = str(exc)

        return anonymization_log
    
    def _get_age_range(self, dob_str: Optional[str]) -> Optional[str]:
        """Convert exact DOB to age range for anonymization"""
        if not dob_str:
            return None
        
        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d")
            age = (datetime.now() - dob).days // 365
            
            if age < 18:
                return "under_18"
            elif age < 25:
                return "18-24"
            elif age < 35:
                return "25-34"
            elif age < 45:
                return "35-44"
            elif age < 55:
                return "45-54"
            elif age < 65:
                return "55-64"
            else:
                return "65_plus"
        except:
            return None
