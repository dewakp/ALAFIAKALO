"""Admin console API.

Single-operator console for ALAFIA, served at `minister.alafia.com`. Every
endpoint is gated by `require_admin` — the hostname is routing, never
authorization, because a Host header proves nothing.

Endpoints:
    GET /admin/overview      headline counts for the dashboard
    GET /admin/users         every registered user, searchable + paginated
    GET /admin/users/{id}    one user in detail
    GET /admin/health        live app health: DB, migrations, AI, corpus
    GET /admin/token-usage   LLM token usage per user over a window

This surface reads patient-adjacent data. It deliberately returns *counts and
metadata* — never clinical records — so the console can answer "is the app
healthy and who is using it" without becoming a back door into health data.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.ai_memory import AIInteraction
from app.models.subscription import Subscription
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


def _iso(value: datetime | None) -> str | None:
    """Always-zoned ISO-8601, matching the rest of the API."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


# ── Overview ─────────────────────────────────────────────────────────────
@router.get("/overview")
async def admin_overview(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    day_ago, week_ago, month_ago = (now - timedelta(days=n) for n in (1, 7, 30))

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active_users = (await db.execute(
        select(func.count(User.id)).where(User.is_active.is_(True)))).scalar() or 0
    never_logged_in = (await db.execute(
        select(func.count(User.id)).where(User.last_login.is_(None)))).scalar() or 0

    async def _since(column, cutoff):
        return (await db.execute(select(func.count(User.id)).where(column >= cutoff))).scalar() or 0

    signups_30d = await _since(User.created_at, month_ago)
    active_24h = await _since(User.last_login, day_ago)
    active_7d = await _since(User.last_login, week_ago)
    active_30d = await _since(User.last_login, month_ago)

    interactions_30d = (await db.execute(
        select(func.count(AIInteraction.id)).where(AIInteraction.created_at >= month_ago)
    )).scalar() or 0
    tokens_30d = (await db.execute(
        select(func.coalesce(func.sum(AIInteraction.tokens_used), 0))
        .where(AIInteraction.created_at >= month_ago)
    )).scalar() or 0

    subs = dict((await db.execute(
        select(Subscription.status, func.count(Subscription.id)).group_by(Subscription.status)
    )).all())

    return {
        "generated_at": _iso(now),
        "users": {
            "total": total_users,
            "active_flag": active_users,
            "never_logged_in": never_logged_in,
            "signups_30d": signups_30d,
            "logged_in_24h": active_24h,
            "logged_in_7d": active_7d,
            "logged_in_30d": active_30d,
        },
        "ai": {"interactions_30d": interactions_30d, "tokens_30d": int(tokens_30d)},
        "subscriptions_by_status": {str(k): v for k, v in subs.items()},
    }


# ── Users ────────────────────────────────────────────────────────────────
@router.get("/users")
async def admin_list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="match on email or full name"),
    sort: str = Query("last_login", pattern="^(last_login|created_at|email|tokens)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Every registered user, with last login and lifetime token usage."""
    # Token totals per user, joined in one query rather than N+1.
    usage_sq = (
        select(
            AIInteraction.user_id.label("uid"),
            func.coalesce(func.sum(AIInteraction.tokens_used), 0).label("tokens"),
            func.count(AIInteraction.id).label("interactions"),
            func.max(AIInteraction.created_at).label("last_interaction"),
        )
        .group_by(AIInteraction.user_id)
        .subquery()
    )

    stmt = select(User, usage_sq.c.tokens, usage_sq.c.interactions, usage_sq.c.last_interaction) \
        .outerjoin(usage_sq, usage_sq.c.uid == User.id)

    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            func.lower(User.email).like(needle) | func.lower(func.coalesce(User.full_name, "")).like(needle)
        )

    sort_col = {
        "last_login": User.last_login,
        "created_at": User.created_at,
        "email": User.email,
        "tokens": usage_sq.c.tokens,
    }[sort]
    # NULLs last on descending sorts — "never logged in" should not top the list.
    stmt = stmt.order_by(sort_col.desc().nullslast() if order == "desc" else sort_col.asc().nullsfirst())

    total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).all()

    sub_rows = dict((await db.execute(
        select(Subscription.user_id, Subscription.status)
    )).all())

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "is_active": u.is_active,
                "is_superuser": u.is_superuser,
                "auth_provider": u.auth_provider,
                "country": getattr(u, "country", None),
                "created_at": _iso(u.created_at),
                "last_login": _iso(u.last_login),
                "subscription_status": str(sub_rows.get(u.id)) if sub_rows.get(u.id) else None,
                "tokens_used": int(tokens or 0),
                "ai_interactions": int(interactions or 0),
                "last_interaction": _iso(last_interaction),
            }
            for (u, tokens, interactions, last_interaction) in rows
        ],
    }


@router.get("/users/{user_id}")
async def admin_user_detail(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    tokens, interactions, first_seen, last_seen = (await db.execute(
        select(
            func.coalesce(func.sum(AIInteraction.tokens_used), 0),
            func.count(AIInteraction.id),
            func.min(AIInteraction.created_at),
            func.max(AIInteraction.created_at),
        ).where(AIInteraction.user_id == user_id)
    )).one()

    by_model = [
        {"model": m or "-", "provider": p or "-", "interactions": c, "tokens": int(t or 0)}
        for (m, p, c, t) in (await db.execute(
            select(
                AIInteraction.llm_model, AIInteraction.llm_provider,
                func.count(AIInteraction.id),
                func.coalesce(func.sum(AIInteraction.tokens_used), 0),
            )
            .where(AIInteraction.user_id == user_id)
            .group_by(AIInteraction.llm_model, AIInteraction.llm_provider)
            .order_by(func.count(AIInteraction.id).desc())
        )).all()
    ]

    subscription = (await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )).scalars().first()

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "auth_provider": user.auth_provider,
        "created_at": _iso(user.created_at),
        "last_login": _iso(user.last_login),
        "subscription": {
            "status": str(subscription.status) if subscription else None,
            "current_period_end": _iso(getattr(subscription, "current_period_end", None)),
        } if subscription else None,
        "usage": {
            "tokens_used": int(tokens or 0),
            "ai_interactions": int(interactions or 0),
            "first_interaction": _iso(first_seen),
            "last_interaction": _iso(last_seen),
            "by_model": by_model,
        },
    }


# ── App health ───────────────────────────────────────────────────────────
@router.get("/health")
async def admin_app_health(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Live health. Each probe reports its own status so one failure does not
    mask the rest, and every probe is timed — a slow dependency is a problem
    long before it is a down one."""
    checks: list[dict] = []

    async def probe(name: str, coro_factory, detail_on_ok=None):
        t0 = time.monotonic()
        try:
            value = await coro_factory()
            checks.append({
                "name": name, "status": "ok",
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "detail": detail_on_ok(value) if detail_on_ok else value,
            })
        except Exception as exc:
            checks.append({
                "name": name, "status": "error",
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "detail": str(exc)[:300],
            })

    # Database round trip.
    async def _db_ping():
        return (await db.execute(text("SELECT 1"))).scalar()
    await probe("database", _db_ping, lambda v: "reachable")

    # Migration state: what this DB is stamped at. Drift here explains most
    # "column does not exist" incidents.
    async def _alembic():
        rev = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        return rev or "unstamped"
    await probe("migration_revision", _alembic)

    # Table counts that indicate the app is actually being used.
    async def _counts():
        users = (await db.execute(select(func.count(User.id)))).scalar() or 0
        interactions = (await db.execute(select(func.count(AIInteraction.id)))).scalar() or 0
        return f"{users} users, {interactions} AI interactions"
    await probe("data", _counts)

    # Vision training corpus — the Phase 5 readiness number.
    async def _corpus():
        from app.services.food_vision_store import corpus_stats
        s = await corpus_stats(db)
        return f"{s['samples']} samples, {s['corrected']} corrected, {s['images_retained']} images"
    await probe("vision_corpus", _corpus)

    # AI reachability. Reports which backends are configured without leaking keys.
    async def _ai():
        configured = []
        if settings.OPENAI_API_KEY:
            configured.append("openai")
        if getattr(settings, "OLLAMA_BASE_URL", ""):
            configured.append(f"ollama({settings.OLLAMA_BASE_URL})")
        if not configured:
            raise RuntimeError("no LLM backend configured")
        return ", ".join(configured)
    await probe("ai_backends", _ai)

    # Email: signup cannot complete without it, so it belongs in health.
    async def _email():
        from app.services import email as email_service
        provider = email_service.email_provider()
        if provider == "none":
            raise RuntimeError("no email provider configured — signup cannot complete")
        return provider
    await probe("email", _email)

    overall = "ok" if all(c["status"] == "ok" for c in checks) else "degraded"
    return {
        "status": overall,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "app": settings.APP_NAME,
        "version": settings.GIT_SHA,
        "checks": checks,
    }


# ── Token usage ──────────────────────────────────────────────────────────
@router.get("/token-usage")
async def admin_token_usage(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=500),
):
    """Token spend per user over a window, plus a by-model breakdown."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (await db.execute(
        select(
            User.id, User.email, User.full_name,
            func.coalesce(func.sum(AIInteraction.tokens_used), 0).label("tokens"),
            func.count(AIInteraction.id).label("interactions"),
            func.max(AIInteraction.created_at).label("last_interaction"),
        )
        .join(AIInteraction, AIInteraction.user_id == User.id)
        .where(AIInteraction.created_at >= since)
        .group_by(User.id, User.email, User.full_name)
        .order_by(func.coalesce(func.sum(AIInteraction.tokens_used), 0).desc())
        .limit(limit)
    )).all()

    by_model = [
        {"model": m or "-", "provider": p or "-", "interactions": c, "tokens": int(t or 0)}
        for (m, p, c, t) in (await db.execute(
            select(
                AIInteraction.llm_model, AIInteraction.llm_provider,
                func.count(AIInteraction.id),
                func.coalesce(func.sum(AIInteraction.tokens_used), 0),
            )
            .where(AIInteraction.created_at >= since)
            .group_by(AIInteraction.llm_model, AIInteraction.llm_provider)
            .order_by(func.coalesce(func.sum(AIInteraction.tokens_used), 0).desc())
        )).all()
    ]

    total_tokens = sum(int(r.tokens or 0) for r in rows)
    total_interactions = sum(int(r.interactions or 0) for r in rows)

    return {
        "window_days": days,
        "since": _iso(since),
        "totals": {"tokens": total_tokens, "interactions": total_interactions},
        # Token counts are only as good as what the providers report; a model
        # that returns no usage contributes 0 and would understate the total.
        "note": "Counts come from provider-reported usage on each interaction.",
        "by_model": by_model,
        "top_users": [
            {
                "user_id": r.id, "email": r.email, "full_name": r.full_name,
                "tokens": int(r.tokens or 0), "interactions": int(r.interactions or 0),
                "last_interaction": _iso(r.last_interaction),
            }
            for r in rows
        ],
    }
