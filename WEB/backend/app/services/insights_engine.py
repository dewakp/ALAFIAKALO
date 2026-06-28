"""Relationship / cause-effect engine (Basis req #4: patterns, relationship graphs,
cause & effect).

Computes lagged Pearson correlations between the user's daily health signals. A
positive lag means the *source* signal precedes the *target* by N days — a hint at
a possible lead/lag relationship (e.g. high-sodium day → next-day weight/BP).

IMPORTANT: these are statistical *associations*, never proof of causation. Every
edge carries that caveat and is meant to prompt curiosity, not clinical decisions.

Pure-Python; no numpy.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.services.health_signals import signal_domain, signal_label

CAVEAT = "Association only — not proof of cause. Discuss with your care team."


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / ((sxx * syy) ** 0.5)


def _aligned(
    a: dict, b: dict, lag_days: int
) -> tuple[list[float], list[float]]:
    """Pair a[d] with b[d + lag] over the dates they share."""
    xs: list[float] = []
    ys: list[float] = []
    for d, av in a.items():
        bd = d + timedelta(days=lag_days)
        if bd in b:
            xs.append(av)
            ys.append(b[bd])
    return xs, ys


def compute_relationships(
    signals: dict[str, dict],
    *,
    max_lag: int = 3,
    min_samples: int = 5,
    min_strength: float = 0.35,
    cross_domain_only: bool = True,
    top_k: int = 30,
) -> list[dict[str, Any]]:
    """Rank candidate relationships across the user's signals.

    Returns a list of edges sorted by |strength|, each:
      {source, target, source_label, target_label, strength, direction,
       lag_days, sample_size, caveat}
    """
    keys = [k for k, v in signals.items() if len(v) >= min_samples]
    edges: list[dict[str, Any]] = []

    for i, a in enumerate(keys):
        for b in keys:
            if a == b:
                continue
            if cross_domain_only and signal_domain(a) == signal_domain(b):
                continue
            # For lag 0 the correlation is symmetric — only keep one ordering.
            for lag in range(0, max_lag + 1):
                if lag == 0 and keys.index(b) <= i:
                    continue
                xs, ys = _aligned(signals[a], signals[b], lag)
                if len(xs) < min_samples:
                    continue
                r = _pearson(xs, ys)
                if r is None or abs(r) < min_strength:
                    continue
                edges.append({
                    "source": a,
                    "target": b,
                    "source_label": signal_label(a),
                    "target_label": signal_label(b),
                    "strength": round(r, 3),
                    "direction": "co-occurs" if lag == 0 else "leads",
                    "lag_days": lag,
                    "sample_size": len(xs),
                    "caveat": CAVEAT,
                })

    # Best edge per unordered signal pair (strongest |r| across lags/directions).
    best: dict[frozenset, dict] = {}
    for e in edges:
        pair = frozenset((e["source"], e["target"]))
        cur = best.get(pair)
        if cur is None or abs(e["strength"]) > abs(cur["strength"]):
            best[pair] = e

    ranked = sorted(best.values(), key=lambda e: abs(e["strength"]), reverse=True)
    return ranked[:top_k]
