#!/usr/bin/env python3
"""Deep-dive: Kaiser labs on dialysis days/next-day for POST identification.

Rule 4: Home dialysis + Kaiser lab same/next day → POST
Source is the proxy for facility:
  records_xlsx = Kaiser records → lab at Kaiser
  pdf_davita = DaVita lab reports
Most sessions have "unknown" facility = home dialysis.
"""
import pandas as pd
import numpy as np
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

labs = pd.read_csv(os.path.join(data_dir, 'processed', 'unified_labs.csv'))
labs['date'] = pd.to_datetime(labs['date'])
labs['value_numeric'] = pd.to_numeric(labs['value_numeric'], errors='coerce')

sess = pd.read_csv(os.path.join(data_dir, 'processed', 'dialysis_sessions.csv'))
sess['session_date'] = pd.to_datetime(sess['session_date'])

# ── 1. Session columns with time info ──
print("═══ SESSION COLUMNS ═══\n")
print(f"Columns: {list(sess.columns)}")
print()

# Check for start/end time columns more broadly
for col in sess.columns:
    valid = sess[col].dropna()
    if len(valid) > 0:
        sample = valid.head(3).tolist()
        # Show columns that might contain time info
        if any(':' in str(s) for s in sample) or col in ['total_time', 'treatment_start', 'treatment_end']:
            print(f"  {col} (N={len(valid)}): {sample[:5]}")

# Check if flowsheet sessions have start_time or end_time
print("\n═══ FLOWSHEET SESSION TIME COLUMNS ═══")
flow_sess = sess[sess.source == 'flowsheet']
print(f"\nFlowsheet sessions: {len(flow_sess)}")
for col in flow_sess.columns:
    valid = flow_sess[col].dropna()
    if len(valid) > 0 and len(valid) < len(flow_sess):
        sample = valid.head(3).tolist()
        print(f"  {col} (N={len(valid)}/{len(flow_sess)}): {sample[:3]}")
    elif len(valid) == len(flow_sess):
        sample = valid.head(3).tolist()
        print(f"  {col} (N=ALL): {sample[:3]}")

# ── 2. Identify Home/DaVita sessions ──
print("\n\n═══ HOME / DAVITA SESSIONS ═══\n")
# Consider "unknown" as home dialysis (patient does HHD)
home_mask = sess.facility.isna() | (sess.facility == 'unknown') | \
            sess.facility.str.contains('Davita|davita|home|Home', na=False, case=False)
home_sess = sess[home_mask].copy()
print(f"Home/DaVita/Unknown sessions: {len(home_sess)}")
print(f"  Facility breakdown:")
print(home_sess.facility.value_counts(dropna=False).to_string())

home_dates = set(home_sess.session_date)
home_next_dates = {d + pd.Timedelta(days=1) for d in home_dates}
print(f"\nUnique home dates: {len(home_dates)}")
print(f"Next-day dates: {len(home_next_dates)}")

# ── 3. Kaiser labs (source=records_xlsx) on home-dialysis dates ──
print("\n═══ KAISER LABS ON HOME DIALYSIS DATES ═══\n")

kaiser_mask = (labs.source == 'records_xlsx') | \
              labs.lab_name.str.contains('Kaiser', na=False, case=False)
kaiser_labs = labs[kaiser_mask].copy()
print(f"Total Kaiser labs: {len(kaiser_labs)}")

# Same-day
kaiser_same = kaiser_labs[kaiser_labs.date.isin(home_dates)]
same_dates = sorted(kaiser_same.date.unique())
print(f"\nKaiser labs on home dialysis days: {len(kaiser_same)} rows, {len(same_dates)} dates")

# Next-day
kaiser_next = kaiser_labs[kaiser_labs.date.isin(home_next_dates) & ~kaiser_labs.date.isin(home_dates)]
next_dates = sorted(kaiser_next.date.unique())
print(f"Kaiser labs day after home dialysis (not also on dialysis day): {len(kaiser_next)} rows, {len(next_dates)} dates")

# ── 4. Show date breakdown ──
print("\n═══ SAME-DAY KAISER LABS (by date) ═══\n")
for d in same_dates[:30]:
    rows = kaiser_same[kaiser_same.date == d]
    tests = rows.test_name.tolist()
    # Check if already marked POST
    has_post = any('POST' in str(t).upper() or 'post' in str(t).lower() for t in tests)
    flag = " [has POST-marked]" if has_post else ""
    print(f"  {d.date()}: {len(rows)} tests{flag}")
    for t in tests[:10]:
        v = rows[rows.test_name == t].value_numeric.values
        print(f"    {t}: {v}")

print(f"\n  ... showing {min(30, len(same_dates))}/{len(same_dates)} dates")

print("\n═══ NEXT-DAY KAISER LABS (by date) ═══\n")
for d in next_dates[:20]:
    rows = kaiser_next[kaiser_next.date == d]
    tests = rows.test_name.tolist()
    has_post = any('POST' in str(t).upper() or 'post' in str(t).lower() for t in tests)
    flag = " [has POST-marked]" if has_post else ""
    # Find the dialysis date
    dial_d = d - pd.Timedelta(days=1)
    print(f"  {d.date()} (dialysis: {dial_d.date()}): {len(rows)} tests{flag}")
    for t in tests[:8]:
        v = rows[rows.test_name == t].value_numeric.values
        print(f"    {t}: {v}")

print(f"\n  ... showing {min(20, len(next_dates))}/{len(next_dates)} dates")

# ── 5. Overlap analysis with existing POST assignments ──
print("\n═══ OVERLAP WITH EXISTING POST ASSIGNMENTS ═══\n")
existing_post = pd.read_csv(os.path.join(data_dir, 'features', 'post_dialysis_labs.csv'))
existing_post['date'] = pd.to_datetime(existing_post['date'])
print(f"Existing POST records: {len(existing_post)}")

new_same_day_dates = set(pd.Timestamp(d) for d in same_dates)
new_next_day_dates = set(pd.Timestamp(d) for d in next_dates)
existing_dates = set(existing_post.date)

overlap_same = new_same_day_dates & existing_dates
overlap_next = new_next_day_dates & existing_dates
new_only = (new_same_day_dates | new_next_day_dates) - existing_dates

print(f"Same-day dates already in POST: {len(overlap_same)}")
print(f"Next-day dates already in POST: {len(overlap_next)}")
print(f"NEW dates not in existing POST: {len(new_only)}")

# ── 6. Analyte breakdown for Rule 4 candidates ──
print("\n═══ ANALYTE BREAKDOWN FOR RULE 4 CANDIDATES ═══\n")
rule4_labs = pd.concat([kaiser_same, kaiser_next])
print(f"Total Rule 4 candidate lab rows: {len(rule4_labs)}")
print("\nTest name distribution:")
test_counts = rule4_labs.test_name.value_counts()
for t, n in test_counts.head(25).items():
    print(f"  {t:40s}  N={n}")

# ── 7. Time delta concept ──
print("\n═══ TIME DELTA FEATURE ═══\n")
print("For time delta: lab date - dialysis session date")
print("We have total_time (minutes) for sessions but no lab collection time")
print("Available proxy: date_delta = 0 (same day) or 1 (next day)")
print("\nWith total_time, we can estimate:")
print("  If session total_time=240min (4hrs) and most sessions end pm/evening,")
print("  next-day Kaiser lab is ~12-18 hrs post-dialysis")
print("  same-day Kaiser lab could be 2-8 hrs post-dialysis")

# Session total_time stats
valid_tt = sess[sess.total_time.notna()].total_time
print(f"\nSession total_time (minutes):")
print(f"  mean: {valid_tt.mean():.1f}")
print(f"  median: {valid_tt.median():.1f}")
print(f"  range: {valid_tt.min():.0f} - {valid_tt.max():.0f}")
print(f"  N valid: {len(valid_tt)} / {len(sess)}")

# For same-day Kaiser labs, merge with session to get total_time
merged = kaiser_same.merge(home_sess[['session_date', 'total_time']], 
                            left_on='date', right_on='session_date', how='left')
print(f"\nSame-day Kaiser labs with session total_time: {merged.total_time.notna().sum()}/{len(merged)}")

# For next-day Kaiser labs
merged_next = kaiser_next.copy()
merged_next['dialysis_date'] = merged_next.date - pd.Timedelta(days=1)
merged_next = merged_next.merge(home_sess[['session_date', 'total_time']], 
                                 left_on='dialysis_date', right_on='session_date', how='left')
print(f"Next-day Kaiser labs with session total_time: {merged_next.total_time.notna().sum()}/{len(merged_next)}")
