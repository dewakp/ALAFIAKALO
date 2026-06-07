#!/usr/bin/env python3
"""Build comprehensive POST-dialysis lab assignments with 4 rules + time delta.

Rules:
  R1 (explicit):  Test name contains 'POST' → POST
  R2 (lower dup): When >1 value on same date, lower = POST  
  R3 (low value): Creat≤3.5 or BUN<30 on dialysis day → POST
  R4 (facility):  Home/DaVita dialysis + Kaiser lab (source=records_xlsx)
                  on same day or day-after → ALL labs on that date are POST

Time-delta feature:
  date_delta_days = lab_date - dialysis_date (0 or 1)
  est_hours_post  = estimated hours since dialysis ended
    - same-day: 4 hrs (conservative; dialysis typically pm, labs drawn after)
    - next-day: 12+total_time/60 hrs (overnight + next-morning labs)

Outputs:
  1. data/features/post_dialysis_labs.csv      — individual POST lab values (for clearance)
  2. data/features/post_dialysis_dates.csv     — dates flagged as POST-collection context
"""
import pandas as pd
import numpy as np
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

# ── Load data ──
labs = pd.read_csv(os.path.join(data_dir, 'processed', 'unified_labs.csv'))
labs['date'] = pd.to_datetime(labs['date'])
labs['value_numeric'] = pd.to_numeric(labs['value_numeric'], errors='coerce')

sess = pd.read_csv(os.path.join(data_dir, 'processed', 'dialysis_sessions.csv'))
sess['session_date'] = pd.to_datetime(sess['session_date'])
sess['total_time_min'] = pd.to_numeric(sess['total_time'], errors='coerce')
sess_dates = set(sess['session_date'])

# ── Identify Home/DaVita sessions ──
home_mask = sess.facility.isna() | (sess.facility == 'unknown') | \
            sess.facility.str.contains('Davita|davita|home|Home', na=False, case=False)
home_sess = sess[home_mask].copy()
home_dates = set(home_sess.session_date)
home_next_dates = {d + pd.Timedelta(days=1) for d in home_dates}

print(f"Total sessions: {len(sess)}")
print(f"Home/DaVita sessions: {len(home_sess)} ({len(home_dates)} unique dates)")

# ── Build session total_time lookup for delta estimation ──
sess_time_lookup = {}
for _, row in home_sess.iterrows():
    d = row['session_date']
    t = row['total_time_min']
    if pd.notna(t):
        sess_time_lookup[d] = float(t)

# ═══════════════════════════════════════════════════════════════════
# PART A: Individual POST lab value assignments (Rules 1-3)
# ═══════════════════════════════════════════════════════════════════

test_groups = {
    'BUN':         {'pre': ['BUN'], 'post': ['BUN -POST', 'BUN - Post']},
    'Creatinine':  {'pre': ['Creatnine', 'Creatinine', 'CREATININE'], 'post': ['Creatnine POST']},
    'PTH':         {'pre': ['PTH Intact', 'PTH-I', 'PTH', 'PTH-INTACT', 'PTH-Intact'], 'post': ['PTH POST']},
    'Calcium':     {'pre': ['Calcium', 'CALCIUM'], 'post': ['Calcium POST']},
    'Phosphorus':  {'pre': ['Phosphorous', 'PHOSPHORUS', 'Phosphorus'], 'post': ['Phosphorous POST']},
    'CO2':         {'pre': ['CO2 (Bicarbonate)', 'CO2'], 'post': ['CO2 POST', 'CO2 PST']},
    'ALP':         {'pre': ['ALK PHOS', 'Alk Phos'], 'post': ['ALK PHOS POST']},
}

post_assignments = []

for canonical, names in test_groups.items():
    all_names = names['pre'] + names['post']
    subset = labs[labs.test_name.isin(all_names)].copy()
    
    # Rule 1 (explicit): test name contains POST
    explicit_post = subset[subset.test_name.isin(names['post'])]
    for _, row in explicit_post.iterrows():
        if pd.notna(row.value_numeric):
            post_assignments.append({
                'date': row.date, 'test': canonical, 
                'value': row.value_numeric, 'rule': 'explicit'
            })
    
    # Rule 2: on dates with >1 value, lower = POST
    explicit_post_dates = set(explicit_post.date)
    valid_rows = subset[subset.value_numeric.notna()].copy()
    date_counts = valid_rows.groupby('date')['value_numeric'].count()
    multi_dates = date_counts[date_counts > 1].index
    
    for d in multi_dates:
        if d in explicit_post_dates:
            continue
        rows = valid_rows[valid_rows.date == d]
        vals = rows.value_numeric.dropna().tolist()
        if len(vals) >= 2:
            post_val = min(vals)
            post_assignments.append({
                'date': d, 'test': canonical,
                'value': post_val, 'rule': 'rule2_lower_of_multiples'
            })
    
    # Rule 3 (BUN/Creatinine only): low values on dialysis days
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
                if d in sess_dates or (d - pd.Timedelta(days=1)) in sess_dates:
                    post_assignments.append({
                        'date': d, 'test': canonical,
                        'value': val, 'rule': 'rule3_low_value_dialysis_day'
                    })

post_df = pd.DataFrame(post_assignments)
print(f"\n═══ PART A: Individual POST assignments (Rules 1-3) ═══")
print(f"Total: {len(post_df)}")
print(post_df.groupby(['test', 'rule']).size().to_string())

# ═══════════════════════════════════════════════════════════════════
# PART B: Rule 4 — Kaiser facility on Home/DaVita dialysis days
# ═══════════════════════════════════════════════════════════════════

print(f"\n═══ PART B: Rule 4 — Kaiser labs on Home/DaVita dialysis days ═══")

# Kaiser labs = source is records_xlsx OR lab_name contains Kaiser
kaiser_mask = (labs.source == 'records_xlsx') | \
              labs['lab_name'].str.contains('Kaiser', na=False, case=False) \
              if 'lab_name' in labs.columns else (labs.source == 'records_xlsx')
kaiser_labs = labs[kaiser_mask].copy()

# Same-day: Kaiser lab on a home-dialysis date
same_day_mask = kaiser_labs.date.isin(home_dates)
same_day_labs = kaiser_labs[same_day_mask].copy()
same_day_labs['date_delta_days'] = 0
same_day_labs['dialysis_date'] = same_day_labs['date']

# Next-day: Kaiser lab on day after home-dialysis (but not also a dialysis day itself)
next_day_mask = kaiser_labs.date.isin(home_next_dates) & ~kaiser_labs.date.isin(home_dates)
next_day_labs = kaiser_labs[next_day_mask].copy()
next_day_labs['date_delta_days'] = 1
next_day_labs['dialysis_date'] = next_day_labs['date'] - pd.Timedelta(days=1)

# Combine Rule 4 candidates
rule4_labs = pd.concat([same_day_labs, next_day_labs], ignore_index=True)

# Estimate hours since dialysis
def estimate_hours_post(row):
    """Estimate hours between dialysis end and lab collection.
    
    For home HD patients:
    - Typical session: 3-4.5 hrs, usually evening/overnight
    - Same-day Kaiser lab: lab drawn AFTER dialysis → ~2-6 hrs post
    - Next-day Kaiser lab: lab drawn next morning → ~10-18 hrs post
    
    We use total_time when available for better estimation.
    """
    dial_date = row['dialysis_date']
    delta_days = row['date_delta_days']
    
    # Get session duration if available
    total_min = sess_time_lookup.get(dial_date, 240.0)  # default 4hrs
    total_hrs = total_min / 60.0
    
    if delta_days == 0:
        # Same day: assume lab drawn ~2-4 hrs after dialysis ends
        return total_hrs + 3.0  # session duration + ~3hr gap
    else:
        # Next day: assume evening dialysis, next-morning lab
        # e.g., dialysis 8pm-midnight, lab at 8am = ~8 hrs post
        # e.g., dialysis 6pm-10pm, lab at 8am = ~10 hrs post  
        return 14.0  # conservative mid-estimate for overnight gap

rule4_labs['est_hours_post'] = rule4_labs.apply(estimate_hours_post, axis=1)

print(f"Same-day Kaiser labs on dialysis days: {len(same_day_labs)} rows, {same_day_labs.date.nunique()} dates")
print(f"Next-day Kaiser labs after dialysis:   {len(next_day_labs)} rows, {next_day_labs.date.nunique()} dates")
print(f"Total Rule 4 labs: {len(rule4_labs)} rows, {rule4_labs.date.nunique()} dates")

# ── Add Rule 4 labs to individual POST assignments ──
# For analytes we track, also add their values to post_assignments
for canonical, names in test_groups.items():
    all_names = names['pre'] + names['post']
    r4_matches = rule4_labs[rule4_labs.test_name.isin(all_names) & rule4_labs.value_numeric.notna()]
    
    already = set(post_df[post_df.test == canonical].date)
    new_count = 0
    for _, row in r4_matches.iterrows():
        if row.date not in already:
            post_assignments.append({
                'date': row.date, 'test': canonical,
                'value': row.value_numeric, 'rule': 'rule4_kaiser_facility'
            })
            already.add(row.date)
            new_count += 1
    if new_count > 0:
        print(f"  {canonical}: +{new_count} new POST dates from Rule 4")

# Rebuild post_df with Rule 4 additions
post_df = pd.DataFrame(post_assignments)
print(f"\nEnriched POST assignments (R1-R4): {len(post_df)}")
print(post_df.groupby(['test', 'rule']).size().to_string())

# ═══════════════════════════════════════════════════════════════════
# PART C: Build POST-dialysis DATE-level context
# ═══════════════════════════════════════════════════════════════════

print(f"\n═══ PART C: POST-dialysis date-level context ═══")

# All dates where labs are post-dialysis (from any rule)
post_date_records = []

# From Rules 1-3: dates with explicit POST assignments
r123_dates = set(post_df.date)

# From Rule 4: all Rule 4 dates
r4_dates = set(rule4_labs.date)

all_post_dates = r123_dates | r4_dates

for d in sorted(all_post_dates):
    # Find the corresponding dialysis session
    if d in home_dates:
        dial_date = d
        delta_days = 0
    elif (d - pd.Timedelta(days=1)) in home_dates:
        dial_date = d - pd.Timedelta(days=1)
        delta_days = 1
    elif d in sess_dates:
        dial_date = d
        delta_days = 0
    else:
        # No matching dialysis session — still mark the date
        dial_date = pd.NaT
        delta_days = -1
    
    # Session total_time
    total_min = sess_time_lookup.get(dial_date, np.nan) if pd.notna(dial_date) else np.nan
    
    # Estimate hours post
    if delta_days == 0 and pd.notna(total_min):
        est_hrs = total_min / 60.0 + 3.0
    elif delta_days == 1:
        est_hrs = 14.0
    elif delta_days == 0:
        est_hrs = 7.0  # default same-day
    else:
        est_hrs = np.nan
    
    # Determine which rules apply
    rules = []
    if d in set(post_df[post_df.rule == 'explicit'].date):
        rules.append('explicit')
    if d in set(post_df[post_df.rule.str.startswith('rule2')].date):
        rules.append('rule2')
    if d in set(post_df[post_df.rule.str.startswith('rule3')].date):
        rules.append('rule3')
    if d in r4_dates:
        rules.append('rule4_kaiser')
    
    # How many lab tests on this date
    n_tests = len(labs[labs.date == d])
    n_kaiser = len(kaiser_labs[kaiser_labs.date == d]) if d in r4_dates else 0
    
    post_date_records.append({
        'lab_date': d,
        'dialysis_date': dial_date,
        'date_delta_days': delta_days,
        'est_hours_post': est_hrs,
        'total_time_min': total_min,
        'n_lab_tests': n_tests,
        'n_kaiser_tests': n_kaiser,
        'rules_applied': '|'.join(rules),
        'is_post': 1,
    })

post_dates_df = pd.DataFrame(post_date_records)
print(f"Total POST-collection dates: {len(post_dates_df)}")
print(f"  Same-day (delta=0): {(post_dates_df.date_delta_days == 0).sum()}")
print(f"  Next-day (delta=1): {(post_dates_df.date_delta_days == 1).sum()}")
print(f"  No dialysis match:  {(post_dates_df.date_delta_days == -1).sum()}")
print(f"\nEst hours post-dialysis:")
valid_hrs = post_dates_df.est_hours_post.dropna()
print(f"  mean: {valid_hrs.mean():.1f}")
print(f"  median: {valid_hrs.median():.1f}")
print(f"  range: {valid_hrs.min():.1f} - {valid_hrs.max():.1f}")

print(f"\nRules applied distribution:")
for rule_combo in sorted(post_dates_df.rules_applied.value_counts().index):
    n = (post_dates_df.rules_applied == rule_combo).sum()
    print(f"  {rule_combo:40s}  N={n}")

# ═══════════════════════════════════════════════════════════════════
# PART D: Pre→Post clearance computation
# ═══════════════════════════════════════════════════════════════════

print(f"\n═══ PART D: Pre→Post clearance stats ═══\n")
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
            pre_val = pre_rows.value_numeric.max()
            if pre_val != prow['value']:
                pairs.append({
                    'date': d, 'pre': pre_val, 'post': prow['value'],
                    'delta': prow['value'] - pre_val,
                    'pct_reduction': 100 * (pre_val - prow['value']) / pre_val if pre_val != 0 else 0
                })
    
    if pairs:
        pdf = pd.DataFrame(pairs)
        print(f"{canonical}:  {len(pdf)} pre→post pairs, "
              f"mean reduction: {pdf['pct_reduction'].mean():.1f}%")

# ═══════════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════════

out_dir = os.path.join(data_dir, 'features')
os.makedirs(out_dir, exist_ok=True)

out1 = os.path.join(out_dir, 'post_dialysis_labs.csv')
post_df.to_csv(out1, index=False)
print(f"\n✅ Saved {len(post_df)} individual POST assignments → {out1}")

out2 = os.path.join(out_dir, 'post_dialysis_dates.csv')
post_dates_df.to_csv(out2, index=False)
print(f"✅ Saved {len(post_dates_df)} POST-collection dates → {out2}")

# Also save the Rule 4 lab rows with time delta for direct use
out3 = os.path.join(out_dir, 'rule4_kaiser_post_labs.csv')
r4_out = rule4_labs[['date', 'test_name', 'value_numeric', 'source', 
                      'date_delta_days', 'dialysis_date', 'est_hours_post']].copy()
r4_out.to_csv(out3, index=False)
print(f"✅ Saved {len(r4_out)} Rule 4 Kaiser POST lab rows → {out3}")
