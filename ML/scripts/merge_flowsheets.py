#!/usr/bin/env python3
"""
Merge early flowsheet sessions (Machine sheet, 2016-2017) with
standard flowsheet sessions (2017-2026) into one unified file.

Maps early column names to standard names, deduplicates overlapping dates.
"""
import pandas as pd
import numpy as np
import os
from pathlib import Path

BASE = str(Path(__file__).resolve().parent.parent / "data" / "raw" / "excel")

# Load both
early = pd.read_csv(os.path.join(BASE, "early_flowsheet_sessions.csv"), parse_dates=['session_date'])
standard = pd.read_csv(os.path.join(BASE, "flowsheet_sessions.csv"))
if 'date' in standard.columns and 'session_date' not in standard.columns:
    standard = standard.rename(columns={'date': 'session_date'})
standard['session_date'] = pd.to_datetime(standard['session_date'])

print(f"Early:    {len(early)} sessions, {early['session_date'].min().date()} to {early['session_date'].max().date()}")
print(f"Standard: {len(standard)} sessions, {standard['session_date'].min().date()} to {standard['session_date'].max().date()}")

# Rename early columns to match standard naming
early_renamed = early.rename(columns={
    'weight_pre_kg': 'today_weight_kg',
    'weight_post_kg': 'post_weight_kg',
    'bp_pre_sys': 'pre_bp_sys',
    'bp_pre_dia': 'pre_bp_dia',
    'bp_post_sys': 'post_bp_sys',
    'bp_post_dia': 'post_bp_dia',
    'duration_mins': 'total_time',
    'pulse_pre': 'pre_pulse',
    'pulse_post': 'post_pulse',
    'blood_flow': 'avg_blood_flow_rate',
    'dialysate_flow': 'avg_dialysate_rate',
    'machine_temp': 'pre_temp',
    'source': 'source_file',
})

# Add format marker
early_renamed['format'] = 'early'

# Concat
combined = pd.concat([early_renamed, standard], ignore_index=True)

# Sort by date
combined = combined.sort_values('session_date').reset_index(drop=True)

# Dedup: for same date, prefer standard over early (standard has more detail)
combined['_is_standard'] = combined['format'] != 'early'
combined = combined.sort_values(['session_date', '_is_standard'], ascending=[True, False])
n_before = len(combined)
combined = combined.drop_duplicates(subset='session_date', keep='first')
n_dupes = n_before - len(combined)
combined = combined.drop(columns=['_is_standard'])
combined = combined.sort_values('session_date').reset_index(drop=True)

print(f"\nAfter merge: {len(combined)} sessions ({n_dupes} overlapping dates removed, kept standard)")
print(f"Date range: {combined['session_date'].min().date()} to {combined['session_date'].max().date()}")

# Count by source
early_count = (combined['format'] == 'early').sum()
std_count = (combined['format'] != 'early').sum()
print(f"  Early (2016-2017): {early_count}")
print(f"  Standard (2017-2026): {std_count}")

# Year breakdown
combined['year'] = combined['session_date'].dt.year
year_counts = combined.groupby('year').size()
print(f"\nSessions by year:")
for year, count in year_counts.items():
    print(f"  {year}: {count}")

# Save merged file
out = os.path.join(BASE, "all_flowsheet_sessions.csv")
combined.drop(columns=['year'], inplace=True)
combined.to_csv(out, index=False)
print(f"\nSaved {len(combined)} sessions to {out}")
print(f"File size: {os.path.getsize(out)/1024:.0f} KB")

# Also check readings coverage
readings = pd.read_csv(os.path.join(BASE, "flowsheet_readings.csv"))
print(f"\nFlowsheet readings: {len(readings)} (unchanged, no intra-session readings for early period)")
