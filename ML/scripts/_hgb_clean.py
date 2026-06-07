#!/usr/bin/env python3
"""Clean hemoglobin comparison — EHR + API labs only, filter outliers."""
import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"

# ── EHR labs (reliable Hemoglobin) ─────────────────────────
ehr = pd.read_csv(BASE / "raw" / "excel" / "records_lab.csv", low_memory=False)
ehr["date"] = pd.to_datetime(ehr["date"], errors="coerce")
hgb_ehr = ehr[ehr["test_name"].str.contains("^HEMOGLOBIN$|^HGB$|^Hemoglobin$", case=False, na=False, regex=True)].copy()
hgb_ehr["hgb"] = pd.to_numeric(hgb_ehr["value_numeric"], errors="coerce")
hgb_ehr = hgb_ehr.dropna(subset=["date", "hgb"])
# Show what test names matched
print("Test names matched:", hgb_ehr["test_name"].unique().tolist())
# Filter physiologically plausible (2-20 g/dL)
hgb_ehr = hgb_ehr[(hgb_ehr["hgb"] >= 2) & (hgb_ehr["hgb"] <= 20)]
hgb_ehr = hgb_ehr[["date", "hgb"]].sort_values("date").drop_duplicates()
print(f"Clean EHR hemoglobin: {len(hgb_ehr)}, {hgb_ehr['date'].min().date()} -> {hgb_ehr['date'].max().date()}")

# ── API labs ───────────────────────────────────────────────
api = pd.read_csv(BASE / "raw" / "api" / "lab_results.csv")
api["date"] = pd.to_datetime(api["date"], errors="coerce")
hgb_api = api[api["test_name"].str.contains("^HEMOGLOBIN$|^HGB$|^Hemoglobin$", case=False, na=False, regex=True)].copy()
hgb_api["hgb"] = pd.to_numeric(hgb_api["value"], errors="coerce")
hgb_api = hgb_api.dropna(subset=["date", "hgb"])
hgb_api = hgb_api[(hgb_api["hgb"] >= 2) & (hgb_api["hgb"] <= 20)]
hgb_api = hgb_api[["date", "hgb"]].sort_values("date").drop_duplicates()
print(f"Clean API hemoglobin: {len(hgb_api)}, {hgb_api['date'].min().date()} -> {hgb_api['date'].max().date()}")

# ── Combine ────────────────────────────────────────────────
all_hgb = pd.concat([hgb_ehr, hgb_api], ignore_index=True).drop_duplicates(subset=["date", "hgb"]).sort_values("date").reset_index(drop=True)
print(f"\nTotal clean Hgb: {len(all_hgb)}, {all_hgb['date'].min().date()} -> {all_hgb['date'].max().date()}")

CUT = pd.Timestamp("2019-01-01")
pre = all_hgb[all_hgb["date"] < CUT]
post = all_hgb[all_hgb["date"] >= CUT]

print(f"\n{'='*65}")
print("HEMOGLOBIN COMPARISON: Pre-2019 vs Post-01/2019 (clean data)")
print("=" * 65)

for label, df in [("PRE-2019", pre), ("POST-01/2019", post)]:
    if len(df) == 0:
        print(f"\n  {label}: NO DATA")
        continue
    print(f"\n  {label} (n={len(df)}, {df['date'].min().date()} -> {df['date'].max().date()})")
    print(f"    Mean:   {df['hgb'].mean():.2f} g/dL")
    print(f"    Median: {df['hgb'].median():.2f} g/dL")
    print(f"    Std:    {df['hgb'].std():.2f} g/dL")
    print(f"    Min:    {df['hgb'].min():.1f} g/dL  on {df.loc[df['hgb'].idxmin(), 'date'].date()}")
    print(f"    Max:    {df['hgb'].max():.1f} g/dL  on {df.loc[df['hgb'].idxmax(), 'date'].date()}")
    print(f"    Range:  {df['hgb'].max() - df['hgb'].min():.1f} g/dL")
    print(f"    CV:     {df['hgb'].std() / df['hgb'].mean() * 100:.1f}%")
    print(f"    < 5 g/dL (severe):    {(df['hgb'] < 5).sum()} ({(df['hgb'] < 5).mean()*100:.1f}%)")
    print(f"    < 7 g/dL (critical):  {(df['hgb'] < 7).sum()} ({(df['hgb'] < 7).mean()*100:.1f}%)")
    print(f"    < 8 g/dL (low):       {(df['hgb'] < 8).sum()} ({(df['hgb'] < 8).mean()*100:.1f}%)")
    print(f"    8-10 g/dL (subopt):   {((df['hgb'] >= 8) & (df['hgb'] < 10)).sum()} ({((df['hgb'] >= 8) & (df['hgb'] < 10)).mean()*100:.1f}%)")
    print(f"    10-13 g/dL (target):  {((df['hgb'] >= 10) & (df['hgb'] <= 13)).sum()} ({((df['hgb'] >= 10) & (df['hgb'] <= 13)).mean()*100:.1f}%)")

# Lowest 10 in each
for label, df in [("PRE-2019", pre), ("POST-01/2019", post)]:
    if len(df) == 0:
        continue
    n = min(15, len(df))
    print(f"\n  LOWEST {n} -- {label}:")
    for _, r in df.nsmallest(n, "hgb").iterrows():
        print(f"    {r['date'].date()}: {r['hgb']:.1f} g/dL")

# By year
print(f"\n{'='*65}")
print("HEMOGLOBIN BY YEAR (clean):")
all_hgb["year"] = all_hgb["date"].dt.year
yearly = all_hgb.groupby("year")["hgb"].agg(["count", "mean", "std", "min", "max"])
yearly["CV_pct"] = yearly["std"] / yearly["mean"] * 100
print(yearly.to_string())

# Pre-2019 Hgb < 5 episodes (possible transfusion triggers)
print(f"\n{'='*65}")
print("ALL Hgb < 5 g/dL EPISODES (transfusion triggers):")
severely_low = all_hgb[all_hgb["hgb"] < 5].sort_values("date")
for _, r in severely_low.iterrows():
    period = "PRE " if r["date"] < CUT else "POST"
    print(f"    [{period}] {r['date'].date()}: {r['hgb']:.1f} g/dL")

# Transfusion jumps (clean)
print(f"\n{'='*65}")
print("HEMOGLOBIN JUMPS > 2 g/dL (transfusion proxy, clean):")
all_hgb["diff"] = all_hgb["hgb"].diff()
all_hgb["days_gap"] = all_hgb["date"].diff().dt.days
jumps = all_hgb[all_hgb["diff"] > 2.0]
for _, r in jumps.iterrows():
    period = "PRE " if r["date"] < CUT else "POST"
    prev_val = r["hgb"] - r["diff"]
    print(f"    [{period}] {r['date'].date()}: {prev_val:.1f} -> {r['hgb']:.1f} (+{r['diff']:.1f}, gap: {r['days_gap']:.0f}d)")
print(f"\n  Pre-2019 jumps:     {(jumps['date'] < CUT).sum()}")
print(f"  Post-2019 jumps:    {(jumps['date'] >= CUT).sum()}")
print(f"  Post-06/2019 jumps: {(jumps['date'] >= '2019-07-01').sum()}")
