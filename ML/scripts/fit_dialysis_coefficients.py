#!/usr/bin/env python3
"""Fit per-patient dialysis solute-transfer coefficients against measured serum.

The model in `app/services/dialysis_balance.py` ships literature priors. This
fits them to one patient's own blood work and — the part that matters — reports
whether the fitted version actually predicts better than doing nothing.

    ML/.venv-health-ml/bin/python ML/scripts/fit_dialysis_coefficients.py --report

## Two fits, because the data supports two different things

**Direct** (BUN, calcium, phosphorus): a same-day pre and post value bracket a
session, so the coefficient is whatever makes the predicted post match the
measured one.

**Interdialytic** (potassium, magnesium): *no post-dialysis value exists for
these anywhere in the corpus* — not in the flowsheets, not in the DaVita PDFs.
So they are fitted across consecutive pre-dialysis draws instead: removal by the
sessions in between, plus a net accumulation rate per day. That rate absorbs
diet, which cannot be used directly here because `nutrition_logs` only starts in
2025-05 while the labs go back to 2016.

## The honest part

Every fit is scored on a **chronological** hold-out — fit on the early years,
test on the later ones. A random split would leak future information backwards
through a time series and flatter the model.

The comparison is against *predict-the-previous-value*, which is a strong
baseline for a slow-moving biomarker and is exactly what a clinician does by
default. A coefficient that cannot beat it is not adopted, and the analyte keeps
its prior and is marked uncalibrated.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_LABS = REPO / "ML" / "data" / "processed" / "unified_labs.csv"
DEFAULT_POST = REPO / "ML" / "data" / "features" / "post_dialysis_labs.csv"
DEFAULT_SESSIONS = REPO / "ML" / "data" / "processed" / "therapy_sessions.csv"

SESSION_EXPORT_HINT = """
Sessions are not in the ML tree. Export them first.

NOTE `therapy_sessions.blood_flow_rate` is the PRESCRIBED rate — a flat 350 on
every row, carrying no information. The delivered rate is the per-session mean
of `intradialytic_readings.blood_flow_rate`, which really does vary (median 397,
SD 61, range ~150-480). Raw readings span 0-4660, so band them first.

  cd WEB && docker compose exec -T db psql -U alafia -d alafia -tAF',' -c \\
    "SELECT s.scheduled_date::date, s.duration_minutes,
            coalesce(r.avg_qb, s.blood_flow_rate),
            s.dialysate_volume_liters, s.dialysate_potassium_meq, s.fluid_removed_ml,
            s.pre_dialysis_weight_kg, s.post_dialysis_weight_kg, s.status,
            r.avg_qb, r.n_readings
     FROM therapy_sessions s
     LEFT JOIN (SELECT session_id, avg(blood_flow_rate) AS avg_qb, count(*) AS n_readings
                FROM intradialytic_readings
                WHERE blood_flow_rate BETWEEN 50 AND 600
                GROUP BY session_id) r ON r.session_id = s.id
     ORDER BY s.scheduled_date;" \\
    > ../ML/data/processed/therapy_sessions.csv
"""

SESSION_COLUMNS = [
    "date", "duration_minutes", "blood_flow", "dialysate_l",
    "bath_k_meq", "uf_ml", "pre_weight_kg", "post_weight_kg", "status",
    # Measured blood flow, averaged over the session's own readings, and how
    # many readings it came from. `blood_flow` above prefers this and falls
    # back to the session record.
    "measured_qb", "n_readings",
]

#: Lab names differ between sources ("Phosphorous", "Magnessium", …).
ANALYTE_ALIASES = {
    "potassium": ["Potassium", "K+"],
    "phosphorus": ["Phosphorus", "Phosphorous"],
    "calcium": ["Calcium"],
    "magnesium": ["Magnesium", "Magnessium"],
    "bun": ["BUN"],
}
POST_ALIASES = {
    "phosphorus": ["Phosphorus", "Phosphorous"],
    "calcium": ["Calcium"],
    "bun": ["BUN"],
}

#: Analytes whose post-dialysis value is already identified in post_dialysis_labs.csv.
DIRECT_ANALYTES = ["bun", "calcium", "phosphorus"]

#: Analytes with no *explicitly named* post value, whose post draw is instead
#: identified by where and when it was taken. See `derive_post_by_facility`.
DERIVED_ANALYTES = ["potassium", "magnesium"]

INTERDIALYTIC_ANALYTES = ["potassium", "magnesium"]

#: Plausibility guards, mirroring dialysis_balance.
BATH_K_RANGE = (0.0, 4.0)
DIALYSATE_RANGE = (5.0, 120.0)

#: Ignore an interdialytic gap longer than this — a month between draws says
#: nothing about a per-day accumulation rate.
MAX_GAP_DAYS = 10

#: Analytes the patient GAINS from the bath. A "post must be lower than pre"
#: sanity filter is correct for solutes being removed and exactly wrong here —
#: applied to calcium it discards the very pairs that demonstrate the gain, and
#: leaves too few to fit.
GAINED_FROM_BATH = {"calcium"}

#: Session columns the fit needs. `duration_minutes` and `blood_flow` are not
#: optional: without them `base_removal_mg` cannot derive dialysate flow or
#: blood volume processed, silently falls back to unit efficiency, and the
#: model reduces to volume-only — which is exactly the bug this list fixes.
_SESSION_FIT_COLUMNS = [
    "date", "dialysate_l", "bath_k_meq", "uf_ml", "duration_minutes", "blood_flow",
]

#: Fraction of the timeline used for fitting; the remainder is held out.
HOLDOUT_SPLIT = 0.7


@dataclass
class FitResult:
    analyte: str
    method: str
    n_fit: int
    n_holdout: int
    alpha: float | None          # serum-units change per mg removed
    accumulation_per_day: float | None
    implied_volume_l: float | None
    holdout_mae: float | None
    baseline_mae: float | None
    holdout_bias: float | None
    beats_baseline: bool
    note: str = ""

    @property
    def improvement_pct(self) -> float | None:
        if not self.baseline_mae or self.holdout_mae is None:
            return None
        return 100.0 * (self.baseline_mae - self.holdout_mae) / self.baseline_mae


# ── Loading ──────────────────────────────────────────────────────────────────

def load_sessions(path: pathlib.Path) -> pd.DataFrame:
    if not path.exists():
        sys.exit(f"No session export at {path}\n{SESSION_EXPORT_HINT}")
    df = pd.read_csv(path, names=SESSION_COLUMNS, header=None)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    before = len(df)
    # Same guards the runtime model applies — a session excluded there must not
    # be allowed to shape the coefficients here.
    df = df[df["dialysate_l"].between(*DIALYSATE_RANGE, inclusive="both")]
    bath_ok = df["bath_k_meq"].isna() | df["bath_k_meq"].between(*BATH_K_RANGE, inclusive="both")
    df = df[bath_ok]
    excluded = before - len(df)
    if excluded:
        print(f"  excluded {excluded} session(s) with implausible volume or bath")
    return df.sort_values("date").reset_index(drop=True)


def load_labs(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["value_numeric"] = pd.to_numeric(df["value_numeric"], errors="coerce")
    return df.dropna(subset=["value_numeric"])


def load_post(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date", "value"])


def derive_post_by_facility(
    labs: pd.DataFrame, sessions: pd.DataFrame, analyte: str
) -> pd.DataFrame:
    """Identify post-dialysis draws for analytes that are never labelled as such.

    Potassium and magnesium have no "POST" test name anywhere in the corpus, so
    a name-based search concludes — wrongly — that no post value exists. What
    identifies them is *where and when the blood was taken*:

      - the monthly pre-dialysis panel is drawn by the dialysis provider
        (lab_name = DaVita Labs) before treatment;
      - the outside lab (Kaiser, arriving via the records spreadsheet) drawn on
        a treatment day is taken afterwards.

    This is the same signal `_build_post_labs_v2.py` calls rule 4; that script
    simply never listed potassium or magnesium among the analytes to extract.

    Only **same-day** draws are used. A next-morning potassium has already
    re-equilibrated from the intracellular pool and says little about what the
    session removed, so including it would bias the coefficient downward.
    """
    names = ANALYTE_ALIASES[analyte]
    values = labs[labs["test_name"].isin(names) & labs["value_numeric"].notna()].copy()
    if values.empty:
        return pd.DataFrame(columns=["date", "pre", "post"])

    outside_lab = (
        (values["source"] == "records_xlsx")
        | values["lab_name"].astype(str).str.contains("Kaiser", case=False, na=False)
    )
    provider_lab = values["lab_name"].astype(str).str.contains("DaVita", case=False, na=False)

    session_dates = set(sessions["date"])
    on_treatment_day = values["date"].isin(session_dates)

    post = (
        values[outside_lab & on_treatment_day]
        .groupby("date", as_index=False)["value_numeric"].min()
        .rename(columns={"value_numeric": "post"})
    )
    pre = (
        values[provider_lab]
        .groupby("date", as_index=False)["value_numeric"].max()
        .rename(columns={"value_numeric": "pre"})
    )

    # A same-day provider draw gives a true pre/post pair. Where there is no
    # provider value, fall back to the most recent earlier draw as the pre —
    # weaker, but it is what a clinician reads too.
    paired = post.merge(pre, on="date", how="left")
    plain = series_for(labs, analyte).rename(columns={"value": "prior"})
    paired = pd.merge_asof(
        paired.sort_values("date"),
        plain.sort_values("date"),
        on="date", direction="backward", allow_exact_matches=False,
    )
    paired["pre"] = paired["pre"].fillna(paired["prior"])
    return paired.dropna(subset=["pre", "post"])[["date", "pre", "post"]]


def series_for(labs: pd.DataFrame, analyte: str) -> pd.DataFrame:
    """Pre-dialysis (i.e. plain) values for one analyte, one row per date."""
    names = ANALYTE_ALIASES[analyte]
    exact = labs[labs["test_name"].isin(names)]
    # Anything explicitly marked POST is a different measurement.
    exact = exact[~exact["test_name"].str.upper().str.contains("POST", na=False)]
    return (
        exact.groupby("date", as_index=False)["value_numeric"].median()
        .rename(columns={"value_numeric": "value"})
        .sort_values("date").reset_index(drop=True)
    )


# ── Removal, with saturation=1 so the fit can scale it ───────────────────────

def base_removal_mg(session: pd.Series, serum_value: float, analyte: str) -> float:
    """Removal at unit saturation. The fitted alpha absorbs saturation and 1/V.

    Fitting saturation and volume separately would be ill-posed — only their
    ratio is observable from a concentration change — so one scalar is fitted
    and the implied volume is reported afterwards.
    """
    sys.path.insert(0, str(REPO / "WEB" / "backend"))
    from app.services.dialysis_balance import (  # noqa: E402
        _DL_PER_L, _MG_PER_MEQ_CA, _MG_PER_MEQ_K, _MG_PER_MEQ_MG, _MG_PER_MMOL_K,
        DEFAULT_BATH_CALCIUM_MEQ, DEFAULT_BATH_MAGNESIUM_MEQ, DEFAULT_COEFFICIENTS,
    )

    volume_l = float(session["dialysate_l"])
    # `nan or 0.0` evaluates to nan — NaN is truthy — so a session with no
    # recorded ultrafiltration silently poisoned every downstream fit.
    uf_raw = session["uf_ml"]
    uf_l = (float(uf_raw) / 1000.0) if pd.notna(uf_raw) else 0.0

    if analyte == "potassium":
        coeff = DEFAULT_COEFFICIENTS["potassium"]
        serum_mg_l = serum_value * _MG_PER_MMOL_K
        bath_mg_l = float(session["bath_k_meq"] or 0.0) * _MG_PER_MEQ_K
    elif analyte == "calcium":
        coeff = DEFAULT_COEFFICIENTS["calcium"]
        serum_mg_l = serum_value * _DL_PER_L
        bath_mg_l = DEFAULT_BATH_CALCIUM_MEQ * _MG_PER_MEQ_CA
    elif analyte == "magnesium":
        coeff = DEFAULT_COEFFICIENTS["magnesium"]
        serum_mg_l = serum_value * _DL_PER_L
        bath_mg_l = DEFAULT_BATH_MAGNESIUM_MEQ * _MG_PER_MEQ_MG
    else:  # phosphorus, bun — no bath term
        key = "urea" if analyte == "bun" else analyte
        coeff = DEFAULT_COEFFICIENTS.get(key) or DEFAULT_COEFFICIENTS["phosphorus"]
        serum_mg_l = serum_value * _DL_PER_L
        bath_mg_l = 0.0

    # Blood volume processed and the Qb:Qd ratio. Two sessions can run the same
    # dialysate volume and clear different amounts if the access ran poorly, so
    # the fit must see those parameters or it will attribute the difference to
    # noise.
    from app.services.dialysis_balance import (  # noqa: E402
        _MAX_SINGLE_PASS_EXTRACTION, _flow_efficiency,
    )

    duration = session.get("duration_minutes")
    blood_flow = session.get("blood_flow")
    qd = (volume_l * 1000.0 / duration) if pd.notna(duration) and duration else None
    qb = float(blood_flow) if pd.notna(blood_flow) else None
    efficiency = _flow_efficiency(qb, qd)
    blood_l = (qb * duration / 1000.0) if qb and pd.notna(duration) and duration else None

    diffusible = serum_mg_l * coeff.diffusible_fraction
    applied_efficiency = 1.0 - coeff.flow_sensitivity * (1.0 - efficiency)
    diffusive = volume_l * (diffusible - bath_mg_l) * applied_efficiency
    if blood_l:
        diffusive = min(diffusive, blood_l * diffusible * _MAX_SINGLE_PASS_EXTRACTION)
    convective = uf_l * diffusible
    return diffusive + convective


# ── Fits ─────────────────────────────────────────────────────────────────────

def _fit_scale(x: np.ndarray, y: np.ndarray) -> float:
    """Least-squares scale with no intercept: y ≈ alpha·x."""
    denom = float(np.dot(x, x))
    return float(np.dot(x, y) / denom) if denom > 0 else 0.0


def fit_direct(analyte: str, labs, post, sessions) -> FitResult | None:
    """Fit against measured post-dialysis values."""
    pre = series_for(labs, analyte)
    names = POST_ALIASES.get(analyte, [])
    posts = post[post["test"].isin(names)][["date", "value"]].rename(columns={"value": "post"})
    if posts.empty:
        return None

    merged = pre.merge(posts, on="date", how="inner")
    merged = merged.merge(sessions[_SESSION_FIT_COLUMNS],
                          on="date", how="inner").dropna(subset=["dialysate_l"])
    if analyte not in GAINED_FROM_BATH:
        merged = merged[merged["post"] < merged["value"]]  # a session should lower it
    if len(merged) < 12:
        return FitResult(analyte, "direct", len(merged), 0, None, None, None,
                         None, None, None, False,
                         note=f"only {len(merged)} usable pre/post pairs")

    merged = merged.sort_values("date").reset_index(drop=True)
    cut = int(len(merged) * HOLDOUT_SPLIT)
    train, test = merged.iloc[:cut], merged.iloc[cut:]

    removal = np.array([base_removal_mg(r, r["value"], analyte) for _, r in train.iterrows()])
    drop = (train["value"] - train["post"]).to_numpy()
    alpha = _fit_scale(removal, drop)

    test_removal = np.array([base_removal_mg(r, r["value"], analyte) for _, r in test.iterrows()])
    predicted = test["value"].to_numpy() - alpha * test_removal
    actual = test["post"].to_numpy()

    mae = float(np.mean(np.abs(predicted - actual)))
    bias = float(np.mean(predicted - actual))
    # Baseline: assume the session changed nothing.
    baseline = float(np.mean(np.abs(test["value"].to_numpy() - actual)))

    implied_v = 1.0 / (alpha * (39.10 if analyte == "potassium" else 10.0)) if alpha > 0 else None

    return FitResult(
        analyte=analyte, method="direct", n_fit=len(train), n_holdout=len(test),
        alpha=alpha, accumulation_per_day=None, implied_volume_l=implied_v,
        holdout_mae=mae, baseline_mae=baseline, holdout_bias=bias,
        beats_baseline=mae < baseline,
    )


def fit_from_pairs(analyte: str, pairs: pd.DataFrame, sessions, method: str) -> FitResult:
    """Fit a scale factor against pre/post pairs, scored on a chronological hold-out."""
    merged = pairs.merge(
        sessions[_SESSION_FIT_COLUMNS], on="date", how="inner"
    ).dropna(subset=["dialysate_l"])
    if analyte not in GAINED_FROM_BATH:
        merged = merged[merged["post"] < merged["pre"]]  # a session should lower it

    if len(merged) < 12:
        return FitResult(analyte, method, len(merged), 0, None, None, None,
                         None, None, None, False,
                         note=f"only {len(merged)} usable pre/post pairs")

    merged = merged.sort_values("date").reset_index(drop=True)
    cut = int(len(merged) * HOLDOUT_SPLIT)
    train, test = merged.iloc[:cut], merged.iloc[cut:]

    removal = np.array([base_removal_mg(r, r["pre"], analyte) for _, r in train.iterrows()])
    drop = (train["pre"] - train["post"]).to_numpy()
    alpha = _fit_scale(removal, drop)

    test_removal = np.array([base_removal_mg(r, r["pre"], analyte) for _, r in test.iterrows()])
    predicted = test["pre"].to_numpy() - alpha * test_removal
    actual = test["post"].to_numpy()

    mae = float(np.mean(np.abs(predicted - actual)))
    bias = float(np.mean(predicted - actual))
    baseline = float(np.mean(np.abs(test["pre"].to_numpy() - actual)))
    implied_v = 1.0 / (alpha * (39.10 if analyte == "potassium" else 10.0)) if alpha > 0 else None

    return FitResult(
        analyte=analyte, method=method, n_fit=len(train), n_holdout=len(test),
        alpha=alpha, accumulation_per_day=None, implied_volume_l=implied_v,
        holdout_mae=mae, baseline_mae=baseline, holdout_bias=bias,
        beats_baseline=mae < baseline,
    )


def fit_derived(analyte: str, labs, sessions) -> FitResult:
    """Fit potassium/magnesium against post draws identified by facility."""
    pairs = derive_post_by_facility(labs, sessions, analyte)
    return fit_from_pairs(analyte, pairs, sessions, "derived-post")


def fit_interdialytic(analyte: str, labs, sessions) -> FitResult | None:
    """Fit across consecutive pre-dialysis draws, with no post value available.

    Between two draws the serum moves by what the sessions removed and what the
    body put back. Both are fitted; the accumulation term stands in for diet,
    which is not recorded over most of this period.
    """
    pre = series_for(labs, analyte)
    if len(pre) < 20:
        return FitResult(analyte, "interdialytic", len(pre), 0, None, None, None,
                         None, None, None, False, note=f"only {len(pre)} draws")

    rows = []
    for i in range(len(pre) - 1):
        start, end = pre.iloc[i], pre.iloc[i + 1]
        gap_days = (end["date"] - start["date"]).days
        if not (1 <= gap_days <= MAX_GAP_DAYS):
            continue
        between = sessions[(sessions["date"] > start["date"]) & (sessions["date"] <= end["date"])]
        between = between.dropna(subset=["dialysate_l"])
        if between.empty:
            continue
        removal = sum(base_removal_mg(s, start["value"], analyte) for _, s in between.iterrows())
        rows.append({
            "date": end["date"], "prev": start["value"], "next": end["value"],
            "removal": removal, "days": gap_days,
        })

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame[np.isfinite(frame[["prev", "next", "removal", "days"]]).all(axis=1)]
    if len(frame) < 15:
        return FitResult(analyte, "interdialytic", len(frame), 0, None, None, None,
                         None, None, None, False,
                         note=f"only {len(frame)} usable intervals")

    frame = frame.sort_values("date").reset_index(drop=True)
    cut = int(len(frame) * HOLDOUT_SPLIT)
    train, test = frame.iloc[:cut], frame.iloc[cut:]

    # next − prev = −alpha·removal + rate·days   → two-column least squares
    design = np.column_stack([-train["removal"].to_numpy(), train["days"].to_numpy()])
    target = (train["next"] - train["prev"]).to_numpy()
    solution, *_ = np.linalg.lstsq(design, target, rcond=None)
    alpha, rate = float(solution[0]), float(solution[1])

    predicted = (
        test["prev"].to_numpy()
        - alpha * test["removal"].to_numpy()
        + rate * test["days"].to_numpy()
    )
    actual = test["next"].to_numpy()
    mae = float(np.mean(np.abs(predicted - actual)))
    bias = float(np.mean(predicted - actual))
    baseline = float(np.mean(np.abs(test["prev"].to_numpy() - actual)))

    implied_v = 1.0 / (alpha * (39.10 if analyte == "potassium" else 10.0)) if alpha > 0 else None

    return FitResult(
        analyte=analyte, method="interdialytic", n_fit=len(train), n_holdout=len(test),
        alpha=alpha, accumulation_per_day=rate, implied_volume_l=implied_v,
        holdout_mae=mae, baseline_mae=baseline, holdout_bias=bias,
        beats_baseline=mae < baseline,
    )


# ── Report ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labs", type=pathlib.Path, default=DEFAULT_LABS)
    parser.add_argument("--post", type=pathlib.Path, default=DEFAULT_POST)
    parser.add_argument("--sessions", type=pathlib.Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    print("Loading…")
    sessions = load_sessions(args.sessions)
    labs = load_labs(args.labs)
    post = load_post(args.post)
    print(f"  {len(sessions)} usable sessions  {sessions['date'].min().date()} → {sessions['date'].max().date()}")
    print(f"  {len(labs)} lab values, {labs['date'].nunique()} draws")
    print(f"  {len(post)} post-dialysis values\n")

    results: list[FitResult] = []
    for analyte in DIRECT_ANALYTES:
        fit = fit_direct(analyte, labs, post, sessions)
        if fit:
            results.append(fit)
    for analyte in DERIVED_ANALYTES:
        results.append(fit_derived(analyte, labs, sessions))
    for analyte in INTERDIALYTIC_ANALYTES:
        fit = fit_interdialytic(analyte, labs, sessions)
        if fit:
            results.append(fit)

    # Where an analyte was fitted more than one way, the hold-out decides.
    best: dict[str, FitResult] = {}
    for r in results:
        current = best.get(r.analyte)
        if current is None or (
            r.holdout_mae is not None
            and (current.holdout_mae is None or r.holdout_mae < current.holdout_mae)
        ):
            best[r.analyte] = r

    header = f"{'analyte':12s} {'method':14s} {'n_fit':>6s} {'n_test':>7s} {'MAE':>8s} {'baseline':>9s} {'vs base':>8s}  adopt"
    print(header)
    print("-" * len(header))
    for r in results:
        if r.holdout_mae is None:
            print(f"{r.analyte:12s} {r.method:14s} {r.n_fit:6d} {'—':>7s} {'—':>8s} {'—':>9s} {'—':>8s}  no   ({r.note})")
            continue
        improvement = r.improvement_pct
        print(
            f"{r.analyte:12s} {r.method:14s} {r.n_fit:6d} {r.n_holdout:7d} "
            f"{r.holdout_mae:8.3f} {r.baseline_mae:9.3f} {improvement:7.1f}%  "
            f"{'YES' if r.beats_baseline else 'no'}"
        )

    adopted = [r for r in best.values() if r.beats_baseline]
    print()
    print(f"{len(adopted)}/{len(best)} analytes beat the naive baseline on held-out draws.")
    if adopted:
        print("adopted: " + ", ".join(f"{r.analyte} ({r.method})" for r in adopted))
    if not adopted:
        print("No coefficient is adopted — the model stays on literature priors and")
        print("must not be used to widen any dietary limit.")

    if args.out:
        payload = {
            "generated_from": str(args.labs),
            "sessions": len(sessions),
            "results": [asdict(r) for r in results],
            "adopted": [r.analyte for r in adopted],
        }
        args.out.write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nwrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
