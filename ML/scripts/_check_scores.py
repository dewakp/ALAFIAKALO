"""Analyze pathway-level and composite score distributions for clinical plausibility."""
import pandas as pd
import numpy as np

from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
df = pd.read_csv(BASE / "data" / "features" / "health_features.csv", parse_dates=["date"])

pathways = ["Metabolic", "Hemolytical", "Endocrinology", "Digestive",
            "Immunological", "BoneFormation", "Neurological"]

pcols = [c for c in df.columns
         if any(p.lower() in c.lower() for p in pathways) and "score" in c.lower()]

print("=== Pathway score columns ===")
for c in sorted(pcols):
    vals = df[c].dropna()
    print(f"  {c:40s}  n={len(vals):5d}  mean={vals.mean():.3f}  "
          f"median={vals.median():.3f}  std={vals.std():.3f}  "
          f"min={vals.min():.3f}  max={vals.max():.3f}")

wcols = [c for c in df.columns
         if "wellness" in c.lower() or "holistic" in c.lower()
         or "product" in c.lower() or "additive" in c.lower()
         or "geometric" in c.lower()]

print("\n=== Wellness/composite columns ===")
for c in sorted(wcols):
    vals = df[c].dropna()
    print(f"  {c:40s}  n={len(vals):5d}  mean={vals.mean():.3f}  "
          f"median={vals.median():.3f}  std={vals.std():.3f}")

pcol = [c for c in df.columns if "product" in c.lower()]
if pcol:
    vals = df[pcol[0]].dropna()
    print(f"\n=== Product score distribution ({pcol[0]}) ===")
    for threshold in [20, 30, 40, 50, 60, 70]:
        n = (vals < threshold).sum()
        print(f"  < {threshold}: {n:5d} days ({100 * n / len(vals):.1f}%)")
    for threshold in [80, 90]:
        n = (vals >= threshold).sum()
        print(f"  >= {threshold}: {n:5d} days ({100 * n / len(vals):.1f}%)")

print("\n=== Proportion of time each pathway is LOW ===")
for c in sorted(pcols):
    vals = df[c].dropna()
    if len(vals) > 0:
        pct_05 = 100 * (vals < 0.5).mean()
        pct_03 = 100 * (vals < 0.3).mean()
        pct_01 = 100 * (vals < 0.1).mean()
        print(f"  {c:40s}  <0.5: {pct_05:5.1f}%   <0.3: {pct_03:5.1f}%   <0.1: {pct_01:5.1f}%")
