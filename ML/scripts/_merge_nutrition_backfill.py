#!/usr/bin/env python3
"""
Merge LLM-backfilled nutrient values into unified_nutrition.csv.

Strategy:
  - Read backfill CSV (per-food-description nutrient totals)
  - Group by original_index to get one row per original nutrition entry
  - Overwrite empty nutrient columns in unified_nutrition.csv with backfill values
  - Preserve any existing hand-entered nutrient data
"""
import pandas as pd
import numpy as np
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent.parent
UNIFIED  = ML_ROOT / "data" / "processed" / "unified_nutrition.csv"
BACKFILL = ML_ROOT / "data" / "nutrition_backfill" / "nutrition_backfilled.csv"
OUTPUT   = UNIFIED  # overwrite in-place (backup first)
BACKUP   = UNIFIED.with_suffix(".csv.bak")

# ── Load ──
print("Loading unified_nutrition.csv ...")
df_orig = pd.read_csv(UNIFIED, low_memory=False)
print(f"  Rows: {len(df_orig)}")

print("Loading nutrition_backfilled.csv ...")
df_back = pd.read_csv(BACKFILL, low_memory=False)
print(f"  Rows: {len(df_back)}")
print(f"  Unique original_index: {df_back['original_index'].nunique()}")

# ── Aggregate backfill by original_index ──
# Each original_index maps to one row in unified_nutrition.csv
# The backfill CSV may have one row per original index already (with totals)
# or may have duplicates if the same index was retried. Take the first successful.
nutrient_cols = ['calories', 'protein', 'carbs', 'fat', 'fiber', 'sugar',
                 'sodium', 'potassium', 'calcium', 'iron', 'phosphorus',
                 'cholesterol', 'vitamin_d', 'vitamin_b12', 'folic_acid']

# Keep only rows with actual nutrient data
df_back_valid = df_back.dropna(subset=['calories'])
df_back_valid = df_back_valid[df_back_valid['calories'] > 0]
print(f"  Valid backfill rows (calories > 0): {len(df_back_valid)}")

# Group by original_index — sum nutrients (multiple food items per meal)
# Actually check if there are duplicates first
dup_check = df_back_valid.groupby('original_index').size()
print(f"  Indices with >1 row: {(dup_check > 1).sum()}")
print(f"  Max rows per index: {dup_check.max()}")

# If there are duplicate indices, it means either the items were split or
# there were retries. Sum the nutrients for each unique original_index.
backfill_agg = df_back_valid.groupby('original_index')[nutrient_cols].sum().reset_index()
print(f"  Aggregated to {len(backfill_agg)} unique indices")

# ── Count pre-merge coverage ──
orig_nutrient_cols = [c for c in nutrient_cols if c in df_orig.columns]
for col in orig_nutrient_cols:
    df_orig[col] = pd.to_numeric(df_orig[col], errors='coerce')

pre_coverage = {}
for col in orig_nutrient_cols:
    pre_coverage[col] = (df_orig[col].notna() & (df_orig[col] > 0)).sum()
print(f"\nPre-merge coverage (rows with data):")
for col, cnt in pre_coverage.items():
    print(f"  {col}: {cnt}/{len(df_orig)}")

# ── Backup ──
df_orig.to_csv(BACKUP, index=False)
print(f"\nBacked up original to {BACKUP.name}")

# ── Merge ──
filled = 0
for _, row in backfill_agg.iterrows():
    idx = int(row['original_index'])
    if idx >= len(df_orig):
        continue
    for col in nutrient_cols:
        if col not in df_orig.columns:
            df_orig[col] = np.nan
        # Only fill if the existing value is empty/zero
        existing = df_orig.at[idx, col]
        if pd.isna(existing) or existing == 0:
            df_orig.at[idx, col] = row[col]
    filled += 1

print(f"Merged {filled} rows from backfill")

# ── Post-merge coverage ──
post_coverage = {}
for col in nutrient_cols:
    if col in df_orig.columns:
        df_orig[col] = pd.to_numeric(df_orig[col], errors='coerce')
        post_coverage[col] = (df_orig[col].notna() & (df_orig[col] > 0)).sum()

print(f"\nPost-merge coverage:")
for col in nutrient_cols:
    pre = pre_coverage.get(col, 0)
    post = post_coverage.get(col, 0)
    delta = post - pre
    print(f"  {col}: {pre} → {post}  (+{delta})")

# ── Save ──
df_orig.to_csv(OUTPUT, index=False)
print(f"\nSaved merged file: {OUTPUT}")
print(f"Total rows: {len(df_orig)}")
