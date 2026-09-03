"""
ALAFIA — Holistic Health Platform
Main FastAPI application entry point.
"""

import secrets
import time
from datetime import datetime, timedelta, timezone

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging as _logging

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.database import get_db
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


# ── Always-zoned ISO-8601 datetime normalizer ─────────────────────────────────
# Some legacy rows/columns serialize as *naive* ISO strings (no zone) because they
# were written with datetime.utcnow() into `DateTime` (not tz-aware) columns — e.g.
# ChronicCondition.created_at (models/chronic_condition.py). A naive datetime broke
# client decoders (iOS "Chronic Conditions … isn't in the correct format"). Rather
# than chase every schema and column, we normalize once at the edge: any JSON string
# that is a bare `YYYY-MM-DDTHH:MM:SS[.ffffff]` with no zone is treated as UTC and
# gets a trailing 'Z'. Strings already zoned (…Z / …±hh:mm) and date-only values are
# left untouched. This also repairs existing naive data on read.
import re as _re

_NAIVE_ISO_DT = _re.compile(rb'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)"')


@app.middleware("http")
async def normalize_datetimes_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    if not response.headers.get("content-type", "").startswith("application/json"):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    fixed = _NAIVE_ISO_DT.sub(rb'"\1Z"', body)
    if fixed == body:
        # No naive datetimes → still must re-emit the buffered body.
        new = Response(content=body, status_code=response.status_code)
    else:
        new = Response(content=fixed, status_code=response.status_code)
    # Preserve ALL original headers (incl. duplicate Set-Cookie on /auth/login);
    # only content-length is recomputed for the possibly-longer body.
    new.raw_headers = [(k, v) for (k, v) in response.raw_headers if k.lower() != b"content-length"]
    new.raw_headers.append((b"content-length", str(len(new.body)).encode()))
    return new


# ── CSRF double-submit cookie middleware ──
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _csrf_exempt(request: Request) -> bool:
    """CSRF protects against *ambient* browser credentials (cookies). Requests that
    authenticate with an explicit, non-ambient credential are not CSRF-vulnerable:

    - **Bearer-token requests** (mobile/native clients, and the web SPA which sends
      its token from localStorage) — the token is an explicit header a cross-site
      attacker can neither read nor force.
    - **Body-based token refresh** — mobile sends the refresh token in the body, with
      no ambient cookie. Only the *cookie*-based refresh (web) needs CSRF.
    """
    if request.headers.get("Authorization", "").startswith("Bearer "):
        return True
    if request.url.path == "/api/v1/auth/refresh" and not request.cookies.get("refresh_token"):
        return True
    # Payment-provider webhooks carry no browser credentials — they are
    # authenticated by a provider signature (verified in the handler), not CSRF.
    if request.url.path.startswith("/api/v1/subscription/webhook/"):
        return True
    return False


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    # Issue a CSRF token cookie on every response if not present
    csrf_cookie = request.cookies.get("csrf_token")
    if not csrf_cookie:
        csrf_cookie = secrets.token_urlsafe(32)

    if (request.method not in _CSRF_SAFE_METHODS
            and request.url.path.startswith("/api/v1/")
            and not _csrf_exempt(request)):
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


async def _geocode_practices_job() -> None:
    """Scheduled practice-facility geocoding (default: every 24h).

    Upgrades practice-facility coordinates from ZIP-fallback → exact street
    coordinates via the free US Census batch geocoder, and moves each facility's
    primary-practice clinicians to the resolved coordinates. Idempotent: it only
    scans rows that still lack precise coordinates (rows already marked 'exact' or
    'zip_fallback' are skipped), so re-runs are cheap and safe. Bounded to
    PRACTICE_GEOCODE_MAX_BATCHES passes per run to cap Census load.
    """
    logger.info("[scheduler] Practice geocode started")
    from app.services.census_geocode import bulk_geocode_practices  # lazy import
    total_matched = 0
    try:
        async with async_session() as db:
            for _ in range(max(1, settings.PRACTICE_GEOCODE_MAX_BATCHES)):
                result = await bulk_geocode_practices(
                    db, limit=settings.PRACTICE_GEOCODE_BATCH_LIMIT
                )
                await db.commit()
                if result.get("error"):
                    logger.warning("[scheduler] Practice geocode paused: %s", result["error"])
                    break
                total_matched += result.get("matched", 0)
                # Stop early when nothing left to scan or a pass matched nothing new.
                if result.get("scanned", 0) == 0 or result.get("matched", 0) == 0:
                    break
        logger.info(
            "[scheduler] Practice geocode complete — %d facilities matched this run",
            total_matched,
        )
    except Exception as exc:
        logger.error("[scheduler] Practice geocode error: %s", exc)


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

    # Schedule the one-directional, incremental Firebase→PostgreSQL sync.
    # Cadence + on/off come from settings (FIREBASE_SYNC_INTERVAL_SECONDS,
    # FIREBASE_SYNC_ENABLED) instead of being hardcoded. The job only fetches
    # records newer than each user's MAX(source_timestamp) watermark, so every
    # run is a delta. The first run is scheduled immediately (non-blocking) so
    # app startup never waits on Firestore.
    if settings.FIREBASE_SYNC_ENABLED:
        interval = max(30, settings.FIREBASE_SYNC_INTERVAL_SECONDS)
        _scheduler.add_job(
            _firebase_sync_job,
            trigger="interval",
            seconds=interval,
            id="firebase_sync",
            replace_existing=True,
            max_instances=1,   # never overlap a still-running sync
            coalesce=True,     # collapse any missed runs into a single catch-up
            misfire_grace_time=300,
            next_run_time=datetime.now(timezone.utc),  # run once right away
        )
        logger.info("[scheduler] Firebase sync enabled — every %ds (incremental)", interval)
    else:
        logger.info("[scheduler] Firebase sync disabled (set FIREBASE_SYNC_ENABLED=true)")

    # Server-side practice-facility geocoder — runs on a fixed cadence (default
    # every 24h) inside the backend process. The first run is delayed a few
    # minutes so a burst of restarts never hammers the Census API on boot; the
    # job is idempotent so overlapping runs are collapsed (coalesce/max_instances).
    if settings.PRACTICE_GEOCODE_ENABLED:
        hours = max(1, settings.PRACTICE_GEOCODE_INTERVAL_HOURS)
        _scheduler.add_job(
            _geocode_practices_job,
            trigger="interval",
            hours=hours,
            id="practice_geocode",
            replace_existing=True,
            max_instances=1,   # never overlap a still-running geocode pass
            coalesce=True,     # collapse missed runs into one catch-up
            misfire_grace_time=3600,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        logger.info("[scheduler] Practice geocode enabled — every %dh", hours)
    else:
        logger.info("[scheduler] Practice geocode disabled (set PRACTICE_GEOCODE_ENABLED=true)")

    # Start the shared scheduler if any job was registered (and not already running).
    if _scheduler.get_jobs() and not _scheduler.running:
        _scheduler.start()


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
    """LIVENESS: is this process up. Deliberately does not touch the database.

    `database: "not checked"` is stated outright because this endpoint returned a
    bare `{"status": "healthy"}` right through a total outage. During the
    PostgreSQL 16 → 18 upgrade on 2026-08-16 it answered 200 for eleven minutes
    while every data-backed request 500'd; Cloud Run saw a healthy service and so
    would any uptime monitor pointed here. Point monitoring at /api/ready.
    """
    return {"status": "healthy", "app": settings.APP_NAME, "version": settings.GIT_SHA,
            "database": "not checked — use /api/ready"}


@app.get("/api/ready", tags=["Health"])
async def readiness_check(response: Response, session=Depends(get_db)):
    """READINESS: can this process actually serve a request that needs data.

    Runs `SELECT 1` and returns 503 when it cannot. Separate from liveness on
    purpose — a database blip should take the service out of the load balancer,
    not kill and restart every container, which is what a failing liveness probe
    does and which makes an outage worse.
    """
    from sqlalchemy import text as _text

    # Injected through get_db rather than built here, so readiness exercises the
    # SAME path a real request takes — including the pool. Calling get_db()
    # directly also bypasses dependency_overrides, which made this endpoint dial
    # the configured host from inside a test that had overridden the database.
    #
    # When the connection cannot be opened at all, get_db itself raises 503
    # before this body runs, which is the correct answer. What is caught below is
    # a session that opened and then failed to query.
    started = time.perf_counter()
    try:
        await session.execute(_text("SELECT 1"))
    except Exception as exc:
        logger.error("Readiness check failed: %s", exc, exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "unreachable",
                "app": settings.APP_NAME, "version": settings.GIT_SHA}
    return {"status": "ready", "database": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "app": settings.APP_NAME, "version": settings.GIT_SHA}


@app.exception_handler(DBAPIError)
@app.exception_handler(OperationalError)
async def _database_unavailable_handler(request: Request, exc: Exception):
    """A database that cannot be reached is 503, not 500.

    During the upgrade a login attempt returned `500 Internal Server Error` with
    no body worth reading. 500 tells a client "this request was wrong or the app
    is broken"; 503 with Retry-After tells it "the service is down, come back" —
    which is the true statement, is retryable, and is what a client can act on.

    Only connection-level failures are translated. A constraint violation or a
    bad query is a real 500 and must keep saying so.
    """
    if not _is_connection_failure(exc):
        raise exc
    logger.error("Database unavailable on %s %s: %s",
                 request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "The service is temporarily unavailable. Please try again."},
        headers={"Retry-After": "15"},
    )


def _is_connection_failure(exc: Exception) -> bool:
    """True when the driver could not reach or talk to the server.

    Matched on the driver's own exception types rather than on message text:
    asyncpg raises these for a server that is down, restarting, or has closed the
    connection — exactly the states an upgrade passes through.
    """
    causes = []
    current: BaseException | None = exc
    while current is not None and len(causes) < 8:
        causes.append(current)
        current = current.__cause__
    for err in causes:
        if isinstance(err, OperationalError):
            return True
        if err.__class__.__module__.startswith("asyncpg") and isinstance(
            err, (ConnectionError, OSError)
        ):
            return True
        if err.__class__.__name__ in {
            "ConnectionDoesNotExistError", "ConnectionFailureError",
            "CannotConnectNowError", "TooManyConnectionsError",
            "PostgresConnectionError", "InterfaceError", "ConnectionRefusedError",
            "ServerNotRunningError",
        }:
            return True
    return False


# Mount all API routes. The paywall dependency runs first on every /api/v1 request:
# when SUBSCRIPTION_REQUIRED is on it 402s unsubscribed, non-exempt users on gated
# paths (auth/subscription/users stay open so they can sign in and pay).
from app.core.entitlement import require_active_subscription  # noqa: E402
app.include_router(api_router, prefix="/api/v1", dependencies=[Depends(require_active_subscription)])

# WebSocket routes (no /api/v1 prefix — direct on root)
from app.api.ws_telehealth import router as ws_router
app.include_router(ws_router)

from app.api.ws_messaging import router as ws_messaging_router
app.include_router(ws_messaging_router)

# Marketing unsubscribe — deliberately NOT under api_router. That router carries
# the paywall dependency, and the person most likely to click "unsubscribe" is
# the one whose subscription lapsed; a 402 there would trap them on a list they
# asked to leave. Public and unauthenticated by design.
from app.api.marketing import router as marketing_router  # noqa: E402
app.include_router(marketing_router)

# Contact form — also NOT under api_router, and for the same reason: the people
# most likely to need it are the ones who cannot get in (a lapsed subscription,
# an account that will not authenticate, a privacy request from someone who has
# already deleted theirs). A paywalled contact form is not a contact form.
from app.api.contact import router as contact_router  # noqa: E402
app.include_router(contact_router, prefix="/api/v1")
