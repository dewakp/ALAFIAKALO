#!/usr/bin/env python3
"""
Convert early flowsheet data (Machine sheet, 2016-2017) to match
the standardized flowsheet_sessions.csv format so we get continuous
dialysis data from April 2016 → Feb 2026.

Input:  data/raw/excel/records_machine.csv (pivot format: date, metric, value)
Output: data/raw/excel/early_flowsheet_sessions.csv
"""

import pandas as pd
import numpy as np
import os
import re
from pathlib import Path

BASE = str(Path(__file__).resolve().parent.parent)
SRC = os.path.join(BASE, "data/raw/excel/records_machine.csv")
OUT_DIR = os.path.join(BASE, "data/raw/excel")

df = pd.read_csv(SRC)
print(f"Source: {len(df)} records, {df['date'].nunique()} dates")

# Pivot to wide format: one row per date, columns = metrics
wide = df.pivot_table(index='date', columns='metric', values='value', aggfunc='first')
wide = wide.reset_index()
print(f"Pivoted: {len(wide)} sessions x {len(wide.columns)} columns")

# Parse BP strings (format "120/80")
def parse_bp(bp_str, part):
    """Extract systolic or diastolic from 'sys/dia' string."""
    if pd.isna(bp_str) or not isinstance(bp_str, str):
        return np.nan
    bp_str = bp_str.strip()
    m = re.match(r'(\d+)\s*/\s*(\d+)', bp_str)
    if m:
        return float(m.group(1)) if part == 'sys' else float(m.group(2))
    return np.nan

# Build standardized session dataframe
sessions = pd.DataFrame()
sessions['session_date'] = pd.to_datetime(wide['date'])

# Weights
sessions['weight_pre_kg'] = pd.to_numeric(wide.get('Weight Pre'), errors='coerce')
sessions['weight_post_kg'] = pd.to_numeric(wide.get('Weight Post'), errors='coerce')
wl = pd.to_numeric(wide.get('Weight Loss'), errors='coerce')
wg = pd.to_numeric(wide.get('Weight Gain (BT)'), errors='coerce')

# Fix formula artifacts: Weight Loss or Gain(BT) that are negative and close
# to a body weight (< -30) are formula errors (=0 - PostWeight), not real values.
wl_bad = wl.notna() & (wl < -30)
wl.loc[wl_bad] = np.nan
wg_bad = wg.notna() & (wg < -30)
wg.loc[wg_bad] = np.nan

# Also treat Weight Loss == 0 with no Pre/Post as truly missing
wl_zero_empty = (wl == 0) & sessions['weight_pre_kg'].isna() & sessions['weight_post_kg'].isna()
wl.loc[wl_zero_empty] = np.nan

# Calculate weight_loss_kg: prefer Pre-Post, fall back to Weight Loss column
sessions['weight_loss_kg'] = sessions['weight_pre_kg'] - sessions['weight_post_kg']
mask = sessions['weight_loss_kg'].isna() & wl.notna()
sessions.loc[mask, 'weight_loss_kg'] = wl[mask]

# Recover missing Pre or Post from the other + Weight Loss
recover_pre = sessions['weight_pre_kg'].isna() & sessions['weight_post_kg'].notna() & wl.notna()
sessions.loc[recover_pre, 'weight_pre_kg'] = sessions.loc[recover_pre, 'weight_post_kg'] + wl[recover_pre]

recover_post = sessions['weight_post_kg'].isna() & sessions['weight_pre_kg'].notna() & wl.notna()
sessions.loc[recover_post, 'weight_post_kg'] = sessions.loc[recover_post, 'weight_pre_kg'] - wl[recover_post]

print(f"  Weight recovery: {recover_pre.sum()} Pre, {recover_post.sum()} Post recovered from Loss column")

# Pre BP
if 'Pre BP Sitting' in wide.columns:
    sessions['bp_pre_sys'] = wide['Pre BP Sitting'].apply(lambda x: parse_bp(x, 'sys'))
    sessions['bp_pre_dia'] = wide['Pre BP Sitting'].apply(lambda x: parse_bp(x, 'dia'))

# Post BP
if 'Post BP Sitting' in wide.columns:
    sessions['bp_post_sys'] = wide['Post BP Sitting'].apply(lambda x: parse_bp(x, 'sys'))
    sessions['bp_post_dia'] = wide['Post BP Sitting'].apply(lambda x: parse_bp(x, 'dia'))

# Lowest BP
if 'Lowest BP' in wide.columns:
    sessions['bp_lowest_sys'] = wide['Lowest BP'].apply(lambda x: parse_bp(x, 'sys'))
    sessions['bp_lowest_dia'] = wide['Lowest BP'].apply(lambda x: parse_bp(x, 'dia'))

# Duration
sessions['duration_mins'] = pd.to_numeric(wide.get('Duration'), errors='coerce')
# Also try Treatment Length
tl = pd.to_numeric(wide.get('Treatment Length'), errors='coerce')
mask = sessions['duration_mins'].isna() & tl.notna()
sessions.loc[mask, 'duration_mins'] = tl[mask]

# Kt/V
sessions['ktv_actual'] = pd.to_numeric(wide.get('Actual Kt/V'), errors='coerce')
sessions['ktv_target'] = pd.to_numeric(wide.get('Target Kt/V'), errors='coerce')
sessions['ktv_spk'] = pd.to_numeric(wide.get('spKdt/V Dialysis'), errors='coerce')
sessions['ktv_ek'] = pd.to_numeric(wide.get('eKdt/V Dialysis'), errors='coerce')

# BUN
sessions['bun_pre'] = pd.to_numeric(wide.get('BUN Pre'), errors='coerce')
sessions['bun_post'] = pd.to_numeric(wide.get('BUN Post'), errors='coerce')
sessions['urr'] = pd.to_numeric(wide.get('URR'), errors='coerce')

# Pulse
sessions['pulse_pre'] = pd.to_numeric(wide.get('Pulse Pre'), errors='coerce')
sessions['pulse_post'] = pd.to_numeric(wide.get('Pulse Post'), errors='coerce')

# Machine settings
sessions['blood_flow'] = pd.to_numeric(wide.get('Blood Flow'), errors='coerce')
sessions['dialysate_flow'] = pd.to_numeric(wide.get('Dializer State Flow'), errors='coerce')
sessions['bath_ca'] = pd.to_numeric(wide.get('Bath CA'), errors='coerce')
sessions['bath_k'] = pd.to_numeric(wide.get('Bath K'), errors='coerce')
sessions['bath_na'] = pd.to_numeric(wide.get('Bath Na'), errors='coerce')
sessions['machine_temp'] = pd.to_numeric(wide.get('Machine Temp'), errors='coerce')
sessions['conductivity'] = pd.to_numeric(wide.get('Machine Conductivity'), errors='coerce')
sessions['manual_ph'] = pd.to_numeric(wide.get('Manual PH'), errors='coerce')

# Metadata
sessions['facility'] = wide.get('Facility')
sessions['physician'] = wide.get('Physician')
sessions['technician'] = wide.get('Technician')
sessions['machine_make'] = wide.get('Machine Make')
sessions['machine_model'] = wide.get('Machine Model')
sessions['machine_series'] = wide.get('Machine Series')

# nPCR
sessions['npcr'] = pd.to_numeric(wide.get('nPCR'), errors='coerce')

# Weight gain between treatments (use cleaned wg)
sessions['weight_gain_bt'] = wg

# Clean impossible values (same thresholds as parse_flowsheets.py)
for col in ['bp_pre_sys', 'bp_post_sys', 'bp_lowest_sys']:
    if col in sessions.columns:
        sessions.loc[sessions[col] < 45, col] = np.nan
        sessions.loc[sessions[col] > 250, col] = np.nan

for col in ['bp_pre_dia', 'bp_post_dia', 'bp_lowest_dia']:
    if col in sessions.columns:
        sessions.loc[sessions[col] < 20, col] = np.nan
        sessions.loc[sessions[col] > 200, col] = np.nan

for col in ['weight_pre_kg', 'weight_post_kg']:
    if col in sessions.columns:
        sessions.loc[sessions[col] < 30, col] = np.nan

sessions['source'] = 'Records_Machine'

# Sort by date
sessions = sessions.sort_values('session_date').reset_index(drop=True)

# Save
out_path = os.path.join(OUT_DIR, "early_flowsheet_sessions.csv")
sessions.to_csv(out_path, index=False)

# Rename original if it still exists
raw_src = os.path.join(OUT_DIR, "records_machine.csv")
raw_dst = os.path.join(OUT_DIR, "records_early_flowsheets_raw.csv")
if os.path.exists(raw_src) and not os.path.exists(raw_dst):
    os.rename(raw_src, raw_dst)

# Summary
print(f"\n=== EARLY FLOWSHEET SESSIONS ===")
print(f"  Sessions: {len(sessions)}")
print(f"  Date range: {sessions['session_date'].min().date()} to {sessions['session_date'].max().date()}")
has_pre = sessions['weight_pre_kg'].notna().sum()
has_bp = sessions['bp_pre_sys'].notna().sum()
has_dur = sessions['duration_mins'].notna().sum()
has_ktv = sessions['ktv_actual'].notna().sum()
print(f"  With pre-weight: {has_pre}")
print(f"  With pre-BP: {has_bp}")
print(f"  With duration: {has_dur}")
print(f"  With Kt/V: {has_ktv}")
print(f"  Saved to {out_path}")

# Check overlap with existing flowsheet_sessions.csv
try:
    fs = pd.read_csv(os.path.join(OUT_DIR, "flowsheet_sessions.csv"), parse_dates=['session_date'])
    fs_min = fs['session_date'].min().date()
    fs_max = fs['session_date'].max().date()
    early_max = sessions['session_date'].max().date()
    overlap = sessions[sessions['session_date'].dt.date >= fs_min]
    print(f"\n  Standard flowsheets: {fs_min} to {fs_max} ({len(fs)} sessions)")
    print(f"  Overlap dates: {len(overlap)} early sessions on/after {fs_min}")
    print(f"  Combined: {sessions['session_date'].min().date()} to {fs_max} = continuous timeline")
except Exception as e:
    print(f"\n  Could not check overlap: {e}")
