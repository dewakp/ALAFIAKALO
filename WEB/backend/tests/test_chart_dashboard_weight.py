"""Tests for the composite weight series (all-sources retrieval + statistics).

The series builder is pure and fully testable offline; endpoint routes are
asserted to exist and be auth-gated (authenticated flows run in CI/Docker).
"""

from datetime import date

import pytest
from httpx import AsyncClient

from app.api.chart_dashboard import build_weight_series, VIRTUAL_DATASETS, WEIGHT_SOURCES


def _obs(*items):
    """items: (iso_date, value, source)"""
    return [(date.fromisoformat(d), v, s) for d, v, s in items]


def test_empty_observations():
    out = build_weight_series([])
    assert out["points"] == []
    assert out["summary"]["count"] == 0
    assert out["summary"]["avg"] is None


def test_daily_mean_min_max_count_and_sources():
    out = build_weight_series(_obs(
        ("2026-06-01", 50.0, "vitals"),
        ("2026-06-01", 52.0, "meals"),
        ("2026-06-01", 54.0, "therapy"),
        ("2026-06-02", 51.0, "vitals"),
    ))
    p1, p2 = out["points"]
    assert p1["date"] == "2026-06-01"
    assert p1["value"] == 52.0          # mean(50, 52, 54)
    assert p1["min"] == 50.0 and p1["max"] == 54.0
    assert p1["count"] == 3
    assert p1["sources"] == {"vitals": 1, "meals": 1, "therapy": 1}
    assert p2["value"] == 51.0

    s = out["summary"]
    assert s["count"] == 4
    assert s["avg"] == round((50 + 52 + 54 + 51) / 4, 2)
    assert s["min"] == 50.0 and s["max"] == 54.0
    assert s["stddev"] is not None
    assert s["sources"] == {"vitals": 2, "meals": 1, "therapy": 1}


def test_rolling_7day_average_uses_trailing_window():
    # Daily means: day1=50, day3=52, day9=60
    out = build_weight_series(_obs(
        ("2026-06-01", 50.0, "vitals"),
        ("2026-06-03", 52.0, "vitals"),
        ("2026-06-09", 60.0, "vitals"),
    ))
    by_date = {p["date"]: p for p in out["points"]}
    assert by_date["2026-06-01"]["rolling_7d"] == 50.0
    assert by_date["2026-06-03"]["rolling_7d"] == 51.0   # mean(50, 52) within 7d
    # Jun 9 window is Jun 3–9: mean(52, 60) — Jun 1 has aged out.
    assert by_date["2026-06-09"]["rolling_7d"] == 56.0


def test_weekly_aggregation_buckets_by_monday():
    out = build_weight_series(_obs(
        ("2026-06-01", 50.0, "vitals"),   # Monday
        ("2026-06-03", 52.0, "vitals"),   # same ISO week
        ("2026-06-08", 60.0, "vitals"),   # next Monday
    ), aggregation="weekly")
    assert [p["date"] for p in out["points"]] == ["2026-06-01", "2026-06-08"]
    assert out["points"][0]["value"] == 51.0
    assert out["points"][0]["count"] == 2


def test_trend_detection():
    rising = build_weight_series(_obs(
        ("2026-06-01", 50.0, "vitals"),
        ("2026-06-02", 50.0, "vitals"),
        ("2026-06-10", 60.0, "vitals"),
        ("2026-06-11", 60.0, "vitals"),
    ))
    assert rising["summary"]["trend"] == "increasing"


def test_all_expected_sources_registered():
    """Every record type that stores dated body weight must be in the union."""
    names = {src for src, *_ in WEIGHT_SOURCES}
    assert names == {"vitals", "lifestyle", "fitness", "meals", "elimination", "therapy"}
    # labs are handled separately in _collect_weight_observations;
    # both composite datasets are exposed to the chart dashboard.
    assert set(VIRTUAL_DATASETS) == {"weight_all", "weight_all_7d"}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/chart-dashboard/weight-series",
    "/api/v1/chart-dashboard/data?datasets=weight_all,weight_all_7d",
    "/api/v1/chart-dashboard/summary?dataset=weight_all",
])
async def test_endpoints_require_auth(client: AsyncClient, path):
    r = await client.get(path)
    assert r.status_code == 401
