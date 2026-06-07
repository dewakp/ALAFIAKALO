#!/usr/bin/env python3
"""Extract fresh results from all models/data for paper update."""
import joblib, json, pandas as pd, numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / 'models'
FEATURES = ROOT / 'data' / 'features'
PROCESSED = ROOT / 'data' / 'processed'

# 1. Holistic model
hm = joblib.load(MODELS / 'holistic_health_model.joblib')
print('=== HOLISTIC MODEL ===')
fn = list(hm['pipeline'].feature_names_in_)
print(f'  Features: {len(fn)}')
metrics = hm['metrics']
for k, v in metrics.items():
    print(f'  {k}: {v}')
last_step = list(hm['pipeline'].named_steps.keys())[-1]
algo = type(hm['pipeline'].named_steps[last_step]).__name__
print(f'  Algorithm: {algo}')

# 2. Risk models (NB04)
print('\n=== NB04 RISK MODELS ===')
risk_names = ['anemia','gi_distress','hyperkalemia','hyperparathyroid','hypocalcemia',
              'hypokalemia','intradialytic_hypotension','iron_deficiency',
              'malnutrition','metabolic_acidosis','poor_health']
for rn in risk_names:
    try:
        rm = joblib.load(MODELS / f'risk_{rn}_model.joblib')
        met = rm.get('metrics', {})
        last_step = list(rm['pipeline'].named_steps.keys())[-1]
        algo = type(rm['pipeline'].named_steps[last_step]).__name__
        print(f'  {rn}: metrics={met}, algo={algo}')
    except Exception as e:
        print(f'  {rn}: ERROR {e}')

# 3. NB06 clinical risk performance
print('\n=== NB06 CLINICAL RISK ===')
try:
    perf = pd.read_csv(MODELS / 'clinical_risk' / 'performance_summary.csv')
    print(perf.to_string(index=False))
except Exception as e:
    print(f'  Error: {e}')

# 4. Data sizes
print('\n=== DATA SIZES ===')
df_f = pd.read_csv(FEATURES / 'health_features.csv')
print(f'  health_features: {df_f.shape}')
date_col = [c for c in df_f.columns if 'date' in c.lower()]
if date_col:
    dates = pd.to_datetime(df_f[date_col[0]])
    print(f'  Date range: {dates.min()} to {dates.max()}')
    print(f'  Calendar days: {(dates.max() - dates.min()).days}')

df_n = pd.read_csv(PROCESSED / 'unified_nutrition.csv', low_memory=False)
print(f'  nutrition: {len(df_n)} rows')
df_d = pd.read_csv(PROCESSED / 'dialysis_sessions.csv', low_memory=False)
print(f'  dialysis_sessions: {len(df_d)} rows')
df_l = pd.read_csv(PROCESSED / 'unified_labs.csv', low_memory=False)
print(f'  labs: {len(df_l)} rows, {df_l["test_name"].nunique()} unique tests')
df_w = pd.read_csv(FEATURES / 'HEBCS_wellness_daily.csv', index_col=0, parse_dates=True)
print(f'  wellness_daily: {df_w.shape}')
df_ps = pd.read_csv(FEATURES / 'HEBCS_pathway_scores.csv')
print(f'  pathway_scores: {df_ps.shape}')

# 5. Pathway details
print('\n=== PATHWAY DETAILS ===')
if 'pathway' in df_ps.columns:
    print(f'  Unique pathways: {df_ps["pathway"].nunique()}')
    for p in df_ps['pathway'].unique():
        sub = df_ps[df_ps['pathway'] == p]
        print(f'    {p}: {len(sub)} rows')
print(f'  Columns: {list(df_ps.columns)}')

# 6. Wellness aggregation stats
print('\n=== WELLNESS AGGREGATION ===')
for col in ['W_product', 'W_additive', 'W_geometric']:
    if col in df_w.columns:
        s = df_w[col].dropna()
        print(f'  {col}: mean={s.mean():.4f}, std={s.std():.4f}, n={len(s)}')

# 7. Elimination data
print('\n=== ELIMINATION DATA ===')
elim_path = PROCESSED / 'unified_elimination.csv'
if elim_path.exists():
    df_e = pd.read_csv(elim_path)
    print(f'  Total: {len(df_e)} rows')
    if 'type' in df_e.columns:
        print(f'  By type:')
        for t, cnt in df_e['type'].value_counts().items():
            print(f'    {t}: {cnt}')

# 8. Dialysis readings
print('\n=== DIALYSIS READINGS ===')
dr_path = PROCESSED / 'dialysis_readings.csv'
if dr_path.exists():
    df_dr = pd.read_csv(dr_path, low_memory=False)
    print(f'  Total: {len(df_dr)} rows')
