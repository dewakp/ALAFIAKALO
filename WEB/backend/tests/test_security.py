"""Tests for security utilities (JWT, password hashing, config validation)."""

import pytest
import jwt  # PyJWT (python-jose was retired); decode() API is compatible

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_password_reset_token,
    verify_password_reset_token,
)
from app.core.config import settings, validate_production_settings, _INSECURE_SECRET


def test_password_hash_and_verify():
    """Bcrypt hash is valid and verifiable."""
    hashed = hash_password("MySecurePass123")
    assert hashed != "MySecurePass123"
    assert verify_password("MySecurePass123", hashed)
    assert not verify_password("WrongPassword", hashed)


def test_access_token_structure():
    """Access token has correct claims."""
    token = create_access_token(data={"sub": "42"})
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_refresh_token_structure():
    """Refresh token has correct claims."""
    token = create_refresh_token(data={"sub": "42"})
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "42"
    assert payload["type"] == "refresh"


def test_password_reset_token_roundtrip():
    """Password reset token encodes and decodes user_id."""
    token = create_password_reset_token(user_id=99)
    uid = verify_password_reset_token(token)
    assert uid == 99


def test_password_reset_token_invalid():
    """Invalid token returns None."""
    assert verify_password_reset_token("garbage.token.here") is None


def test_validate_production_rejects_insecure_key():
    """Production mode MUST reject the default SECRET_KEY."""
    original_debug = settings.DEBUG
    original_key = settings.SECRET_KEY
    try:
        settings.DEBUG = False
        settings.SECRET_KEY = _INSECURE_SECRET
        with pytest.raises(RuntimeError, match="insecure default"):
            validate_production_settings()
    finally:
        settings.DEBUG = original_debug
        settings.SECRET_KEY = original_key
