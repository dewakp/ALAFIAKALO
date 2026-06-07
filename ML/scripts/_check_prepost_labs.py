#!/usr/bin/env python3
"""Quick check for pre/post dialysis lab data."""
import pandas as pd
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

# 1. unified_labs.csv
labs = pd.read_csv(os.path.join(data_dir, 'processed', 'unified_labs.csv'))
print('=== unified_labs.csv ===')
print(f'Shape: {labs.shape}')
print(f'Columns: {list(labs.columns)}')
print()

for col in ['context', 'timing', 'sample_type', 'collection_timing']:
    if col in labs.columns:
        print(f'{col} values: {labs[col].value_counts().to_dict()}')

if 'test_name' in labs.columns:
    # Pre/post in test names
    pre_post = labs[labs.test_name.str.contains('pre|post|Pre|Post|PRE|POST', na=False)]
    if len(pre_post):
        print(f'\nPre/Post test names ({len(pre_post)} rows):')
        for tn in sorted(pre_post.test_name.unique()):
            n = (pre_post.test_name == tn).sum()
            print(f'  {tn:40s}  N={n}')
    
    # Mineral/PTH tests
    mineral = labs[labs.test_name.str.contains('PTH|Potassium|Calcium|Phosph|pth|potassium|calcium|Alk', na=False, case=False)]
    print(f'\nMineral/PTH/ALP tests ({len(mineral)} rows):')
    for tn in sorted(mineral.test_name.unique()):
        n = (mineral.test_name == tn).sum()
        print(f'  {tn:40s}  N={n}')

print('\n=== First 5 rows ===')
print(labs.head().to_string())

# 2. Check what columns the lab_pivot was built from
lab_pivot = pd.read_csv(os.path.join(data_dir, 'features', 'lab_pivot_canonical.csv'))
print(f'\n=== lab_pivot_canonical.csv ===')
print(f'Shape: {lab_pivot.shape}')
# Check for Potassium specifically
for col in ['Potassium', 'K', 'Potassium_pre', 'Potassium_post']:
    if col in lab_pivot.columns:
        n = lab_pivot[col].notna().sum()
        print(f'  {col}: {n} non-null')

# 3. Check raw source files for pre/post labs
raw_dir = os.path.join(data_dir, 'raw')
if os.path.exists(raw_dir):
    for f in os.listdir(raw_dir):
        if 'lab' in f.lower() or 'pre' in f.lower() or 'post' in f.lower():
            fp = os.path.join(raw_dir, f)
            print(f'\nRaw file: {f} ({os.path.getsize(fp)} bytes)')
            if f.endswith('.csv'):
                df = pd.read_csv(fp, nrows=3)
                print(f'  Columns: {list(df.columns)[:20]}')

# 4. BUN pre/post in dialysis sessions 
sess = pd.read_csv(os.path.join(data_dir, 'processed', 'dialysis_sessions.csv'))
for col in ['bun_pre', 'bun_post']:
    if col in sess.columns:
        vals = pd.to_numeric(sess[col], errors='coerce')
        n = vals.notna().sum()
        if n > 0:
            print(f'\n  {col}: N={n}, mean={vals.mean():.1f}, range=[{vals.min():.1f}, {vals.max():.1f}]')
