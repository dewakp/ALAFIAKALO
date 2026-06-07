#!/usr/bin/env python3
"""Compare hemoglobin extremes pre vs post January 2019 — using ALL data sources."""
import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"

# ── Gather hemoglobin from ALL sources ────────────────────
frames = []

# 1. API lab_results
api_labs = pd.read_csv(BASE / "raw" / "api" / "lab_results.csv")
for dcol in ["date", "collection_date", "result_date"]:
    if dcol in api_labs.columns:
        api_labs["lab_date"] = pd.to_datetime(api_labs[dcol], errors="coerce")
        break
name_col = "test_name" if "test_name" in api_labs.columns else api_labs.columns[1]
val_col = "value_numeric" if "value_numeric" in api_labs.columns else "value"
hgb_api = api_labs[api_labs[name_col].str.contains("hemoglobin|hgb", case=False, na=False)].copy()
hgb_api["hgb"] = pd.to_numeric(hgb_api[val_col], errors="coerce")
hgb_api = hgb_api.dropna(subset=["lab_date", "hgb"])[["lab_date", "hgb"]]
hgb_api["source"] = "api_labs"
frames.append(hgb_api)
print(f"API labs hemoglobin: {len(hgb_api)} records, {hgb_api['lab_date'].min()} -> {hgb_api['lab_date'].max()}")

# 2. Excel records_lab (EHR)
ehr_labs_path = BASE / "raw" / "excel" / "records_lab.csv"
if ehr_labs_path.exists():
    ehr = pd.read_csv(ehr_labs_path, low_memory=False)
    print(f"\nEHR labs: {ehr.shape}, columns: {list(ehr.columns[:15])}")
    date_candidates = [c for c in ehr.columns if "date" in c.lower()]
    print(f"  Date columns: {date_candidates}")
    name_candidates = [c for c in ehr.columns if "name" in c.lower() or "test" in c.lower()]
    print(f"  Name columns: {name_candidates}")
    
    ehr_date_col = date_candidates[0] if date_candidates else ehr.columns[0]
    ehr["lab_date"] = pd.to_datetime(ehr[ehr_date_col], errors="coerce")
    
    ehr_name_col = None
    for nc in name_candidates:
        if ehr[nc].astype(str).str.contains("hemoglobin|hgb", case=False).any():
            ehr_name_col = nc
            break
    if not ehr_name_col:
        for c in ehr.columns:
            if ehr[c].astype(str).str.contains("hemoglobin|hgb", case=False).any():
                ehr_name_col = c
                print(f"  Found hemoglobin in column: {c}")
                break
    
    if ehr_name_col:
        hgb_ehr = ehr[ehr[ehr_name_col].astype(str).str.contains("hemoglobin|hgb", case=False, na=False)].copy()
        val_candidates = [c for c in ehr.columns if "value" in c.lower() or "result" in c.lower()]
        print(f"  Value columns: {val_candidates}")
        if val_candidates:
            hgb_ehr["hgb"] = pd.to_numeric(hgb_ehr[val_candidates[0]], errors="coerce")
            hgb_ehr = hgb_ehr.dropna(subset=["lab_date", "hgb"])[["lab_date", "hgb"]]
            hgb_ehr["source"] = "ehr_labs"
            frames.append(hgb_ehr)
            print(f"  EHR hemoglobin: {len(hgb_ehr)} records, {hgb_ehr['lab_date'].min()} -> {hgb_ehr['lab_date'].max()}")
    else:
        print("  WARNING: No hemoglobin column found in EHR labs")

# 3. Processed unified_labs
uni_path = BASE / "processed" / "unified_labs.csv"
if uni_path.exists():
    uni = pd.read_csv(uni_path, low_memory=False)
    print(f"\nUnified labs: {uni.shape}, cols: {list(uni.columns[:15])}")
    for dcol in ["date", "collection_date", "lab_date"]:
        if dcol in uni.columns:
            uni["lab_date"] = pd.to_datetime(uni[dcol], errors="coerce")
            break
    uni_name_col = None
    for nc in uni.columns:
        if uni[nc].astype(str).str.contains("hemoglobin|hgb", case=False).any():
            uni_name_col = nc
            break
    if uni_name_col:
        hgb_uni = uni[uni[uni_name_col].astype(str).str.contains("hemoglobin|hgb", case=False, na=False)].copy()
        val_candidates = [c for c in uni.columns if "value" in c.lower() or "result" in c.lower()]
        if val_candidates:
            hgb_uni["hgb"] = pd.to_numeric(hgb_uni[val_candidates[0]], errors="coerce")
            hgb_uni = hgb_uni.dropna(subset=["lab_date", "hgb"])[["lab_date", "hgb"]]
            hgb_uni["source"] = "unified_labs"
            frames.append(hgb_uni)
            print(f"  Unified hemoglobin: {len(hgb_uni)} records, {hgb_uni['lab_date'].min()} -> {hgb_uni['lab_date'].max()}")

# 4. daily_unified (processed features)
daily_path = BASE / "processed" / "daily_unified.csv"
if daily_path.exists():
    daily = pd.read_csv(daily_path, parse_dates=["date"], low_memory=False)
    hgb_cols = [c for c in daily.columns if "hgb" in c.lower() or "hemoglobin" in c.lower()]
    print(f"\nDaily unified hemoglobin columns: {hgb_cols}")
    if hgb_cols:
        hgb_daily = daily[["date"] + hgb_cols].dropna(subset=hgb_cols, how="all").copy()
        hgb_daily["hgb"] = pd.to_numeric(hgb_daily[hgb_cols[0]], errors="coerce")
        hgb_daily = hgb_daily.rename(columns={"date": "lab_date"}).dropna(subset=["hgb"])[["lab_date", "hgb"]]
        hgb_daily["source"] = "daily_unified"
        frames.append(hgb_daily)
        print(f"  Daily unified hemoglobin: {len(hgb_daily)} records, {hgb_daily['lab_date'].min()} -> {hgb_daily['lab_date'].max()}")

# 5. Lab pivot canonical
pivot_path = BASE / "features" / "lab_pivot_canonical.csv"
if pivot_path.exists():
    pivot = pd.read_csv(pivot_path, low_memory=False)
    print(f"\nLab pivot canonical: {pivot.shape}")
    hgb_pcols = [c for c in pivot.columns if "hgb" in c.lower() or "hemoglobin" in c.lower()]
    print(f"  Hemoglobin columns: {hgb_pcols}")
    if hgb_pcols and "date" in pivot.columns:
        pivot["lab_date"] = pd.to_datetime(pivot["date"], errors="coerce")
        hgb_piv = pivot[["lab_date"] + hgb_pcols].dropna(subset=hgb_pcols, how="all").copy()
        hgb_piv["hgb"] = pd.to_numeric(hgb_piv[hgb_pcols[0]], errors="coerce")
        hgb_piv = hgb_piv.dropna(subset=["hgb"])[["lab_date", "hgb"]]
        hgb_piv["source"] = "lab_pivot"
        frames.append(hgb_piv)
        print(f"  Lab pivot hemoglobin: {len(hgb_piv)} records, {hgb_piv['lab_date'].min()} -> {hgb_piv['lab_date'].max()}")

# ── Combine and deduplicate ────────────────────────────────
all_hgb = pd.concat(frames, ignore_index=True)
all_hgb = all_hgb.drop_duplicates(subset=["lab_date", "hgb"]).sort_values("lab_date").reset_index(drop=True)
print(f"\n{'='*65}")
print(f"TOTAL UNIQUE HEMOGLOBIN: {len(all_hgb)} records")
print(f"Date range: {all_hgb['lab_date'].min().date()} -> {all_hgb['lab_date'].max().date()}")
print(f"Sources: {all_hgb['source'].value_counts().to_dict()}")

# ── Compare pre vs post ────────────────────────────────────
CUT = pd.Timestamp("2019-01-01")
pre = all_hgb[all_hgb["lab_date"] < CUT]
post = all_hgb[all_hgb["lab_date"] >= CUT]

print(f"\n{'='*65}")
print("HEMOGLOBIN COMPARISON: Pre-2019 vs Post-01/2019")
print("=" * 65)

for label, df in [("PRE-2019", pre), ("POST-01/2019", post)]:
    if len(df) == 0:
        print(f"\n  {label}: NO DATA")
        continue
    print(f"\n  {label} (n={len(df)}, {df['lab_date'].min().date()} -> {df['lab_date'].max().date()})")
    print(f"    Mean:   {df['hgb'].mean():.2f} g/dL")
    print(f"    Median: {df['hgb'].median():.2f} g/dL")
    print(f"    Std:    {df['hgb'].std():.2f} g/dL")
    print(f"    Min:    {df['hgb'].min():.1f} g/dL  on {df.loc[df['hgb'].idxmin(), 'lab_date'].date()}")
    print(f"    Max:    {df['hgb'].max():.1f} g/dL  on {df.loc[df['hgb'].idxmax(), 'lab_date'].date()}")
    print(f"    Range:  {df['hgb'].max() - df['hgb'].min():.1f} g/dL")
    print(f"    CV:     {df['hgb'].std() / df['hgb'].mean() * 100:.1f}%")
    print(f"    < 7 g/dL (critical):  {(df['hgb'] < 7).sum()} ({(df['hgb'] < 7).mean()*100:.1f}%)")
    print(f"    < 8 g/dL (low):       {(df['hgb'] < 8).sum()} ({(df['hgb'] < 8).mean()*100:.1f}%)")
    print(f"    10-13 g/dL (target):  {((df['hgb'] >= 10) & (df['hgb'] <= 13)).sum()} ({((df['hgb'] >= 10) & (df['hgb'] <= 13)).mean()*100:.1f}%)")

# Lowest 10 in each period
for label, df in [("PRE-2019", pre), ("POST-01/2019", post)]:
    if len(df) == 0:
        continue
    n = min(10, len(df))
    print(f"\n  LOWEST {n} -- {label}:")
    for _, r in df.nsmallest(n, "hgb").iterrows():
        print(f"    {r['lab_date'].date()}: {r['hgb']:.1f} g/dL  [{r['source']}]")

# By year
print(f"\n{'='*65}")
print("HEMOGLOBIN BY YEAR:")
all_hgb["year"] = all_hgb["lab_date"].dt.year
yearly = all_hgb.groupby("year")["hgb"].agg(["count", "mean", "std", "min", "max"])
yearly["CV_pct"] = yearly["std"] / yearly["mean"] * 100
print(yearly.to_string())

# Jumps > 2 g/dL
print(f"\n{'='*65}")
print("HEMOGLOBIN JUMPS > 2 g/dL (transfusion proxy):")
all_hgb = all_hgb.sort_values("lab_date").reset_index(drop=True)
all_hgb["diff"] = all_hgb["hgb"].diff()
all_hgb["days_gap"] = all_hgb["lab_date"].diff().dt.days
jumps = all_hgb[all_hgb["diff"] > 2.0]
for _, r in jumps.iterrows():
    period = "PRE " if r["lab_date"] < CUT else "POST"
    print(f"    [{period}] {r['lab_date'].date()}: +{r['diff']:.1f} g/dL -> {r['hgb']:.1f} (gap: {r['days_gap']:.0f}d)")
print(f"\n  Pre-2019 jumps:  {(jumps['lab_date'] < CUT).sum()}")
print(f"  Post-2019 jumps: {(jumps['lab_date'] >= CUT).sum()}")
