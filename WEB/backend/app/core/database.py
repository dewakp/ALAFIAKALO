"""Database engine and session management."""

from sqlalchemy import create_engine
import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ── Synchronous engine/session ──────────────────────────────────────────────
# Some services (PrivacyService, AIMemoryService) are written against the sync
# SQLAlchemy ORM API (``Session.query(...)``). Endpoints that use them are
# declared as plain ``def`` so FastAPI runs them in a threadpool, and they take
# ``get_sync_db`` — so sync DB I/O never blocks the async event loop.
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=sync_engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


#: Connect-time failures that mean "the server is not reachable", as opposed to
#: "your query was wrong". asyncpg raises the OSError family (socket.gaierror
#: when DNS is gone, ConnectionRefusedError when the port is shut) BEFORE
#: SQLAlchemy wraps anything, so these never arrive as DBAPIError and an
#: exception handler registered on DBAPIError never sees them.
_CONNECT_FAILURES = (OSError, ConnectionError, TimeoutError)


async def get_db() -> AsyncSession:
    """Dependency that yields an async database session.

    A database that cannot be reached is 503, not 500. During the PostgreSQL
    16 → 18 upgrade a login returned `500 Internal Server Error` with no body
    worth reading: 500 tells a client "this request was wrong or the app is
    broken", while 503 with Retry-After says "the service is down, come back",
    which is true, retryable, and something a client can act on.

    Only failures to CONNECT are translated. A constraint violation or a bad
    query is a genuine 500 and keeps saying so.
    """
    try:
        session_ctx = async_session()
        session = await session_ctx.__aenter__()
    except _CONNECT_FAILURES as exc:
        logger.error("Database unreachable while opening a session: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="The service is temporarily unavailable. Please try again.",
            headers={"Retry-After": "15"},
        ) from exc

    try:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    except _CONNECT_FAILURES as exc:
        # The pool handed back a socket that was alive when it was checked out
        # and is not any more — a server restarting underneath us.
        logger.error("Database unreachable mid-request: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="The service is temporarily unavailable. Please try again.",
            headers={"Retry-After": "15"},
        ) from exc
    finally:
        await session_ctx.__aexit__(None, None, None)


def get_sync_db():
    """Dependency that yields a synchronous database session.

    For use by sync (``def``) endpoints backed by sync ORM services. Commits on
    success, rolls back on error, always closes.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
