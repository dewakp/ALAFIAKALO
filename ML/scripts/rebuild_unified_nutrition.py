#!/usr/bin/env python3
"""
Rebuild unified_nutrition.csv from:
  1. data/raw/excel/records_food.csv (freshly extracted from RecordsN.xlsx)
  2. Existing Firestore rows from old unified_nutrition.csv (source=firestore)

Preserves existing nutrient columns for rows that already had values.
"""
import pandas as pd
import numpy as np
from pathlib import Path

ML = Path(__file__).resolve().parent.parent
RECORDS_FOOD = ML / 'data' / 'raw' / 'excel' / 'records_food.csv'
FIRESTORE_NUTRITION = ML / 'data' / 'raw' / 'api' / 'nutrition.csv'
OLD_UNIFIED = ML / 'data' / 'processed' / 'unified_nutrition.csv'
OUTPUT = ML / 'data' / 'processed' / 'unified_nutrition.csv'
BACKUP = ML / 'data' / 'processed' / 'unified_nutrition_backup.csv'

# ── 1. Load fresh records_food.csv ──
rf = pd.read_csv(RECORDS_FOOD)
print(f"records_food.csv: {len(rf)} rows, date range {rf['date'].min()} → {rf['date'].max()}")

# ── 2. Load fresh Firestore nutrition data ──
fs = pd.read_csv(FIRESTORE_NUTRITION)
print(f"Firestore nutrition.csv: {len(fs)} rows, date range {fs['date'].min()} → {fs['date'].max()}")

# ── 3. Backup old unified ──
if Path(OLD_UNIFIED).exists():
    old = pd.read_csv(OLD_UNIFIED)
    old.to_csv(BACKUP, index=False)
    print(f"Backed up old unified ({len(old)} rows) to {BACKUP}")

# ── 4. Build Firestore portion ──
firestore_rows = fs.copy()
firestore_rows['source'] = 'firestore'
# Map Firestore columns to unified format
col_remap = {
    'food_description': 'description',
    'food_items': 'food_item',
}
for old_name, new_name in col_remap.items():
    if old_name in firestore_rows.columns and new_name not in firestore_rows.columns:
        firestore_rows[new_name] = firestore_rows[old_name]
if 'food_item' not in firestore_rows.columns:
    firestore_rows['food_item'] = firestore_rows.get('description', '')

print(f"  Firestore rows: {len(firestore_rows)}")

# ── 3. Build new records_xlsx portion ──
# Map columns to match unified_nutrition format
records_df = rf.copy()
records_df['source'] = records_df['source'].replace({
    'Food': 'records_xlsx',
    'FoodLog': 'records_xlsx',
    'FoodLog2022': 'records_xlsx',
    'FoodLog2023': 'records_xlsx',
    'FoodLog2024': 'records_xlsx',
    'FoodLog2025': 'records_xlsx',
})

# Combine description into food_item
records_df['food_item'] = records_df['description'].fillna('')
records_df['meal_type'] = np.nan
records_df['pre_meal_weight_kg'] = records_df['pre_weight_kg']
records_df['post_meal_weight_kg'] = records_df['post_weight_kg']
records_df['ai_summary'] = np.nan

# Nutrient columns — start as NaN (enrichment will fill them)
nutrient_cols = ['calories', 'protein', 'carbs', 'fat', 'fiber', 'sugar',
                 'sodium', 'potassium', 'calcium', 'iron', 'phosphorus',
                 'vitamin_d', 'vitamin_b12', 'folic_acid', 'cholesterol']
for col in nutrient_cols:
    records_df[col] = np.nan

# Try to preserve existing nutrient values from old unified rows
if Path(BACKUP).exists():
    old = pd.read_csv(BACKUP)
    old_records = old[old['source'] == 'records_xlsx'].copy()
    if not old_records.empty:
        # Match on date + description
        old_records['_merge_key'] = old_records['date'].astype(str) + '|' + old_records['description'].fillna('')
        records_df['_merge_key'] = records_df['date'].astype(str) + '|' + records_df['description'].fillna('')
        
        # For matching rows, copy existing nutrient values
        old_nutr = old_records.set_index('_merge_key')[nutrient_cols]
        old_nutr = old_nutr[~old_nutr.index.duplicated()]  # Remove dups
        
        matched = 0
        for idx, row in records_df.iterrows():
            key = row['_merge_key']
            if key in old_nutr.index:
                for col in nutrient_cols:
                    if pd.notna(old_nutr.loc[key, col]):
                        records_df.at[idx, col] = old_nutr.loc[key, col]
                matched += 1
        
        print(f"  Preserved nutrient values for {matched} / {len(records_df)} records rows")
        records_df.drop('_merge_key', axis=1, inplace=True)

# ── 4. Combine records_xlsx + firestore ──
# Align columns
all_cols = ['date', 'time_slot', 'description', 'source', 'start_time', 'end_time',
            'quantity', 'pre_weight_kg', 'post_weight_kg', 'state_post', 'medication',
            'new_recipe', 'recipe_code',
            'meal_type', 'food_item', 'pre_meal_weight_kg', 'post_meal_weight_kg',
            *nutrient_cols, 'ai_summary']

for col in all_cols:
    if col not in records_df.columns:
        records_df[col] = np.nan
    if col not in firestore_rows.columns:
        firestore_rows[col] = np.nan

unified = pd.concat([records_df[all_cols], firestore_rows[all_cols]], ignore_index=True)
unified = unified.sort_values(['date', 'start_time']).reset_index(drop=True)

# ── 5. Save ──
unified.to_csv(OUTPUT, index=False)
print(f"\n{'='*60}")
print(f"NEW unified_nutrition.csv: {len(unified)} rows")
print(f"  Sources: {unified['source'].value_counts().to_dict()}")
print(f"  Date range: {unified['date'].min()} → {unified['date'].max()}")
print(f"  Rows with medication: {unified['medication'].notna().sum()}")
print(f"  Rows with recipe_code: {unified['recipe_code'].notna().sum()}")
print(f"  Rows with new_recipe: {unified['new_recipe'].notna().sum()}")
print(f"  Rows with calories (pre-existing): {unified['calories'].notna().sum()}")
print(f"  Rows needing enrichment: {unified['calories'].isna().sum()}")
print(f"  Saved to {OUTPUT}")
