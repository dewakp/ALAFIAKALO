#!/usr/bin/env python3
"""Investigate implicit post-dialysis labs using domain rules.

Rules from patient/clinician:
1. When a date has >1 BUN or Creatinine, the LOWER value is always POST
2. Creatinine <= 3.5 AND BUN < 30 on a given date → POST
   (if lab was collected < 12 hrs after dialysis end time)
3. BUN POST and Creatinine POST are almost always collected together
"""
import pandas as pd
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

labs = pd.read_csv(os.path.join(data_dir, 'processed', 'unified_labs.csv'))
labs['date'] = pd.to_datetime(labs['date'])
labs['value_numeric'] = pd.to_numeric(labs['value_numeric'], errors='coerce')

sess = pd.read_csv(os.path.join(data_dir, 'processed', 'dialysis_sessions.csv'))
sess['session_date'] = pd.to_datetime(sess['session_date'])

# ── Rule 1: Multiple BUN or Creatinine on same date ──
print("═══ RULE 1: Multiple values on same date → lower = POST ═══\n")

# BUN variants (excluding explicitly labeled POST)
bun_names = ['BUN', 'B.U.N.', 'BUN -POST', 'BUN - Post']
bun_pre_names = [n for n in bun_names if 'POST' not in n.upper() and 'Post' not in n]
bun_post_names = [n for n in bun_names if 'POST' in n.upper() or 'Post' in n]

bun_all = labs[labs.test_name.isin(bun_names)].copy()
print(f"BUN test names found: {bun_all.test_name.unique().tolist()}")
print(f"Total BUN rows: {len(bun_all)}")

# Count dates with multiple BUN values
bun_per_date = bun_all.groupby('date').agg(
    count=('value_numeric', 'count'),
    values=('value_numeric', list),
    names=('test_name', list)
).reset_index()

multi_bun = bun_per_date[bun_per_date['count'] > 1]
print(f"Dates with >1 BUN: {len(multi_bun)}")
if len(multi_bun) > 0:
    for _, row in multi_bun.head(10).iterrows():
        vals = [v for v in row['values'] if pd.notna(v)]
        names = row['names']
        print(f"  {row['date'].date()}  values={vals}  names={names}")

# Creatinine variants
creat_names_raw = labs[labs.test_name.str.contains('Creat|creat|CREAT', na=False)].test_name.unique()
print(f"\nCreatinine test names found: {creat_names_raw.tolist()}")

creat_all_names = [n for n in creat_names_raw if 'ratio' not in n.lower() and 'clear' not in n.lower()]
creat_pre_names = [n for n in creat_all_names if 'POST' not in n.upper() and 'Post' not in n]
creat_post_names = [n for n in creat_all_names if 'POST' in n.upper() or 'Post' in n]
print(f"  Pre names: {creat_pre_names}")
print(f"  Post names: {creat_post_names}")

creat_all = labs[labs.test_name.isin(creat_all_names)].copy()
print(f"Total Creatinine rows: {len(creat_all)}")

creat_per_date = creat_all.groupby('date').agg(
    count=('value_numeric', 'count'),
    values=('value_numeric', list),
    names=('test_name', list)
).reset_index()

multi_creat = creat_per_date[creat_per_date['count'] > 1]
print(f"Dates with >1 Creatinine: {len(multi_creat)}")
if len(multi_creat) > 0:
    for _, row in multi_creat.head(10).iterrows():
        vals = [v for v in row['values'] if pd.notna(v)]
        names = row['names']
        print(f"  {row['date'].date()}  values={vals}  names={names}")

# ── Rule 2: Low Creatinine + Low BUN = POST ──
print("\n═══ RULE 2: Creatinine <= 3.5 AND BUN < 30 → likely POST ═══\n")

# Get all BUN and Creatinine values per date
bun_vals = bun_all.groupby('date')['value_numeric'].apply(list).to_dict()
creat_vals = creat_all.groupby('date')['value_numeric'].apply(list).to_dict()

low_creat_bun_dates = []
for d in set(bun_vals.keys()) | set(creat_vals.keys()):
    b_list = [v for v in bun_vals.get(d, []) if pd.notna(v)]
    c_list = [v for v in creat_vals.get(d, []) if pd.notna(v)]
    
    for bv in b_list:
        for cv in c_list:
            if cv <= 3.5 and bv < 30:
                low_creat_bun_dates.append({
                    'date': d, 'bun': bv, 'creatinine': cv,
                    'is_dialysis_day': d in set(sess.session_date)
                })

low_df = pd.DataFrame(low_creat_bun_dates)
if len(low_df) > 0:
    print(f"Dates with Creatinine<=3.5 AND BUN<30: {len(low_df)}")
    print(f"  Of those, on dialysis days: {low_df.is_dialysis_day.sum()}")
    print(f"\n  Sample:")
    for _, row in low_df.head(15).iterrows():
        print(f"    {row['date'].date()}  BUN={row['bun']:.0f}  Creat={row['creatinine']:.1f}  dialysis_day={row['is_dialysis_day']}")
else:
    print("No dates matched the low-value rule")

# ── Summary: How many POST values can we infer? ──
print("\n═══ SUMMARY: Implicit POST detection ═══\n")

# Explicitly labeled POST
explicit_bun_post = labs[labs.test_name.isin(bun_post_names)]
explicit_creat_post = labs[labs.test_name.isin(creat_post_names)]
print(f"Explicitly labeled POST:")
print(f"  BUN POST:        {len(explicit_bun_post)} rows, {explicit_bun_post.date.nunique()} unique dates")
print(f"  Creatinine POST: {len(explicit_creat_post)} rows, {explicit_creat_post.date.nunique()} unique dates")

# From Rule 1: multi-value dates where lower = POST
inferred_r1_bun = 0
inferred_r1_creat = 0
for _, row in multi_bun.iterrows():
    vals = [v for v in row['values'] if pd.notna(v)]
    names = row['names']
    # Only count if not already has an explicit POST label
    if not any('POST' in n.upper() or 'Post' in n for n in names):
        inferred_r1_bun += 1

for _, row in multi_creat.iterrows():
    vals = [v for v in row['values'] if pd.notna(v)]
    names = row['names']
    if not any('POST' in n.upper() or 'Post' in n for n in names):
        inferred_r1_creat += 1

print(f"\nRule 1 (lower of multiples = POST, excluding already-labeled):")
print(f"  BUN:        {inferred_r1_bun} new POST dates")
print(f"  Creatinine: {inferred_r1_creat} new POST dates")

# From Rule 2: low values on dialysis days
if len(low_df) > 0:
    # Exclude dates that already have explicit POST labels
    explicit_post_dates = set(explicit_bun_post.date) | set(explicit_creat_post.date)
    r2_new = low_df[~low_df.date.isin(explicit_post_dates) & low_df.is_dialysis_day]
    print(f"\nRule 2 (Creat<=3.5 & BUN<30 on dialysis days, excluding already-labeled):")
    print(f"  New POST dates: {len(r2_new)}")

# ── Check dialysis end times for Rule 2 validation ──
print("\n═══ Dialysis end times check ═══\n")
time_cols = [c for c in sess.columns if 'time' in c.lower() or 'end' in c.lower()]
print(f"Session time columns: {time_cols}")
for col in ['treatment_end', 'total_time', 'total_machine_time']:
    if col in sess.columns:
        n = sess[col].notna().sum()
        print(f"  {col}: {n} non-null")
        if n > 0:
            print(f"    Sample: {sess[col].dropna().head(5).tolist()}")

# ── Also check: do ALL dates with explicit POST also have a PRE? ──
print("\n═══ PRE/POST pairing check ═══\n")
# For same-date matching
bun_dates_by_type = {}
for name in bun_names:
    dates = set(labs[labs.test_name == name].date)
    if dates:
        bun_dates_by_type[name] = dates
        print(f"  {name:20s}  {len(dates)} dates")

creat_dates_by_type = {}
for name in creat_all_names:
    dates = set(labs[labs.test_name == name].date)
    if dates:
        creat_dates_by_type[name] = dates
        print(f"  {name:20s}  {len(dates)} dates")

# Check: other analytes that may also follow same POST pattern
print("\n═══ Other analytes with similar multi-value patterns ═══\n")
for test_group, pattern in [
    ('PTH', 'PTH|pth'),
    ('Calcium', 'Calcium|calcium|CALCIUM'),
    ('Phosphorus', 'Phosphor|phosphor|PHOSPHOR'),
    ('CO2', 'CO2|co2|Bicarb'),
    ('Potassium', 'Potassium|potassium|POTASSIUM'),
]:
    subset = labs[labs.test_name.str.contains(pattern, na=False, case=False)]
    subset = subset[~subset.test_name.str.contains('ratio|clear|correc', na=False, case=False)]
    per_date = subset.groupby('date').agg(count=('value_numeric', 'count')).reset_index()
    multi = per_date[per_date['count'] > 1]
    if len(multi) > 0:
        print(f"  {test_group:15s}  {len(multi)} dates with >1 value  (names: {subset.test_name.unique().tolist()})")
    else:
        print(f"  {test_group:15s}  no multi-value dates")
