"""Database engine and session management."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

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


async def get_db() -> AsyncSession:
    """Dependency that yields an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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
