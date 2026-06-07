"""
Audit Logging Utilities
Decorators and helpers for HIPAA/GDPR compliance
"""
from functools import wraps
from typing import Callable, Optional
from fastapi import Request
from sqlalchemy.orm import Session

from app.models.privacy import DataAccessPurpose
from app.services.privacy_service import PrivacyService


def log_phi_access(
    resource_type: str,
    access_type: str,
    purpose: DataAccessPurpose,
    get_resource_id: Optional[Callable] = None,
):
    """
    Decorator to automatically log PHI/PII access
    
    Usage:
        @log_phi_access("LabResult", "view_labs", DataAccessPurpose.TREATMENT)
        async def get_lab_results(user_id: int, db: Session):
            ...
    
    Args:
        resource_type: Type of resource being accessed
        access_type: Description of access type
        purpose: HIPAA purpose for access
        get_resource_id: Optional function to extract resource ID from result
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Execute the original function
            result = await func(*args, **kwargs)
            
            # Extract dependencies from kwargs
            db: Optional[Session] = kwargs.get('db')
            request: Optional[Request] = kwargs.get('request')
            current_user_id: Optional[int] = kwargs.get('current_user')
            user_id: Optional[int] = kwargs.get('user_id')
            
            # Log access if we have required dependencies
            if db and (user_id or current_user_id):
                try:
                    privacy_service = PrivacyService(db)
                    
                    # Determine resource ID
                    resource_id = None
                    if get_resource_id and result:
                        resource_id = get_resource_id(result)
                    
                    # Get IP and user agent from request
                    ip_address = None
                    user_agent = None
                    if request:
                        ip_address = request.client.host if request.client else None
                        user_agent = request.headers.get("user-agent")
                    
                    # Log the access
                    privacy_service.log_data_access(
                        user_id=user_id or current_user_id,
                        access_type=access_type,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        purpose=purpose,
                        accessed_by_system="api_endpoint",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                except Exception as e:
                    # Don't fail request if logging fails
                    print(f"Audit logging failed: {e}")
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Execute the original function
            result = func(*args, **kwargs)
            
            # Extract dependencies from kwargs
            db: Optional[Session] = kwargs.get('db')
            request: Optional[Request] = kwargs.get('request')
            current_user_id: Optional[int] = kwargs.get('current_user')
            user_id: Optional[int] = kwargs.get('user_id')
            
            # Log access if we have required dependencies
            if db and (user_id or current_user_id):
                try:
                    privacy_service = PrivacyService(db)
                    
                    # Determine resource ID
                    resource_id = None
                    if get_resource_id and result:
                        resource_id = get_resource_id(result)
                    
                    # Get IP and user agent from request
                    ip_address = None
                    user_agent = None
                    if request:
                        ip_address = request.client.host if request.client else None
                        user_agent = request.headers.get("user-agent")
                    
                    # Log the access
                    privacy_service.log_data_access(
                        user_id=user_id or current_user_id,
                        access_type=access_type,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        purpose=purpose,
                        accessed_by_system="api_endpoint",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                except Exception as e:
                    # Don't fail request if logging fails
                    print(f"Audit logging failed: {e}")
            
            return result
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def require_consent(consent_type: str, error_message: Optional[str] = None):
    """
    Decorator to require specific consent before accessing endpoint
    
    Usage:
        @require_consent("data_sharing_research", "You must consent to research participation")
        async def join_research_study(current_user: int, db: Session):
            ...
    """
    from app.models.privacy import ConsentType
    
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            db: Optional[Session] = kwargs.get('db')
            current_user_id: Optional[int] = kwargs.get('current_user')
            
            if db and current_user_id:
                privacy_service = PrivacyService(db)
                
                # Check consent
                has_consent = privacy_service.check_consent(
                    current_user_id,
                    ConsentType(consent_type)
                )
                
                if not has_consent:
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=error_message or f"Consent required: {consent_type}"
                    )
            
            return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            db: Optional[Session] = kwargs.get('db')
            current_user_id: Optional[int] = kwargs.get('current_user')
            
            if db and current_user_id:
                privacy_service = PrivacyService(db)
                
                # Check consent
                has_consent = privacy_service.check_consent(
                    current_user_id,
                    ConsentType(consent_type)
                )
                
                if not has_consent:
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=error_message or f"Consent required: {consent_type}"
                    )
            
            return func(*args, **kwargs)
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
