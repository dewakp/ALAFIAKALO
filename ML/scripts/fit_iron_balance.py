#!/usr/bin/env python3
"""Fit what IV iron actually does to THIS patient's iron stores.

The effects store currently holds an iron magnitude a language model supplied.
That number could have been *fitted*: the corpus carries 150 ferritin values,
126 saturations and 943 sessions with a recorded iron dose across ten years.
Asking a model to state a quantity that a decade of measurements can estimate is
the wrong instrument, and this script is the right one.

    ML/.venv-health-ml/bin/python ML/scripts/fit_iron_balance.py --report
    ML/.venv-health-ml/bin/python ML/scripts/fit_iron_balance.py --out iron.json

## The model

Between two consecutive draws the marker moves by what was given and what was
lost:

    next - prev  =  beta * (iron administered between the draws)  -  rate * days

Two unknowns, ordinary least squares, exactly the shape `fit_interdialytic`
already uses for potassium. `beta` is the marker's response per milligram of IV
iron; `rate` is ongoing loss per day, which on haemodialysis is real and large —
circuit residue, blood draws, GI losses — and is what makes IV iron routine
rather than exceptional.

The sign is the opposite of every fit in `fit_dialysis_coefficients.py`: those
model a treatment REMOVING solute, this models a drug ADDING iron.

## Why two targets, and why saturation is the honest one

Ferritin is an acute-phase reactant. Inflammation raises it independently of
iron stores, so a ferritin fit can be confounded by anything inflammatory and a
good hold-out score does not by itself mean the iron model is right. Transferrin
saturation tracks iron actually AVAILABLE for erythropoiesis. Both are fitted
and both are reported; disagreement between them is a finding, not noise.

## The honest part, unchanged from the sibling script

Scored on a CHRONOLOGICAL hold-out — fit the early years, test the later ones.
A random split leaks the future backwards through a time series. The comparison
is against predict-the-previous-value, which for a slow-moving marker is a
strong baseline and is what a clinician assumes by default. A fit that cannot
beat it is reported with `beats_baseline=False` and must not be adopted.

Beating it is judged on the PAIRED per-point errors, not on which mean is
lower: a fit must be ahead by at least 1.96 standard errors. On the first run
haemoglobin came in at 0.588 against 0.592 over 24 points — a 0.6% difference
that a bare `mae < baseline` reports as a win.

## What this script found, and why it is a negative result worth keeping

Saturation, ferritin and iron all LOSE to the baseline, and the fitted
coefficients come back physiologically inverted — iron administration
apparently lowering ferritin. That is the signature of confounding by
indication: IV iron is given precisely when iron is low and withheld when
ferritin is high, so a naive regression on observational treatment data
recovers the sign backwards. ESA is not in the model though it consumes iron,
ferritin is an acute-phase reactant, and the recorded dose barely varies
(median 100 mg), so the coefficient is weakly identified in any case.

The conclusion is not that the effect is absent. It is that THIS specification
cannot measure it, and a number taken from it would be worse than the
literature prior it replaced.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import pathlib
import re
import statistics
import sys
from dataclasses import asdict, dataclass

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_LABS = REPO / "ML" / "data" / "processed" / "unified_labs.csv"
DEFAULT_SESSIONS = REPO / "ML" / "data" / "processed" / "dialysis_sessions.csv"

#: Markers to fit. Saturation first: it is the one that reflects available iron.
TARGETS = ("Iron Saturation", "Ferritin", "Iron", "Hemoglobin")

#: Names the IV iron is written under. Read from the corpus, not assumed:
#: the session export writes `venofer=100 mg`, the flowsheet writes
#: `Venofer (100 mg)`, and a FHIR import would say `Iron sucrose`.
IRON_DRUG_TOKENS = ("venofer", "iron sucrose", "iron_sucrose", "ferric", "feraheme")

#: Units we will do arithmetic with. A dose written in mL states a volume of a
#: preparation whose concentration is not recorded here, so it cannot be turned
#: into milligrams of iron without inventing the strength.
_MASS_UNITS = {"mg": 1.0, "mcg": 0.001, "g": 1000.0}

_DOSE_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*([a-zA-Z]+)")

#: Interval bounds, derived from the corpus rather than copied from the
#: potassium fit. Iron panels are drawn on a monthly-ish cadence: the observed
#: gaps run median 15 days, p90 45. `MAX_GAP_DAYS = 10` is correct for
#: potassium and would discard nearly every iron interval here.
MIN_GAP_DAYS = 7
MAX_GAP_DAYS = 90

#: Fraction of the timeline used for fitting; the remainder is held out.
HOLDOUT_SPLIT = 0.7

#: Below this an interval count cannot support a two-parameter fit with a
#: hold-out worth reading.
MIN_INTERVALS = 20


@dataclass
class IronFitResult:
    marker: str
    n_fit: int
    n_holdout: int
    #: Marker units gained per mg of elemental iron administered.
    beta_per_mg: float | None
    #: Marker units lost per day, ongoing.
    loss_per_day: float | None
    holdout_mae: float | None
    baseline_mae: float | None
    holdout_bias: float | None
    #: Standard error of the PAIRED per-point error difference, and that
    #: difference expressed in standard errors. `improvement_z` is the field
    #: that decides adoption, not the raw MAE comparison.
    holdout_se: float | None
    improvement_z: float | None
    beats_baseline: bool
    total_iron_mg: float | None = None
    note: str = ""

    @property
    def improvement_pct(self) -> float | None:
        if not self.baseline_mae or self.holdout_mae is None:
            return None
        return 100.0 * (self.baseline_mae - self.holdout_mae) / self.baseline_mae


def parse_iron_mg(text: str | None) -> float | None:
    """Milligrams of IV iron in one session's medication text, or None.

    None means "this session does not record an iron dose we can use", which is
    NOT zero. A session that gave iron in millilitres of an unstated
    preparation, or named the drug with no amount, must not enter the fit as a
    zero — that would teach the model that iron was given and did nothing.
    """
    if not text:
        return None
    lowered = text.lower()
    if not any(token in lowered for token in IRON_DRUG_TOKENS):
        return None

    # Isolate the iron drug's own clause. Sessions list several drugs separated
    # by ";", and matching the first number in the whole string would pick up
    # the sodium citrate volume or the epoetin units.
    for clause in re.split(r"[;,]", lowered):
        if not any(token in clause for token in IRON_DRUG_TOKENS):
            continue
        match = _DOSE_RE.search(clause)
        if not match:
            return None          # named, amount not recorded
        amount = float(match.group(1).replace(",", ""))
        unit = match.group(2).strip().lower()
        factor = _MASS_UNITS.get(unit)
        if factor is None:
            return None          # mL, SQ, or anything we cannot convert
        return amount * factor if amount > 0 else None
    return None


def load_sessions(path: pathlib.Path) -> list[tuple[datetime.date, float | None]]:
    if not path.exists():
        sys.exit(f"No session corpus at {path}")
    out: list[tuple[datetime.date, float | None]] = []
    with path.open() as fh:
        for row in csv.DictReader(fh):
            raw = (row.get("session_date") or "")[:10]
            if len(raw) != 10:
                continue
            try:
                day = datetime.date.fromisoformat(raw)
            except ValueError:
                continue
            out.append((day, parse_iron_mg(row.get("medications"))))
    out.sort(key=lambda p: p[0])
    return out


def load_series(path: pathlib.Path, marker: str) -> list[tuple[datetime.date, float]]:
    if not path.exists():
        sys.exit(f"No lab corpus at {path}")
    series: list[tuple[datetime.date, float]] = []
    with path.open() as fh:
        for row in csv.DictReader(fh):
            if (row.get("test_name") or "").strip() != marker:
                continue
            raw = (row.get("date") or "")[:10]
            value = (row.get("value_numeric") or "").strip()
            if len(raw) != 10 or not value:
                continue
            try:
                series.append((datetime.date.fromisoformat(raw), float(value)))
            except ValueError:
                continue
    series.sort(key=lambda p: p[0])
    return series


def build_intervals(series, sessions) -> list[dict]:
    """One row per consecutive pair of draws, with the iron given between them."""
    rows: list[dict] = []
    for (start_day, prev), (end_day, nxt) in zip(series, series[1:]):
        gap = (end_day - start_day).days
        if not (MIN_GAP_DAYS <= gap <= MAX_GAP_DAYS):
            continue
        # Strictly after the first draw, up to and including the second: a dose
        # given on the morning of the first draw cannot explain that draw.
        doses = [mg for day, mg in sessions if start_day < day <= end_day]
        if not doses:
            continue
        # A session whose dose could not be read is excluded from the total but
        # recorded, because an interval containing unreadable doses understates
        # the exposure and the fit should be able to say how often that happens.
        usable = [mg for mg in doses if mg is not None]
        rows.append({
            "date": end_day, "prev": prev, "next": nxt, "days": gap,
            "iron_mg": float(sum(usable)),
            "sessions": len(doses), "unreadable": len(doses) - len(usable),
        })
    return rows


def fit_marker(marker: str, series, sessions) -> IronFitResult:
    if len(series) < MIN_INTERVALS:
        return IronFitResult(marker, len(series), 0, None, None, None, None, None,
                             False, note=f"only {len(series)} draws")

    rows = build_intervals(series, sessions)
    rows = [r for r in rows if r["iron_mg"] > 0]
    if len(rows) < MIN_INTERVALS:
        return IronFitResult(marker, len(rows), 0, None, None, None, None, None,
                             False, note=f"only {len(rows)} usable intervals")

    cut = int(len(rows) * HOLDOUT_SPLIT)
    train, test = rows[:cut], rows[cut:]
    if not test:
        return IronFitResult(marker, len(train), 0, None, None, None, None, None,
                             False, note="no hold-out after the split")

    # next - prev = beta*iron - rate*days
    design = np.column_stack([
        np.array([r["iron_mg"] for r in train], dtype=float),
        -np.array([r["days"] for r in train], dtype=float),
    ])
    target = np.array([r["next"] - r["prev"] for r in train], dtype=float)
    solution, *_ = np.linalg.lstsq(design, target, rcond=None)
    beta, rate = float(solution[0]), float(solution[1])

    predicted = np.array([
        r["prev"] + beta * r["iron_mg"] - rate * r["days"] for r in test
    ], dtype=float)
    actual = np.array([r["next"] for r in test], dtype=float)
    previous = np.array([r["prev"] for r in test], dtype=float)

    model_error = np.abs(predicted - actual)
    # Predict-the-previous-value: what a clinician assumes by default.
    baseline_error = np.abs(previous - actual)
    mae = float(np.mean(model_error))
    baseline = float(np.mean(baseline_error))
    bias = float(np.mean(predicted - actual))

    # `mae < baseline` alone adopts a coin flip. The two error sets are PAIRED
    # — the same hold-out points predicted two ways — so the question is
    # whether the per-point difference is distinguishable from zero, not
    # whether one mean happened to land lower. Without this, haemoglobin fitted
    # 0.588 against 0.592 on 24 points and was reported ADOPT on 0.6%, which is
    # noise. The sibling `fit_dialysis_coefficients.py` uses the bare
    # comparison and has the same weakness.
    difference = baseline_error - model_error        # positive ⇒ the fit helps
    standard_error = (
        float(np.std(difference, ddof=1) / np.sqrt(len(difference)))
        if len(difference) > 1 else 0.0
    )
    z = float(np.mean(difference) / standard_error) if standard_error > 0 else 0.0

    return IronFitResult(
        marker=marker, n_fit=len(train), n_holdout=len(test),
        beta_per_mg=beta, loss_per_day=rate,
        holdout_mae=mae, baseline_mae=baseline, holdout_bias=bias,
        holdout_se=standard_error, improvement_z=z,
        beats_baseline=bool(mae < baseline and z >= 1.96),
        total_iron_mg=float(sum(r["iron_mg"] for r in rows)),
        note=f"{sum(r['unreadable'] for r in rows)} session(s) with an unreadable dose",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labs", type=pathlib.Path, default=DEFAULT_LABS)
    parser.add_argument("--sessions", type=pathlib.Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--out", type=pathlib.Path, default=None)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    sessions = load_sessions(args.sessions)
    dosed = [mg for _, mg in sessions if mg]
    print(f"sessions: {len(sessions)}  with a readable iron dose: {len(dosed)}")
    if dosed:
        print(f"  dose mg: min={min(dosed):g} median={statistics.median(dosed):g} "
              f"max={max(dosed):g}  total={sum(dosed):g}")

    results: list[IronFitResult] = []
    for marker in TARGETS:
        series = load_series(args.labs, marker)
        result = fit_marker(marker, series, sessions)
        results.append(result)
        if args.report or not args.out:
            improvement = result.improvement_pct
            verdict = "ADOPT" if result.beats_baseline else "reject"
            print()
            print(f"{marker}: n={len(series)} draws  fit={result.n_fit} "
                  f"holdout={result.n_holdout}  [{verdict}]")
            if result.beta_per_mg is not None:
                print(f"  per mg of IV iron : {result.beta_per_mg:+.5f}")
                print(f"  loss per day      : {result.loss_per_day:+.5f}")
            if result.holdout_mae is not None:
                print(f"  hold-out MAE      : {result.holdout_mae:.3f} "
                      f"vs baseline {result.baseline_mae:.3f}"
                      + (f"  ({improvement:+.1f}%)" if improvement is not None else ""))
                print(f"  paired z          : {result.improvement_z:+.2f} "
                      f"(needs >= +1.96 to adopt)")
                print(f"  bias              : {result.holdout_bias:+.3f}")
            if result.note:
                print(f"  note              : {result.note}")

    if args.out:
        args.out.write_text(json.dumps(
            {"results": [asdict(r) for r in results]}, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
