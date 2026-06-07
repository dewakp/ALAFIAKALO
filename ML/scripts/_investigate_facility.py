#!/usr/bin/env python3
"""Investigate facility-based POST lab identification.

Rule 4 (from patient):
  Dialysis at Home/DaVita + Lab at Kaiser on same day or <24hrs later
  → ALL lab data on that date is POST
  Include time delta as a feature.
"""
import pandas as pd
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

labs = pd.read_csv(os.path.join(data_dir, 'processed', 'unified_labs.csv'))
labs['date'] = pd.to_datetime(labs['date'])
labs['value_numeric'] = pd.to_numeric(labs['value_numeric'], errors='coerce')

sess = pd.read_csv(os.path.join(data_dir, 'processed', 'dialysis_sessions.csv'))
sess['session_date'] = pd.to_datetime(sess['session_date'])

# ── 1. Check facility columns ──
print("═══ FACILITY DATA IN LABS ═══\n")
for col in ['facility', 'lab_name', 'source', 'source_file']:
    if col in labs.columns:
        vals = labs[col].dropna().unique()
        print(f"{col}: {len(vals)} unique values")
        for v in sorted(vals)[:20]:
            n = (labs[col] == v).sum()
            print(f"  {str(v):50s}  N={n}")
        print()

print("\n═══ FACILITY DATA IN SESSIONS ═══\n")
for col in ['facility', 'source', 'source_file']:
    if col in sess.columns:
        vals = sess[col].dropna().unique()
        print(f"{col}: {len(vals)} unique values")
        for v in sorted(vals)[:20]:
            n = (sess[col] == v).sum()
            print(f"  {str(v):50s}  N={n}")
        print()

# ── 2. Check time columns ──
print("\n═══ TIME DATA IN LABS ═══\n")
time_cols = [c for c in labs.columns if 'time' in c.lower()]
print(f"Time columns: {time_cols}")
# Any column that might have time info
for col in labs.columns:
    sample = labs[col].dropna().head(5).tolist()
    if any(':' in str(s) for s in sample):
        print(f"  {col}: {sample[:5]}")

print("\n═══ TIME DATA IN SESSIONS ═══\n")
for col in ['treatment_start', 'treatment_end', 'total_time']:
    if col in sess.columns:
        n = sess[col].notna().sum()
        sample = sess[col].dropna().head(10).tolist()
        print(f"{col}: N={n}, samples={sample}")

# ── 3. Cross-reference: same-day labs at Kaiser when dialysis at Home/DaVita ──
print("\n═══ CROSS-REFERENCE: Dialysis facility vs Lab facility ═══\n")

# Dialysis facility
if 'facility' in sess.columns:
    sess_fac = sess[['session_date', 'facility']].copy()
    sess_fac['facility'] = sess_fac['facility'].fillna('unknown')
    print("Session facilities:")
    print(sess_fac.facility.value_counts().to_string())
    print()

    # Labs on dialysis days
    sess_dates = set(sess.session_date)
    labs_on_dialysis_days = labs[labs.date.isin(sess_dates)].copy()
    print(f"Lab records on dialysis days: {len(labs_on_dialysis_days)}")
    
    if 'facility' in labs.columns:
        print("\nLab facilities on dialysis days:")
        print(labs_on_dialysis_days.facility.value_counts(dropna=False).to_string())
    
    if 'lab_name' in labs.columns:
        print("\nLab names on dialysis days:")
        print(labs_on_dialysis_days.lab_name.value_counts(dropna=False).to_string())
    
    if 'source' in labs.columns:
        print("\nLab sources on dialysis days:")
        print(labs_on_dialysis_days.source.value_counts(dropna=False).to_string())
    
    if 'source_file' in labs.columns:
        print("\nLab source files on dialysis days:")
        print(labs_on_dialysis_days.source_file.value_counts(dropna=False).to_string())

# ── 4. Day-after labs ──
print("\n═══ DAY-AFTER LABS (lab date = dialysis date + 1) ═══\n")
next_day_dates = set(sess.session_date + pd.Timedelta(days=1))
labs_next_day = labs[labs.date.isin(next_day_dates)].copy()
print(f"Lab records on day after dialysis: {len(labs_next_day)}")
if 'facility' in labs_next_day.columns:
    print(labs_next_day.facility.value_counts(dropna=False).to_string())
if 'lab_name' in labs_next_day.columns:
    print(labs_next_day.lab_name.value_counts(dropna=False).head(10).to_string())
if 'source' in labs_next_day.columns:
    print(labs_next_day.source.value_counts(dropna=False).to_string())

# ── 5. Specifically: Kaiser labs on Home/DaVita dialysis days ──
print("\n═══ RULE 4 CANDIDATES: Kaiser labs on Home/DaVita dialysis days ═══\n")

if 'facility' in sess.columns and ('facility' in labs.columns or 'lab_name' in labs.columns):
    # Home/DaVita sessions
    home_davita = sess[sess.facility.str.contains('Home|DaVita|Davita|HOME|davita|home', na=False, case=False)]
    hd_dates = set(home_davita.session_date)
    hd_next_dates = set(home_davita.session_date + pd.Timedelta(days=1))
    
    print(f"Home/DaVita session dates: {len(hd_dates)}")
    
    # Kaiser labs on those dates or next day
    lab_fac_col = 'facility' if 'facility' in labs.columns else 'lab_name'
    
    kaiser_same_day = labs[
        labs.date.isin(hd_dates) & 
        labs[lab_fac_col].str.contains('Kaiser|KAISER|kaiser', na=False, case=False)
    ]
    kaiser_next_day = labs[
        labs.date.isin(hd_next_dates) & 
        labs[lab_fac_col].str.contains('Kaiser|KAISER|kaiser', na=False, case=False)
    ]
    
    print(f"Kaiser labs on Home/DaVita dialysis days: {len(kaiser_same_day)} rows, {kaiser_same_day.date.nunique()} dates")
    print(f"Kaiser labs day after Home/DaVita dialysis: {len(kaiser_next_day)} rows, {kaiser_next_day.date.nunique()} dates")
    
    if len(kaiser_same_day) > 0:
        print(f"\nSample Kaiser-on-dialysis-day dates:")
        for d in sorted(kaiser_same_day.date.unique())[:10]:
            tests = kaiser_same_day[kaiser_same_day.date == d].test_name.tolist()
            print(f"  {d.date()}  tests={tests[:8]}...")
    
    if len(kaiser_next_day) > 0:
        print(f"\nSample Kaiser-next-day dates:")
        for d in sorted(kaiser_next_day.date.unique())[:10]:
            tests = kaiser_next_day[kaiser_next_day.date == d].test_name.tolist()
            print(f"  {d.date()}  tests={tests[:8]}...")

# Also check: is clinical_pref or any column indicating Kaiser?
print("\n═══ All unique facility/lab_name values ═══\n")
for col in ['facility', 'lab_name', 'clinical_pref']:
    if col in labs.columns:
        print(f"\n{col}:")
        for v in sorted(labs[col].dropna().unique()):
            print(f"  {v}")
