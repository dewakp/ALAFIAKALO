"""Insights API — relationships (patterns) and forecasts (predicted states).

Basis cornerstones #4 (relationship graphs / cause-effect) and #5 (predict future
states). All AI-free statistics over the user's own logged data; results are
associations/projections, never clinical claims.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.health_signals import collect_signals, signal_label, signal_domain
from app.services.insights_engine import compute_relationships
from app.services.forecast_engine import forecast_signal, forecastable_signals

router = APIRouter()


@router.get("/signals")
async def list_signals(
    days: int = Query(90, ge=7, le=730),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the signals that have data for this user, with sample counts."""
    end = date.today()
    start = end - timedelta(days=days)
    signals = await collect_signals(db, current_user.id, start, end)
    return {
        "window_days": days,
        "signals": sorted(
            [
                {
                    "key": k,
                    "label": signal_label(k),
                    "domain": signal_domain(k),
                    "sample_size": len(v),
                }
                for k, v in signals.items()
            ],
            key=lambda s: s["sample_size"],
            reverse=True,
        ),
    }


@router.get("/relationships")
async def relationships(
    days: int = Query(90, ge=14, le=730),
    max_lag: int = Query(3, ge=0, le=14),
    min_samples: int = Query(5, ge=3, le=60),
    cross_domain_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ranked candidate relationships across the user's health signals."""
    end = date.today()
    start = end - timedelta(days=days)
    signals = await collect_signals(db, current_user.id, start, end)
    edges = compute_relationships(
        signals,
        max_lag=max_lag,
        min_samples=min_samples,
        cross_domain_only=cross_domain_only,
    )
    return {
        "window_days": days,
        "signal_count": len([k for k, v in signals.items() if len(v) >= min_samples]),
        "relationships": edges,
        "note": "Associations only — not proof of causation.",
    }


@router.get("/forecast")
async def forecast(
    signal: str | None = Query(None, description="Signal key, e.g. vital.weight_kg"),
    days: int = Query(90, ge=14, le=730),
    horizon: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Forecast a signal forward. With no `signal`, picks the most data-rich one."""
    end = date.today()
    start = end - timedelta(days=days)
    signals = await collect_signals(db, current_user.id, start, end)

    if not signal:
        candidates = forecastable_signals(signals)
        if not candidates:
            return {"signal": None, "forecast": None,
                    "note": "Not enough data yet — keep logging to unlock forecasts."}
        signal = candidates[0]

    if signal not in signals:
        raise HTTPException(status_code=404, detail=f"No data for signal '{signal}'")

    result = forecast_signal(signals[signal], horizon=horizon)
    if result is None:
        raise HTTPException(
            status_code=422,
            detail=f"Not enough data points to forecast '{signal}' (need at least 4).",
        )
    return {"signal": signal, "label": signal_label(signal), **result}
