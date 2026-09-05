"""Forecast engine (Basis req #5: predict future outcomes/states).

Projects a daily health signal forward with an ordinary least-squares trend over
recent history, plus a 95% band derived from the residual spread. This is a
deliberately simple, transparent baseline; the seam (`forecast_signal`) is where a
trained ML model (gap #5 "ML serving") can later be swapped in without changing
the API.

Pure-Python; no numpy.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


CAVEAT = "Projection from your recent trend — not a clinical prediction."

# z for ~95% interval
_Z95 = 1.96


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Return (slope, intercept, residual_std) for y = slope*x + intercept."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    n_free = max(n - 2, 1)
    resid_std = (sum(r * r for r in resid) / n_free) ** 0.5
    return slope, intercept, resid_std


def forecast_signal(
    series: dict[date, float],
    *,
    horizon: int = 7,
    min_points: int = 4,
) -> dict[str, Any] | None:
    """Forecast one signal `horizon` days past its last observation.

    Returns history + projected points with confidence bands, or None if there
    isn't enough data.
    """
    if len(series) < min_points:
        return None

    items = sorted(series.items())  # [(date, value), ...]
    base = items[0][0]
    xs = [(d - base).days for d, _ in items]
    ys = [v for _, v in items]

    slope, intercept, resid_std = _linear_fit(xs, ys)
    last_date = items[-1][0]
    last_x = xs[-1]

    projected: list[dict[str, Any]] = []
    for k in range(1, horizon + 1):
        x = last_x + k
        d = last_date + timedelta(days=k)
        yhat = slope * x + intercept
        margin = _Z95 * resid_std
        projected.append({
            "date": d.isoformat(),
            "value": round(yhat, 2),
            "lower": round(yhat - margin, 2),
            "upper": round(yhat + margin, 2),
        })

    history = [{"date": d.isoformat(), "value": round(v, 2)} for d, v in items]
    # Daily slope → trend label
    if abs(slope) < (resid_std / max(len(items), 1) + 1e-9) or abs(slope) < 1e-6:
        trend = "stable"
    else:
        trend = "rising" if slope > 0 else "falling"

    return {
        "history": history[-30:],          # cap history payload
        "forecast": projected,
        "slope_per_day": round(slope, 4),
        "trend": trend,
        "method": "linear_trend",
        "sample_size": len(items),
        "caveat": CAVEAT,
    }


def forecastable_signals(signals: dict[str, dict], min_points: int = 4) -> list[str]:
    """Signals with enough data to forecast, most-data first."""
    eligible = [(k, len(v)) for k, v in signals.items() if len(v) >= min_points]
    eligible.sort(key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in eligible]
