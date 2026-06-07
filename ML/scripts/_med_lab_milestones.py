"""
Medication & lab trend analysis for clinical milestones.
Verify: amlodipine/labetalol elimination, calcitriol intolerance,
phosphorus binder removal, PTH trends, phosphorus post-dialysis levels.
"""
import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# ---- MEDICATIONS ----
print("=" * 60)
print("1. MEDICATION CHANGES")
print("=" * 60)

meds = pd.read_csv(BASE / "data" / "processed" / "medications.csv")
print(f"Medications: {meds.shape}, cols: {list(meds.columns)}")

# Find date column
dcols = [c for c in meds.columns if "date" in c.lower()]
print(f"Date columns: {dcols}")

# Find medication name column
ncols = [c for c in meds.columns if "name" in c.lower() or "med" in c.lower() or "drug" in c.lower()]
print(f"Name columns: {ncols}")

# Show unique medications
if ncols:
    print(f"\nAll unique medications:")
    for m in sorted(meds[ncols[0]].dropna().unique()):
        print(f"  {m}")

# Check for specific meds
for keyword in ["amlod", "labeta", "labetol", "calcit", "phosph", "binder", "sevel", "renagel", "phoslo", "venofer", "iron", "epogen", "epo", "procrit", "aranesp"]:
    matches = meds[meds.apply(lambda row: any(keyword.lower() in str(v).lower() for v in row), axis=1)]
    if len(matches) > 0:
        print(f"\n  '{keyword}' matches ({len(matches)} records):")
        print(f"    {matches.head(5).to_string()}")

# ---- PHOSPHORUS & PTH TRENDS ----
print("\n" + "=" * 60)
print("2. PHOSPHORUS & PTH TRENDS")
print("=" * 60)

labs = pd.read_csv(BASE / "data" / "processed" / "unified_labs.csv")
print(f"Labs: {labs.shape}")

# Find relevant columns
dcol = [c for c in labs.columns if "date" in c.lower()][0]
ncol = [c for c in labs.columns if "test" in c.lower() or "name" in c.lower() or "analyte" in c.lower()]
vcol = [c for c in labs.columns if "value" in c.lower() or "result" in c.lower()]
print(f"Date: {dcol}, Name: {ncol}, Value: {vcol}")

if ncol and vcol:
    labs["date"] = pd.to_datetime(labs[dcol])
    labs["value"] = pd.to_numeric(labs[vcol[0]], errors="coerce")

    for analyte in ["PHOSPHORUS", "PTH", "CALCIUM", "VITAMIN D"]:
        subset = labs[labs[ncol[0]].str.upper().str.contains(analyte, na=False)]
        if len(subset) > 0:
            pre = subset[subset["date"] < "2018-10-01"]["value"].dropna()
            post = subset[subset["date"] >= "2019-01-01"]["value"].dropna()
            print(f"\n  {analyte}:")
            print(f"    Pre:  n={len(pre)}, mean={pre.mean():.1f}, std={pre.std():.1f}")
            print(f"    Post: n={len(post)}, mean={post.mean():.1f}, std={post.std():.1f}")

            # By year
            subset_yr = subset.copy()
            subset_yr["year"] = subset_yr["date"].dt.year
            yearly = subset_yr.groupby("year")["value"].agg(["mean", "std", "count"])
            print(f"    By year:\n{yearly.to_string()}")

# ---- POST-DIALYSIS PHOSPHORUS ----
print("\n" + "=" * 60)
print("3. POST-DIALYSIS PHOSPHORUS (if identifiable)")
print("=" * 60)

phos = labs[labs[ncol[0]].str.upper().str.contains("PHOSPHORUS", na=False)].copy()
if len(phos) > 0:
    # Check for POST designation
    post_cols = [c for c in labs.columns if "post" in c.lower() or "pre" in c.lower() or "type" in c.lower()]
    print(f"  Post/pre type columns: {post_cols}")
    
    # Low phosphorus readings (< 3.5 is KDOQI lower limit)
    low_phos = phos[phos["value"] < 3.5]
    pre_low = low_phos[low_phos["date"] < "2018-10-01"]
    post_low = low_phos[low_phos["date"] >= "2019-01-01"]
    print(f"  Phosphorus < 3.5 mg/dL:")
    print(f"    Pre:  {len(pre_low)} of {len(phos[phos['date'] < '2018-10-01'])} ({100*len(pre_low)/max(1,len(phos[phos['date']<'2018-10-01'])):.1f}%)")
    print(f"    Post: {len(post_low)} of {len(phos[phos['date'] >= '2019-01-01'])} ({100*len(post_low)/max(1,len(phos[phos['date']>='2019-01-01'])):.1f}%)")

# ---- HEMOGLOBIN VARIABILITY (rolling std) ----
print("\n" + "=" * 60)
print("4. HEMOGLOBIN VARIABILITY (rolling std over 90 days)")
print("=" * 60)

hgb = labs[labs[ncol[0]].str.upper().str.contains("HEMOGLOBIN", na=False) & ~labs[ncol[0]].str.upper().str.contains("POCT|RETICULOCYTE|A1C", na=False)].copy()
hgb = hgb.sort_values("date")
if len(hgb) > 10:
    hgb["rolling_std_90d"] = hgb["value"].rolling(window=6, min_periods=3).std()
    pre_std = hgb[hgb["date"] < "2018-10-01"]["rolling_std_90d"].dropna()
    post_std = hgb[hgb["date"] >= "2019-07-01"]["rolling_std_90d"].dropna()  # after transfusion end
    print(f"  Hemoglobin rolling std (90d window):")
    print(f"    Pre:  mean={pre_std.mean():.2f}")
    print(f"    Post (after 07/2019): mean={post_std.mean():.2f}")
    print(f"    Reduction: {(1 - post_std.mean()/pre_std.mean())*100:.1f}%")

# ---- TRANSFUSION EVIDENCE ----
print("\n" + "=" * 60)
print("5. TRANSFUSION EVIDENCE")
print("=" * 60)

# Look for sudden Hgb jumps (>2 g/dL between consecutive readings) as transfusion proxy
if len(hgb) > 10:
    hgb_sorted = hgb.sort_values("date").reset_index(drop=True)
    hgb_sorted["delta"] = hgb_sorted["value"].diff()
    jumps = hgb_sorted[hgb_sorted["delta"] > 2.0]
    print(f"  Hgb jumps > 2.0 g/dL (transfusion proxy):")
    for _, row in jumps.iterrows():
        print(f"    {row['date'].strftime('%Y-%m-%d')}: Hgb jump of +{row['delta']:.1f} g/dL (to {row['value']:.1f})")
    
    pre_jumps = jumps[jumps["date"] < "2018-10-01"]
    post_jumps = jumps[jumps["date"] >= "2019-07-01"]
    print(f"\n  Pre-G6PD jumps (transfusions): {len(pre_jumps)}")
    print(f"  Post-06/2019 jumps: {len(post_jumps)}")

print("\n=== DONE ===")
