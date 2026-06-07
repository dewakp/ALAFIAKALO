#!/usr/bin/env python3
"""Deep dive: recover missing Creatinine POST values.

Key finding: BUN POST=169 dates, Creatinine POST=90 dates  
Patient says they're almost always collected together.
So ~79 dates have BUN POST but no explicit Creatinine POST.

Also apply: when multiple Creat on same date, lower = POST.
And: Creat<=3.5 + BUN<30 = POST if on/near dialysis day.
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
sess_dates = set(sess['session_date'])

# ── Dates with explicit BUN POST but NO Creatinine POST ──
bun_post_dates = set(labs[labs.test_name.isin(['BUN -POST', 'BUN - Post'])].date)
creat_post_dates = set(labs[labs.test_name == 'Creatnine POST'].date)

missing_creat_post = bun_post_dates - creat_post_dates
print(f"Dates with BUN POST but NO Creatinine POST: {len(missing_creat_post)}")

# On those dates, is there a Creatinine value at all?
creat_names = ['Creatnine', 'Creatinine', 'CREATININE']
creat_on_missing = labs[labs.date.isin(missing_creat_post) & labs.test_name.isin(creat_names)]
print(f"  Creatinine rows on those dates: {len(creat_on_missing)}")
print(f"  Unique dates with Creatinine available: {creat_on_missing.date.nunique()}")

# Check: when there's only 1 Creatinine value on a BUN-POST date, it must be PRE
# When there are 2, the lower is POST
for d in sorted(missing_creat_post)[:20]:
    creat_rows = labs[(labs.date == d) & labs.test_name.isin(creat_names)]
    bun_rows = labs[(labs.date == d) & labs.test_name.isin(['BUN', 'BUN -POST', 'BUN - Post'])]
    creat_vals = creat_rows.value_numeric.dropna().tolist()
    bun_vals = [(r.test_name, r.value_numeric) for _, r in bun_rows.iterrows()]
    if creat_vals:
        print(f"  {d.date()}  Creat={creat_vals}  BUN={bun_vals}")

# ── Now apply all 3 rules to build comprehensive POST pivot ──
print("\n═══ Building comprehensive POST-dialysis assignments ═══\n")

post_assignments = []  # list of {date, test, value, rule}

# All POST-capable test groups
test_groups = {
    'BUN':         {'pre': ['BUN'], 'post': ['BUN -POST', 'BUN - Post']},
    'Creatinine':  {'pre': ['Creatnine', 'Creatinine', 'CREATININE'], 'post': ['Creatnine POST']},
    'PTH':         {'pre': ['PTH Intact', 'PTH-I', 'PTH', 'PTH-INTACT', 'PTH-Intact'], 'post': ['PTH POST']},
    'Calcium':     {'pre': ['Calcium', 'CALCIUM'], 'post': ['Calcium POST']},
    'Phosphorus':  {'pre': ['Phosphorous', 'PHOSPHORUS', 'Phosphorus'], 'post': ['Phosphorous POST']},
    'CO2':         {'pre': ['CO2 (Bicarbonate)', 'CO2'], 'post': ['CO2 POST', 'CO2 PST']},
    'ALP':         {'pre': ['ALK PHOS', 'Alk Phos'], 'post': ['ALK PHOS POST']},
}

for canonical, names in test_groups.items():
    all_names = names['pre'] + names['post']
    subset = labs[labs.test_name.isin(all_names)].copy()
    
    explicit_post = subset[subset.test_name.isin(names['post'])]
    for _, row in explicit_post.iterrows():
        if pd.notna(row.value_numeric):
            post_assignments.append({
                'date': row.date, 'test': canonical, 
                'value': row.value_numeric, 'rule': 'explicit'
            })
    
    # Rule 1: on dates with >1 value, lower = POST (if not already labeled)
    explicit_post_dates = set(explicit_post.date)
    valid_rows = subset[subset.value_numeric.notna()].copy()
    
    date_counts = valid_rows.groupby('date')['value_numeric'].count()
    multi_dates = date_counts[date_counts > 1].index
    
    for d in multi_dates:
        if d in explicit_post_dates:
            continue  # already have explicit POST
        rows = valid_rows[valid_rows.date == d]
        vals = rows.value_numeric.dropna().tolist()
        if len(vals) >= 2:
            post_val = min(vals)
            post_assignments.append({
                'date': d, 'test': canonical,
                'value': post_val, 'rule': 'rule1_lower_of_multiples'
            })
    
    # Rule 2 (BUN/Creatinine only): low values on dialysis days
    if canonical in ('BUN', 'Creatinine'):
        threshold = 30 if canonical == 'BUN' else 3.5
        single_dates = date_counts[date_counts == 1].index
        already_assigned = set(r['date'] for r in post_assignments if r['test'] == canonical)
        
        for d in single_dates:
            if d in already_assigned:
                continue
            rows = valid_rows[valid_rows.date == d]
            val = rows.value_numeric.values[0]
            if pd.notna(val) and val <= threshold:
                # Check if it's a dialysis day or day after
                if d in sess_dates or (d - pd.Timedelta(days=1)) in sess_dates:
                    post_assignments.append({
                        'date': d, 'test': canonical,
                        'value': val, 'rule': 'rule2_low_value_dialysis_day'
                    })

post_df = pd.DataFrame(post_assignments)
print(f"Total POST assignments: {len(post_df)}")
print(f"\nBy test and rule:")
print(post_df.groupby(['test', 'rule']).size().to_string())

print(f"\nUnique dates per test:")
for test in sorted(post_df.test.unique()):
    n = post_df[post_df.test == test].date.nunique()
    print(f"  {test:15s}  {n} dates")

# ── Also compute PRE values for each POST date ──
print("\n═══ Pre→Post pairs (for clearance computation) ═══\n")
for canonical, names in test_groups.items():
    post_vals = post_df[post_df.test == canonical].copy()
    if len(post_vals) == 0:
        continue
    
    pre_subset = labs[labs.test_name.isin(names['pre'])].copy()
    
    pairs = []
    for _, prow in post_vals.iterrows():
        d = prow['date']
        pre_rows = pre_subset[(pre_subset.date == d) & pre_subset.value_numeric.notna()]
        if len(pre_rows) > 0:
            # PRE = highest value on that date (POST is lowest)
            pre_val = pre_rows.value_numeric.max()
            if pre_val != prow['value']:  # make sure pre != post
                pairs.append({
                    'date': d, 'pre': pre_val, 'post': prow['value'],
                    'delta': prow['value'] - pre_val,
                    'pct_reduction': 100 * (pre_val - prow['value']) / pre_val if pre_val != 0 else 0
                })
    
    if pairs:
        pairs_df = pd.DataFrame(pairs)
        print(f"{canonical}:  {len(pairs)} pre→post pairs")
        print(f"  Mean pre:         {pairs_df['pre'].mean():.1f}")
        print(f"  Mean post:        {pairs_df['post'].mean():.1f}")
        print(f"  Mean delta:       {pairs_df['delta'].mean():.1f}")
        print(f"  Mean % reduction: {pairs_df['pct_reduction'].mean():.1f}%")
        print()

# ── Save enriched POST assignments for MATLAB to consume ──
out_path = os.path.join(data_dir, 'features', 'post_dialysis_labs.csv')
post_df.to_csv(out_path, index=False)
print(f"\n✅ Saved {len(post_df)} POST assignments → {out_path}")
