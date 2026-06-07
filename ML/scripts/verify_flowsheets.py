"""Verify parsed flowsheet data quality."""
import pandas as pd

s = pd.read_csv('data/raw/excel/flowsheet_sessions.csv')
s['date'] = pd.to_datetime(s['date'])

print('=== SESSIONS QUALITY CHECK ===')
print(f'Total: {len(s)}')
print(f'Date range: {s.date.min().date()} -> {s.date.max().date()}')
print(f'\nYear breakdown:')
print(s.date.dt.year.value_counts().sort_index().to_string())

print(f'\nKey field coverage:')
for col in ['pre_bp_sys', 'pre_bp_dia', 'today_weight', 'dry_weight',
            'post_bp_sys', 'post_weight', 'total_time', 'n_readings',
            'avg_bp_sys', 'total_uf_kg', 'total_dialysate_L']:
    if col in s.columns:
        n = s[col].notna().sum()
        print(f'  {col:25s}: {n:>4}/{len(s)} ({n/len(s)*100:.0f}%)')

print(f'\nPre-BP ranges:')
desc = s['pre_bp_sys'].describe()
print(f'  Sys: min={desc["min"]:.0f}, 25%={desc["25%"]:.0f}, med={desc["50%"]:.0f}, 75%={desc["75%"]:.0f}, max={desc["max"]:.0f}')
desc = s['pre_bp_dia'].describe()
print(f'  Dia: min={desc["min"]:.0f}, 25%={desc["25%"]:.0f}, med={desc["50%"]:.0f}, 75%={desc["75%"]:.0f}, max={desc["max"]:.0f}')

print(f'\nSuspicious dates:')
for yr in [2016, 2021]:
    subset = s[s.date.dt.year == yr]
    if len(subset) > 0:
        print(f'  {yr}:')
        for _, row in subset.iterrows():
            print(f'    {row.date.date()} - sheet: {row.sheet_name} - file: {row.source_file}')

# Readings
r = pd.read_csv('data/raw/excel/flowsheet_readings.csv')
print(f'\n=== READINGS ===')
print(f'Total: {len(r)}')
print(f'Avg readings per session: {len(r)/len(s):.1f}')

# Vomit
v = pd.read_csv('data/raw/excel/flowsheet_vomit_log.csv')
v['date'] = pd.to_datetime(v['date'])
print(f'\n=== VOMIT LOG ===')
print(f'Total events: {len(v)}')
print(f'Date range: {v.date.min().date()} -> {v.date.max().date()}')

# Weight range check
print(f'\nWeight ranges (kg):')
wt = s['today_weight_kg'].dropna()
print(f'  Today weight: min={wt.min():.1f}, med={wt.median():.1f}, max={wt.max():.1f}')
print(f'  Count in lbs format: {(s.weight_unit.str.lower().isin(["lb", "lbs"])).sum()}')
print(f'  Count in kg format: {(s.weight_unit.str.lower() == "kg").sum()}')
