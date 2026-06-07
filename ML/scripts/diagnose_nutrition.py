#!/usr/bin/env python3
"""Diagnose why nutrition data is mostly missing in the feature matrix."""
import pandas as pd
import numpy as np

nutr = pd.read_csv('data/processed/unified_nutrition.csv')
nutr['date'] = pd.to_datetime(nutr['date'])

print('=== NUTRITION DATA OVERVIEW ===')
print(f'Total rows: {len(nutr)}')
print(f'Unique dates: {nutr.date.dt.normalize().nunique()}')
print(f'Date range: {nutr.date.min().date()} to {nutr.date.max().date()}')
print(f'\nAll columns ({len(nutr.columns)}): {list(nutr.columns)}')

# Nutrient columns
nutr_cols = ['calories', 'protein', 'carbs', 'fat', 'fiber', 'sodium', 'potassium',
             'calcium', 'phosphorus', 'iron', 'sugar', 'cholesterol']

print('\n=== NUTRIENT COLUMN FILL RATES ===')
for c in nutr_cols:
    if c in nutr.columns:
        vals = pd.to_numeric(nutr[c], errors='coerce')
        n_valid = vals.notna().sum()
        n_nonzero = (vals > 0).sum()
        print(f'  {c:15s}: {n_valid:5d} non-null ({100*n_valid/len(nutr):.1f}%), '
              f'{n_nonzero:5d} > 0 ({100*n_nonzero/len(nutr):.1f}%)')
    else:
        print(f'  {c:15s}: *** COLUMN NOT FOUND ***')

# Text columns
text_cols = [c for c in nutr.columns if nutr[c].dtype == 'object']
print(f'\n=== TEXT/STRING COLUMNS: {text_cols} ===')
for c in text_cols[:6]:
    unique_ct = nutr[c].nunique()
    print(f'\n  {c} ({unique_ct} unique values):')
    samples = nutr[c].dropna().head(15).tolist()
    for s in samples:
        print(f'    "{s}"')

# Rows with vs without nutrient breakdowns
has_nutrient = nutr[nutr_cols].apply(pd.to_numeric, errors='coerce').notna().any(axis=1)
print(f'\n=== ROWS WITH vs WITHOUT NUTRIENT BREAKDOWN ===')
print(f'Rows WITH at least 1 nutrient value:  {has_nutrient.sum():5d} ({100*has_nutrient.mean():.1f}%)')
print(f'Rows WITHOUT any nutrient values:     {(~has_nutrient).sum():5d} ({100*(~has_nutrient).mean():.1f}%)')

# Dates with vs without
dates_with = nutr[has_nutrient]['date'].dt.normalize().nunique()
dates_without = nutr[~has_nutrient]['date'].dt.normalize().nunique()
print(f'\nUnique dates with nutrient data:    {dates_with}')
print(f'Unique dates without nutrient data: {dates_without}')

# Sample rows WITHOUT nutrients (just food names?)
print('\n=== SAMPLE ROWS WITHOUT NUTRIENT BREAKDOWN ===')
no_nutr = nutr[~has_nutrient]
print(no_nutr.head(20).to_string())

# Sample rows WITH nutrients
print('\n=== SAMPLE ROWS WITH NUTRIENT BREAKDOWN ===')
with_nutr = nutr[has_nutrient]
print(with_nutr.head(10).to_string())

# Now check overlap with dialysis sessions
sessions = pd.read_csv('data/processed/dialysis_sessions.csv', low_memory=False)
sessions['session_date'] = pd.to_datetime(sessions['session_date'])
sess_dates = set(sessions['session_date'].dt.normalize().dt.date)

nutr_dates_with_nutrients = set(nutr[has_nutrient]['date'].dt.normalize().dt.date)
nutr_dates_all = set(nutr['date'].dt.normalize().dt.date)

overlap_all = sess_dates & nutr_dates_all
overlap_nutrients = sess_dates & nutr_dates_with_nutrients

print(f'\n=== OVERLAP WITH DIALYSIS SESSIONS ===')
print(f'Total session dates:                       {len(sess_dates)}')
print(f'Session dates with ANY nutrition log:       {len(overlap_all)}')
print(f'Session dates with NUTRIENT BREAKDOWN:      {len(overlap_nutrients)}')
print(f'That is why only ~{100*len(overlap_nutrients)/len(sess_dates):.1f}% of sessions have nutrition features')

# Check date distribution of rows WITH nutrients
if has_nutrient.sum() > 0:
    print('\n=== DATE RANGE OF ROWS WITH NUTRIENT BREAKDOWN ===')
    dates_with_nutr = nutr[has_nutrient]['date'].dt.normalize()
    print(f'  Range: {dates_with_nutr.min().date()} to {dates_with_nutr.max().date()}')
    print(f'  Year distribution:')
    print(dates_with_nutr.dt.year.value_counts().sort_index().to_string())

# Check if food_name/description exists but nutrients are missing
food_cols = [c for c in nutr.columns if any(kw in c.lower() for kw in ['food', 'item', 'name', 'description', 'meal'])]
print(f'\n=== FOOD/ITEM/DESCRIPTION COLUMNS: {food_cols} ===')
if food_cols:
    for fc in food_cols:
        has_food_no_nutr = nutr[fc].notna() & ~has_nutrient
        print(f'\n  {fc}: {has_food_no_nutr.sum()} rows have food name but NO nutrient breakdown')
        if has_food_no_nutr.sum() > 0:
            print('  Sample food entries WITHOUT nutrient data:')
            for val in nutr.loc[has_food_no_nutr, fc].head(20).tolist():
                print(f'    - "{val}"')
