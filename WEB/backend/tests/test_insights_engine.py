"""Unit tests for the relationship + forecast engines (pure functions, offline)."""

from datetime import date, timedelta

from app.services.insights_engine import _pearson, _aligned, compute_relationships
from app.services.forecast_engine import forecast_signal, forecastable_signals


def test_pearson_perfect_positive():
    assert _pearson([1, 2, 3, 4], [2, 4, 6, 8]) == 1.0


def test_pearson_perfect_negative():
    assert _pearson([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0


def test_pearson_constant_returns_none():
    assert _pearson([1, 1, 1], [1, 2, 3]) is None


def test_aligned_applies_lag():
    base = date(2026, 1, 1)
    a = {base + timedelta(days=i): i for i in range(5)}
    b = {base + timedelta(days=i): i * 10 for i in range(5)}
    xs, ys = _aligned(a, b, lag_days=1)
    # a[d] pairs with b[d+1]: (0,10),(1,20),(2,30),(3,40)
    assert xs == [0, 1, 2, 3]
    assert ys == [10, 20, 30, 40]


def test_compute_relationships_finds_lagged_cross_domain_edge():
    base = date(2026, 1, 1)
    # sodium on day d predicts systolic BP on day d+1 (perfect lag-1 link).
    sodium = {base + timedelta(days=i): float(v)
              for i, v in enumerate([1, 5, 2, 8, 3, 9, 4, 7, 6, 5])}
    bp = {}
    for i, v in enumerate([1, 5, 2, 8, 3, 9, 4, 7, 6, 5]):
        bp[base + timedelta(days=i + 1)] = float(v) * 2 + 100  # shifted +1 day
    signals = {"diet.sodium_mg": sodium, "vital.bp_systolic": bp}

    edges = compute_relationships(signals, max_lag=3, min_samples=5, min_strength=0.5)
    assert edges, "expected at least one relationship"
    top = edges[0]
    assert {top["source"], top["target"]} == {"diet.sodium_mg", "vital.bp_systolic"}
    assert top["lag_days"] == 1
    assert top["strength"] > 0.9
    assert "caveat" in top


def test_compute_relationships_skips_same_domain_when_cross_only():
    # 14 days, not 8: `MIN_SAMPLES_FLOOR` is 10 because a correlation over
    # fewer points cannot be assessed at all. This test is about DOMAIN
    # filtering, so it needs a fixture large enough to reach that check —
    # otherwise it passes for the wrong reason (empty because too short).
    base = date(2026, 1, 1)
    a = {base + timedelta(days=i): float(i) for i in range(14)}
    b = {base + timedelta(days=i): float(i) * 3 for i in range(14)}
    # both in the "diet" domain → skipped when cross_domain_only
    signals = {"diet.sodium_mg": a, "diet.potassium_mg": b}
    assert compute_relationships(signals, cross_domain_only=True) == []
    assert compute_relationships(signals, cross_domain_only=False)  # found when allowed


def test_forecast_signal_linear_trend():
    base = date(2026, 1, 1)
    series = {base + timedelta(days=i): float(70 + i) for i in range(10)}  # +1/day
    result = forecast_signal(series, horizon=5)
    assert result is not None
    assert result["trend"] == "rising"
    assert len(result["forecast"]) == 5
    # next day after day 9 (value 79) ≈ 80
    assert abs(result["forecast"][0]["value"] - 80) < 0.5
    assert result["forecast"][0]["lower"] <= result["forecast"][0]["value"] <= result["forecast"][0]["upper"]


def test_forecast_insufficient_data():
    base = date(2026, 1, 1)
    series = {base: 1.0, base + timedelta(days=1): 2.0}
    assert forecast_signal(series, min_points=4) is None


def test_forecastable_signals_orders_by_count():
    base = date(2026, 1, 1)
    small = {base + timedelta(days=i): 1.0 for i in range(4)}
    big = {base + timedelta(days=i): 1.0 for i in range(20)}
    order = forecastable_signals({"a": small, "b": big})
    assert order == ["b", "a"]
