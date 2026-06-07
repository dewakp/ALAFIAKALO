"""
ALAFIA — Holistic Health Platform
Main FastAPI application entry point.
"""

import secrets
import time

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging as _logging

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings, validate_production_settings
from app.core.rate_limit import limiter
from app.core.logging import setup_logging, get_logger

from app.api import router as api_router
from app.core.database import async_session
from app.api.ai_learning import seed_global_knowledge
from app.services.firebase_sync import sync_pipeline
from app.services.med_nutrient_service import seed_med_profiles

_scheduler = AsyncIOScheduler(timezone="UTC")

# ── Initialise structured logging ──
setup_logging()
logger = get_logger(__name__)

# ── Sentry error tracking ──
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,  # Never send PII to Sentry
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(
                level=_logging.WARNING,
                event_level=_logging.ERROR,
            ),
        ],
    )
    logger.info("Sentry error tracking initialised (env=%s)", settings.SENTRY_ENVIRONMENT)

app = FastAPI(
    title=settings.APP_NAME,
    description="ALAFIA Holistic Health Platform API",
    version="0.1.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow frontend dev server + any prod origins from env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security headers middleware ──
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# ── CSRF double-submit cookie middleware ──
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    # Issue a CSRF token cookie on every response if not present
    csrf_cookie = request.cookies.get("csrf_token")
    if not csrf_cookie:
        csrf_cookie = secrets.token_urlsafe(32)

    if request.method not in _CSRF_SAFE_METHODS and request.url.path.startswith("/api/v1/"):
        # Validate: header must match cookie (double-submit pattern)
        header_token = request.headers.get("X-CSRF-Token", "")
        if header_token != csrf_cookie:
            err_response = Response(
                content='{"detail":"CSRF token missing or invalid"}',
                status_code=403,
                media_type="application/json",
            )
            # Set the cookie on the 403 so the browser has it for the retry
            err_response.set_cookie(
                key="csrf_token",
                value=csrf_cookie,
                httponly=False,
                secure=not settings.DEBUG,
                samesite="lax",
                path="/",
            )
            return err_response

    response: Response = await call_next(request)
    response.set_cookie(
        key="csrf_token",
        value=csrf_cookie,
        httponly=False,  # JS must read it to send in header
        secure=not settings.DEBUG,
        samesite="lax",
        path="/",
    )
    return response


# ── PHI access audit logging middleware ──
_PHI_ROUTE_PREFIXES = (
    "/api/v1/labs", "/api/v1/medications", "/api/v1/nutrition",
    "/api/v1/fitness", "/api/v1/mood", "/api/v1/lifestyle",
    "/api/v1/mental-health", "/api/v1/chronic", "/api/v1/health-sync",
    "/api/v1/elimination", "/api/v1/wellness", "/api/v1/users/me",
    "/api/v1/telehealth", "/api/v1/insurance", "/api/v1/advanced-directives",
)


@app.middleware("http")
async def phi_access_audit_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith(_PHI_ROUTE_PREFIXES) and response.status_code < 400:
        user = request.headers.get("authorization", "anonymous")
        logger.info(
            "PHI access",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "ip": request.client.host if request.client else "unknown",
                "user_id": "bearer" if "Bearer" in user else "none",
            },
        )
    return response


# ── Request logging middleware ──
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    if request.url.path not in ("/api/health",):
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "ip": request.client.host if request.client else "unknown",
            },
        )
    return response


async def _firebase_sync_job() -> None:
    """Scheduled Firebase→PostgreSQL sync (every 12 hours)."""
    logger.info("[scheduler] Firebase sync started")
    try:
        async with async_session() as db:
            results = await sync_pipeline.sync_all_users(db)
            total = sum(v for v in results.values() if v > 0)
            logger.info("[scheduler] Firebase sync complete — %d new records across %d users", total, len(results))
    except Exception as exc:
        logger.error("[scheduler] Firebase sync error: %s", exc)


@app.on_event("startup")
async def startup_event():
    """Validate config & seed data on first boot."""
    validate_production_settings()
    logger.info("Starting %s (debug=%s)", settings.APP_NAME, settings.DEBUG)
    try:
        async with async_session() as db:
            count = await seed_global_knowledge(db)
            if count:
                logger.info("Seeded %d GlobalKnowledge entries", count)
            med_count = await seed_med_profiles(db)
            if med_count:
                logger.info("Seeded %d MedNutrientProfiles", med_count)
    except Exception as exc:
        logger.warning("DB seed skipped (DB may not be ready yet): %s", exc)

    # Start Redis-backed WebSocket managers
    try:
        from app.api.ws_messaging import manager as msg_manager
        from app.api.ws_telehealth import signaling_manager, chat_manager
        await msg_manager.startup()
        await signaling_manager.startup()
        await chat_manager.startup()
        logger.info("WebSocket managers started (Redis pub/sub if available)")
    except Exception as exc:
        logger.warning("WebSocket manager startup skipped: %s", exc)

    # Schedule Firebase sync every 12 hours, starting immediately
    _scheduler.add_job(
        _firebase_sync_job,
        trigger="interval",
        hours=12,
        id="firebase_sync",
        replace_existing=True,
        misfire_grace_time=300,
    )
    _scheduler.start()
    logger.info("[scheduler] Firebase sync scheduled every 12 h")
    # Run an immediate sync on startup
    await _firebase_sync_job()


@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully stop the background scheduler and Redis connections."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] Stopped")
    from app.api.ws_messaging import manager as msg_manager
    from app.api.ws_telehealth import signaling_manager, chat_manager
    from app.core.redis import close_redis
    await msg_manager.shutdown()
    await signaling_manager.shutdown()
    await chat_manager.shutdown()
    await close_redis()


@app.get("/api/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "app": settings.APP_NAME}


# Mount all API routes
app.include_router(api_router, prefix="/api/v1")

# WebSocket routes (no /api/v1 prefix — direct on root)
from app.api.ws_telehealth import router as ws_router
app.include_router(ws_router)

from app.api.ws_messaging import router as ws_messaging_router
app.include_router(ws_messaging_router)
