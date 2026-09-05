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

import math
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


# ── Significance ──────────────────────────────────────────────────────
#
# The first version kept any |r| >= 0.35 computed over as few as FIVE daily
# points, with no p-value and no correction. That is data dredging, and it
# showed: one page load tests roughly 460 hypotheses (12 signals x lags 0-3),
# the 5% critical |r| at n=5 is 0.878, and the screen filled with rows like
# "Sugar leads by 3d -> Mood, +0.85, n=5". Mood appeared in eight of twelve
# rows, correlating with potassium, carbs, sodium, sugar, calories and
# phosphorus at once, in both directions — the signature of five data points,
# not of physiology.
#
# So an edge must now survive a two-sided t-test AND a Benjamini-Hochberg
# correction across every hypothesis the run tested. Most days that leaves
# nothing, which is the honest answer for a fortnight of logs.

#: Below this, a correlation cannot be assessed at all, whatever its value.
MIN_SAMPLES_FLOOR = 10

#: False-discovery rate for the Benjamini-Hochberg step.
FDR_Q = 0.10


def _p_value(r: float, n: int) -> float:
    """Two-sided p for a Pearson r under the usual t transform."""
    if n < 3 or abs(r) >= 1.0:
        return 0.0 if abs(r) >= 1.0 else 1.0
    df = n - 2
    t = abs(r) * math.sqrt(df / max(1e-12, 1.0 - r * r))
    # Student-t survival via the regularised incomplete beta, two-sided.
    x = df / (df + t * t)
    return max(0.0, min(1.0, _betainc(df / 2.0, 0.5, x)))


def _betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b), continued fraction (Lentz)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(
        lbeta + b * math.log(1.0 - x) + a * math.log(x)
    ) * _betacf(b, a, 1.0 - x) / b


def _betacf(a: float, b: float, x: float, iters: int = 200) -> float:
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, iters + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-7:
            break
    return h


def _survives_fdr(edges: list[dict], *, m_total: int | None = None,
                  q: float = FDR_Q) -> list[dict]:
    """Benjamini-Hochberg across every hypothesis this run tested.

    The correction must count ALL tests performed, not just the ones that
    happened to clear a strength threshold — otherwise the multiple-comparison
    problem is simply hidden rather than corrected.
    """
    if not edges:
        return []
    m = max(m_total or len(edges), len(edges))
    ranked = sorted(edges, key=lambda e: e["p_value"])
    cutoff = 0
    for i, e in enumerate(ranked, start=1):
        if e["p_value"] <= (i / m) * q:
            cutoff = i
    return ranked[:cutoff]


def compute_relationships(
    signals: dict[str, dict],
    *,
    max_lag: int = 3,
    min_samples: int = MIN_SAMPLES_FLOOR,
    min_strength: float = 0.35,
    cross_domain_only: bool = True,
    top_k: int = 30,
) -> list[dict[str, Any]]:
    """Rank candidate relationships across the user's signals.

    Returns a list of edges sorted by |strength|, each:
      {source, target, source_label, target_label, strength, direction,
       lag_days, sample_size, caveat}
    """
    # Never below the floor, whatever the caller asks for. Five points cannot
    # support a correlation and no threshold on |r| repairs that.
    min_samples = max(min_samples, MIN_SAMPLES_FLOOR)
    keys = [k for k, v in signals.items() if len(v) >= min_samples]
    edges: list[dict[str, Any]] = []
    tested = 0   # every correlation computed, for the FDR denominator

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
                if r is None:
                    continue
                # EVERY hypothesis tested is recorded, including the weak ones —
                # Benjamini-Hochberg needs the true denominator. Filtering by
                # |r| first would hide the multiple-comparison problem rather
                # than correct it.
                tested += 1
                if abs(r) < min_strength:
                    continue
                edges.append({
                    "source": a,
                    "target": b,
                    "source_label": signal_label(a),
                    "target_label": signal_label(b),
                    "strength": round(r, 3),
                    # NOT "leads". The banner says these are associations, not
                    # cause and effect, and then the UI drew a causal arrow.
                    # A lag is an offset we tested, not a direction of effect.
                    "direction": "same-day" if lag == 0 else "offset",
                    "lag_days": lag,
                    "sample_size": len(xs),
                    "p_value": _p_value(r, len(xs)),
                    "caveat": CAVEAT,
                })

    # Best edge per unordered signal pair (strongest |r| across lags/directions).
    best: dict[frozenset, dict] = {}
    for e in edges:
        pair = frozenset((e["source"], e["target"]))
        cur = best.get(pair)
        if cur is None or abs(e["strength"]) > abs(cur["strength"]):
            best[pair] = e

    # Benjamini-Hochberg over the FULL set of hypotheses this run tested —
    # `tested`, not `len(best)`. Correcting only against the survivors would
    # understate the denominator by an order of magnitude.
    survivors = _survives_fdr(list(best.values()), m_total=tested)

    ranked = sorted(survivors, key=lambda e: abs(e["strength"]), reverse=True)
    return ranked[:top_k]
