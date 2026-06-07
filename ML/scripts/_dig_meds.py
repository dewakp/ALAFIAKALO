#!/usr/bin/env python3
"""Dig deeper into medication timing and dialysis session medication data."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "data"

# 1. Check Calcium Carbonate dates (phosphorus binder)
print("=" * 60)
print("1. CALCIUM CARBONATE (PHOSPHORUS BINDER) DATE RANGE")
print("=" * 60)
# Try multiple locations
for mpath in [ROOT / "raw" / "api" / "medications.csv", ROOT / "processed" / "medications.csv"]:
    if mpath.exists():
        print(f"  Using: {mpath}")
        break
meds = pd.read_csv(mpath, parse_dates=["date"])
for med_name in meds["medication_name"].unique():
    sub = meds[meds["medication_name"] == med_name].sort_values("date")
    print(f"  {med_name}: {sub['date'].min().date()} → {sub['date'].max().date()} ({len(sub)} records)")

# 2. Calcitriol timeline
print("\n" + "=" * 60)
print("2. CALCITRIOL TIMELINE")
print("=" * 60)
cal = meds[meds["medication_name"].str.contains("calcit", case=False, na=False)].sort_values("date")
print(f"  Records: {len(cal)}")
print(f"  Date range: {cal['date'].min().date()} → {cal['date'].max().date()}")
print(f"  By year-month:")
cal["ym"] = cal["date"].dt.to_period("M")
for ym, grp in cal.groupby("ym"):
    print(f"    {ym}: {len(grp)} doses, dosages: {grp['dosage'].unique().tolist()}")

# 3. Check dialysis sessions for medication columns
print("\n" + "=" * 60)
print("3. DIALYSIS SESSIONS — MEDICATION-RELATED COLUMNS")
print("=" * 60)
for dpath in [ROOT / "raw" / "api" / "dialysis_sessions.csv", ROOT / "processed" / "dialysis_sessions.csv", ROOT / "raw" / "dialysis_sessions.csv"]:
    if dpath.exists():
        print(f"  Using: {dpath}")
        break
dial = pd.read_csv(dpath)
med_cols = [c for c in dial.columns if any(k in c.lower() for k in ["med", "drug", "epoetin", "epo", "venofer", "iron", "erythro", "darbe"])]
print(f"  Session columns with med/drug/epo/iron keywords: {med_cols}")
# Also check all columns for anything interesting
all_cols = sorted(dial.columns.tolist())
print(f"  All columns ({len(all_cols)}):")
for c in all_cols:
    print(f"    {c}")

# 4. Check if there's an ESA/iron/transfusion dataset
print("\n" + "=" * 60)
print("4. SEARCH FOR ESA/IRON/TRANSFUSION DATA FILES")
print("=" * 60)
for p in sorted(ROOT.rglob("*")):
    if p.is_file() and any(k in p.name.lower() for k in ["transfus", "esa", "epo", "iron", "venofer", "blood"]):
        print(f"  {p.relative_to(ROOT)}")

# Also check all raw files
print("\n  All raw files:")
for p in sorted((ROOT / "raw").iterdir()):
    if p.is_file():
        print(f"    {p.name}")

# 5. PTH sudden drop — check 2025-2026 data more carefully
print("\n" + "=" * 60)
print("5. PTH 2024-2026 DETAIL (parathyroidectomy?)")
print("=" * 60)
labs = pd.read_csv(ROOT / "raw" / "api" / "lab_results.csv") if (ROOT / "raw" / "api" / "lab_results.csv").exists() else pd.read_csv(ROOT / "processed" / "lab_results.csv")
for dcol in ["date", "collection_date", "result_date", "lab_date"]:
    if dcol in labs.columns:
        labs[dcol] = pd.to_datetime(labs[dcol], errors="coerce")
        date_col = dcol
        break

name_col = "test_name" if "test_name" in labs.columns else labs.columns[1]
val_col = "value_numeric" if "value_numeric" in labs.columns else "value"

pth = labs[labs[name_col].str.contains("PTH|parathyroid", case=False, na=False)].copy()
pth = pth.sort_values(date_col)
recent = pth[pth[date_col] >= "2024-01-01"]
for _, row in recent.iterrows():
    print(f"  {row[date_col].date()}: PTH = {row[val_col]} {row.get('units', '')}")

print("\n=== DONE ===")
