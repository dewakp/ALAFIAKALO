"""Tests for application configuration."""

import os
from unittest.mock import patch

from app.core.config import Settings


def test_default_debug_is_false():
    """DEBUG defaults to False for production safety."""
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
    assert s.DEBUG is False


def test_default_pool_settings():
    """DB pool defaults are reasonable."""
    s = Settings()
    assert s.DB_POOL_SIZE == 10
    assert s.DB_MAX_OVERFLOW == 20
    assert s.DB_POOL_RECYCLE == 1800


def test_smtp_defaults_unconfigured():
    """SMTP is not configured by default — safe for dev."""
    s = Settings()
    assert s.SMTP_HOST == ""


def test_sentry_defaults_empty():
    """Sentry DSN is empty by default."""
    s = Settings()
    assert s.SENTRY_DSN == ""


def test_log_level_default():
    """Default log level is INFO."""
    s = Settings()
    assert s.LOG_LEVEL == "INFO"
