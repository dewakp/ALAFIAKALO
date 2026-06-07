"""
HEBCS Drift Monitor — Lightweight feature-distribution monitoring
══════════════════════════════════════════════════════════════════

Compares incoming feature vectors against training-time statistics
(min, max, median, missing_pct) stored in models/schema.json and
flags out-of-distribution inputs before they reach the model.

Usage:
    from drift_monitor import DriftMonitor

    monitor = DriftMonitor.from_schema("models/schema.json")
    report  = monitor.check(feature_dict)

    if report.has_warnings:
        print(report.summary())

CLI:
    python drift_monitor.py --schema models/schema.json \
        --features data/features/health_features.csv --row -1
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════════
#  Data classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DriftAlert:
    """Single feature-level alert."""
    feature: str
    kind: str          # "out_of_range", "missing", "extreme_z"
    value: float
    detail: str

    def __repr__(self) -> str:
        return f"DriftAlert({self.feature}: {self.kind} — {self.detail})"


@dataclass
class DriftReport:
    """Full drift-check report for one feature vector."""
    n_features_checked: int = 0
    alerts: list[DriftAlert] = field(default_factory=list)
    _feature_stats: dict = field(default_factory=dict, repr=False)

    @property
    def has_warnings(self) -> bool:
        return len(self.alerts) > 0

    @property
    def n_alerts(self) -> int:
        return len(self.alerts)

    def summary(self) -> str:
        lines = [
            f"Drift Report: {self.n_alerts} alert(s) across "
            f"{self.n_features_checked} features"
        ]
        for a in self.alerts:
            lines.append(f"  [{a.kind}] {a.feature}: {a.detail}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "n_features_checked": self.n_features_checked,
            "n_alerts": self.n_alerts,
            "has_warnings": self.has_warnings,
            "alerts": [
                {"feature": a.feature, "kind": a.kind,
                 "value": a.value, "detail": a.detail}
                for a in self.alerts
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  Monitor
# ═══════════════════════════════════════════════════════════════════════════════

class DriftMonitor:
    """
    Compare incoming features against training-time distributions.

    Checks performed per feature:
      1. Out-of-range:  value < training min  OR  value > training max
      2. Missing:       value is NaN
      3. Extreme shift: |value − median| > k × (max − min)   (k=2 default)
    """

    def __init__(
        self,
        feature_stats: dict[str, dict],
        *,
        range_k: float = 2.0,
    ):
        """
        Args:
            feature_stats: {feature_name: {min, max, median, missing_pct}}
            range_k: multiplier for extreme-shift detection
                     (value further than k * range from median → alert)
        """
        self._stats = feature_stats
        self._k = range_k

    # ─── Factory ──────────────────────────────────────────────────────────

    @classmethod
    def from_schema(cls, schema_path: str = "models/schema.json", **kwargs) -> "DriftMonitor":
        """Load feature statistics from schema.json."""
        schema = json.loads(Path(schema_path).read_text())

        stats: dict[str, dict] = {}

        # Gather from both holistic and clinical feature sections
        # Schema stores stats under "details" (primary) or "per_feature_stats"
        for section_key in ("holistic_health_features", "clinical_risk_features"):
            section = schema.get("features", {}).get(section_key, {})
            per_feature = (
                section.get("details", {})
                or section.get("per_feature_stats", {})
            )
            for feat_name, s in per_feature.items():
                stats[feat_name] = {
                    "min": s.get("min", float("-inf")),
                    "max": s.get("max", float("inf")),
                    "median": s.get("median", 0.0),
                    "missing_pct": s.get("missing_pct", 0.0),
                }

        if not stats:
            print("[DriftMonitor] Warning: no per_feature_stats in schema",
                  file=sys.stderr)

        return cls(stats, **kwargs)

    # ─── Check ────────────────────────────────────────────────────────────

    def check(
        self,
        features: dict[str, float] | pd.Series,
    ) -> DriftReport:
        """Check a single feature vector for drift."""
        if isinstance(features, pd.Series):
            features = features.to_dict()

        report = DriftReport()
        checked_features = set(features.keys()) & set(self._stats.keys())
        report.n_features_checked = len(checked_features)

        for feat in sorted(checked_features):
            val = features[feat]
            s = self._stats[feat]
            t_min, t_max = s["min"], s["max"]
            t_median = s["median"]
            t_range = t_max - t_min if np.isfinite(t_max - t_min) else 0

            # 1. Missing
            if val is None or (isinstance(val, float) and np.isnan(val)):
                report.alerts.append(DriftAlert(
                    feature=feat, kind="missing", value=float("nan"),
                    detail="Value is NaN/missing",
                ))
                continue

            # 2. Out of range (hard)
            if np.isfinite(t_min) and val < t_min:
                report.alerts.append(DriftAlert(
                    feature=feat, kind="out_of_range", value=val,
                    detail=f"{val:.4g} < training min {t_min:.4g}",
                ))
            elif np.isfinite(t_max) and val > t_max:
                report.alerts.append(DriftAlert(
                    feature=feat, kind="out_of_range", value=val,
                    detail=f"{val:.4g} > training max {t_max:.4g}",
                ))

            # 3. Extreme shift (soft — value far from median relative to range)
            if t_range > 0 and np.isfinite(t_median):
                deviation = abs(val - t_median) / t_range
                if deviation > self._k:
                    report.alerts.append(DriftAlert(
                        feature=feat, kind="extreme_z", value=val,
                        detail=(
                            f"Deviation {deviation:.2f}× range from median "
                            f"(val={val:.4g}, median={t_median:.4g}, "
                            f"range={t_range:.4g})"
                        ),
                    ))

        return report

    def check_batch(
        self,
        df: pd.DataFrame,
    ) -> list[DriftReport]:
        """Check multiple rows."""
        return [self.check(row) for _, row in df.iterrows()]

    def summary_stats(self, reports: list[DriftReport]) -> dict:
        """Aggregate drift stats across many rows."""
        from collections import Counter
        alert_counts: Counter = Counter()
        feature_counts: Counter = Counter()
        for r in reports:
            for a in r.alerts:
                alert_counts[a.kind] += 1
                feature_counts[a.feature] += 1

        return {
            "total_rows": len(reports),
            "rows_with_alerts": sum(1 for r in reports if r.has_warnings),
            "total_alerts": sum(r.n_alerts for r in reports),
            "by_kind": dict(alert_counts.most_common()),
            "top_features": dict(feature_counts.most_common(10)),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="HEBCS Drift Monitor")
    parser.add_argument("--schema", default="models/schema.json")
    parser.add_argument("--features", required=True,
                        help="CSV with feature vectors")
    parser.add_argument("--row", type=int, default=None,
                        help="Check a specific row (default: all rows)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--k", type=float, default=2.0,
                        help="Extreme-shift multiplier (default: 2.0)")
    args = parser.parse_args()

    monitor = DriftMonitor.from_schema(args.schema, range_k=args.k)
    df = pd.read_csv(args.features)

    if args.row is not None:
        report = monitor.check(df.iloc[args.row])
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(report.summary())
    else:
        reports = monitor.check_batch(df)
        stats = monitor.summary_stats(reports)
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(f"\nDrift Summary ({stats['total_rows']} rows):")
            print(f"  Rows with alerts: {stats['rows_with_alerts']}")
            print(f"  Total alerts:     {stats['total_alerts']}")
            if stats["by_kind"]:
                print(f"  By kind:          {stats['by_kind']}")
            if stats["top_features"]:
                print(f"  Top features:     {stats['top_features']}")
            print()


if __name__ == "__main__":
    main()
