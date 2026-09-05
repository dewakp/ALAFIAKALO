"""Health Insights must not present noise as a finding.

The first version kept any |r| >= 0.35 over as few as FIVE daily points, with no
p-value and no correction for multiple comparisons. One page load tests roughly
460 hypotheses (12 signals x lags 0-3) and the 5% critical |r| at n=5 is 0.878,
so the screen filled with rows like "Sugar leads by 3d -> Mood, +0.85, n=5".

The tell was in the output: Mood appeared in eight of twelve rows, correlating
with potassium, carbs, sodium, sugar, calories and phosphorus at once, and in
both directions. That is the signature of five data points, not physiology.

A patient asked "what food contributed most to sugar today" and was shown that
page. These tests pin the two properties that make the surface honest: it finds
a real effect, and it finds nothing in noise.
"""

import random
from datetime import date, timedelta

from app.services.insights_engine import (
    FDR_Q,
    MIN_SAMPLES_FLOOR,
    _p_value,
    _pearson,
    _survives_fdr,
    compute_relationships,
)

START = date(2026, 8, 1)


def _noise(n: int, seed: int) -> dict:
    rnd = random.Random(seed)
    return {START + timedelta(days=i): rnd.gauss(0, 1) for i in range(n)}


def _noise_signals(n: int = 21, seed: int = 3) -> dict:
    keys = ["diet.calories", "diet.protein_g", "diet.carbs_g", "diet.sugar_g",
            "diet.sodium_mg", "vital.bp_systolic", "vital.bp_diastolic",
            "vital.weight_kg", "mood.score", "sleep.hours", "activity.steps",
            "symptom.severity_max"]
    return {k: _noise(n, seed + i) for i, k in enumerate(keys)}


# ── the statistics themselves ──────────────────────────────────────────


def test_p_value_of_a_perfect_correlation_is_zero():
    xs = list(range(20))
    ys = [x * 2.0 for x in xs]
    assert _p_value(_pearson(xs, ys), len(xs)) == 0.0


def test_p_value_of_noise_is_large():
    rnd = random.Random(1)
    xs = list(range(20))
    ys = [rnd.gauss(0, 1) for _ in xs]
    assert _p_value(_pearson(xs, ys), len(xs)) > 0.05


def test_the_five_point_correlation_that_shipped_is_not_significant():
    """r = 0.85 at n = 5 was displayed as a finding. The 5% critical value at
    n = 5 is 0.878, so it never cleared even an uncorrected test."""
    assert _p_value(0.85, 5) > 0.05


# ── the floor ──────────────────────────────────────────────────────────


def test_five_days_can_never_produce_a_relationship():
    """No threshold on |r| repairs a five-point sample."""
    assert MIN_SAMPLES_FLOOR >= 10
    assert compute_relationships(_noise_signals(n=5)) == []


def test_the_floor_cannot_be_lowered_by_a_caller():
    assert compute_relationships(_noise_signals(n=6), min_samples=2) == []


# ── noise in, nothing out ──────────────────────────────────────────────


def test_pure_noise_yields_no_relationships():
    """Twelve unrelated signals over three weeks. Anything shown here is a
    false positive by construction."""
    assert compute_relationships(_noise_signals(n=21)) == []


def test_pure_noise_over_a_long_window_still_yields_nothing():
    assert compute_relationships(_noise_signals(n=40, seed=99)) == []


# ── but a real effect still surfaces ───────────────────────────────────


def test_a_genuine_lagged_effect_is_found():
    """A filter that rejects everything is not a fix."""
    rnd = random.Random(11)
    n = 21
    sodium = {START + timedelta(days=i): rnd.gauss(0, 1) for i in range(n)}
    sbp = {
        START + timedelta(days=i + 1): sodium[START + timedelta(days=i)] * 0.95
        + rnd.gauss(0, 0.25)
        for i in range(n - 1)
    }
    signals = {"diet.sodium_mg": sodium, "vital.bp_systolic": sbp}
    for i, k in enumerate(["mood.score", "diet.sugar_g", "sleep.hours"]):
        signals[k] = _noise(n, 500 + i)

    out = compute_relationships(signals)
    assert out, "a strong lag-1 effect must survive the correction"
    top = out[0]
    assert {top["source"], top["target"]} == {"diet.sodium_mg", "vital.bp_systolic"}
    assert top["p_value"] < 0.01
    assert top["sample_size"] >= MIN_SAMPLES_FLOOR


# ── the correction counts every hypothesis ─────────────────────────────


def test_fdr_uses_the_full_denominator_not_just_survivors():
    """Correcting against the rows that happened to clear |r| would hide the
    multiple-comparison problem rather than correct it."""
    edges = [{"p_value": 0.01}, {"p_value": 0.02}]
    assert len(_survives_fdr(edges, m_total=2, q=FDR_Q)) >= 1
    # the same p-values, but 460 hypotheses were actually tested
    assert _survives_fdr(edges, m_total=460, q=FDR_Q) == []


# ── the UI must not claim causation ────────────────────────────────────


def test_direction_is_never_stated_as_causal():
    """The banner says "associations, not cause-and-effect" and the row then
    read "Sugar -> leads by 3d -> Mood". A lag is an offset we tested."""
    rnd = random.Random(5)
    n = 25
    a = {START + timedelta(days=i): rnd.gauss(0, 1) for i in range(n)}
    b = {START + timedelta(days=i + 2): a[START + timedelta(days=i)] * 0.9
         + rnd.gauss(0, 0.2) for i in range(n - 2)}
    out = compute_relationships({"diet.sugar_g": a, "mood.score": b})
    for e in out:
        assert e["direction"] in {"same-day", "offset"}
        assert "lead" not in e["direction"]
