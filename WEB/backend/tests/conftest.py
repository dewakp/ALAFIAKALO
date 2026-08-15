"""Shared pytest fixtures for the ALAFIA backend test suite."""

import asyncio
import sys
import types
from typing import AsyncGenerator
from unittest.mock import MagicMock

# ── Stub out modules that hang or require live services at import time ──────
# `limits` does backend-discovery (MongoDB, Redis, Memcached) at import;
# `firebase_admin` connects to GCP; both hang in offline CI/dev.
_STUB_MODULES = [
    "limits", "limits.errors", "limits.storage", "limits.strategies",
    "limits.typing", "limits._storage_scheme",
    "slowapi", "slowapi.errors", "slowapi.util", "slowapi.wrappers",
    "firebase_admin", "firebase_admin.credentials",
    "firebase_admin.auth", "firebase_admin.firestore",
    "google.cloud.firestore_v1",
]
for _mod in _STUB_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Provide the specific attributes slowapi needs so the Limiter instantiation
# in app.core.rate_limit doesn't raise AttributeError.
sys.modules["limits"].RateLimitItem = MagicMock()
sys.modules["limits.errors"].ConfigurationError = Exception
sys.modules["limits.storage"].MemoryStorage = MagicMock()
sys.modules["limits.storage"].storage_from_string = MagicMock()
sys.modules["limits.strategies"].STRATEGIES = {}
sys.modules["limits.strategies"].RateLimiter = MagicMock()
# A bare MagicMock makes `@limiter.limit(...)` replace the real route handlers
# with mocks (auth endpoints stop returning tokens → the whole suite goes red).
# Use a no-op Limiter whose .limit() is an identity decorator so endpoints stay real.
class _NoopLimiter:
    def __init__(self, *a, **k):
        pass

    def limit(self, *a, **k):
        def _decorator(func):
            return func
        return _decorator

    def __getattr__(self, name):
        return MagicMock()


sys.modules["slowapi"].Limiter = _NoopLimiter
sys.modules["slowapi"]._rate_limit_exceeded_handler = lambda *a, **k: None
sys.modules["slowapi.errors"].RateLimitExceeded = Exception

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.database import Base, get_db
import app.models  # noqa: F401 — registers all ORM models with Base.metadata

# Force LOCAL auth in tests: the shared 6IGMA Identity service is stateful (emails
# persist across runs → fixed-email register returns 409/400) and external. Stub the
# client so register/login/token-verify use the local fallback — hermetic + deterministic.
import app.services.identity_client as _identity_client  # noqa: E402


async def _identity_unavailable(*_a, **_k):
    return None


async def _identity_register_unavailable(*_a, **_k):
    return (503, None)  # (status, data) → register uses the local-only path


async def _identity_false(*_a, **_k):
    return False


_identity_client.identity_login = _identity_unavailable
_identity_client.verify_identity_token = _identity_unavailable
_identity_client.identity_register = _identity_register_unavailable
_identity_client.migrate_password_into_identity = _identity_false

# Open direct registration for tests.
#
# `TWO_STEP_SIGNUP_REQUIRED` defaults to True, which is the correct production
# posture — but almost every test in this suite builds its fixture user by
# POSTing /auth/register. With the gate on, each of those got a 410, then logged
# in as a user that was never created and read `access_token` off an error body:
# one KeyError repeated across ~28 tests, none of which are about signup policy.
# The gate itself is covered directly by test_auth.py.
from app.core.config import settings as _settings  # noqa: E402

_settings.TWO_STEP_SIGNUP_REQUIRED = False

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client bound to the FastAPI app, with CSRF token pre-set."""
    # Import app lazily so pure unit tests don't trigger the full app import chain
    from app.main import app  # noqa: PLC0415
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    csrf_token = "test-csrf-token"
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"csrf_token": csrf_token},
        headers={"X-CSRF-Token": csrf_token},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Direct DB session for seeding test data."""
    async with TestSession() as session:
        yield session
        await session.commit()
