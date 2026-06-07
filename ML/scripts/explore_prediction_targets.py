#!/usr/bin/env python3
"""Explore available data for 11 clinical prediction targets."""
import pandas as pd
import numpy as np
from pathlib import Path

ML = str(Path(__file__).resolve().parent.parent)

# 1. Elimination (bloody bowel movements)
elim = pd.read_csv(f'{ML}/data/processed/unified_elimination.csv')
bloody = elim['blood'].isin(['True', 'TRACE', 'ÝES'])
print(f'Bloody BM: {bloody.sum()} / {len(elim)} ({100*bloody.sum()/len(elim):.1f}%)')
elim['date'] = pd.to_datetime(elim['date'])
print(f'Elimination date range: {elim.date.min()} to {elim.date.max()}')

# 2. Dialysis sessions with BP data
sess = pd.read_csv(f'{ML}/data/processed/dialysis_sessions.csv')
sess['session_date'] = pd.to_datetime(sess['session_date'])
print(f'\nDialysis sessions: {len(sess)}')
for c in ['pre_bp_sys','bp_lowest_sys','post_bp_sys','pre_bp_dia','post_bp_dia','bath_k','bath_ca','bath_na']:
    n = pd.to_numeric(sess[c], errors='coerce').notna().sum() if c in sess.columns else 0
    print(f'  {c}: N={n}')

# 3. Dialysis readings
rd = pd.read_csv(f'{ML}/data/processed/dialysis_readings.csv')
bp = pd.to_numeric(rd['bp_sys'], errors='coerce')
print(f'\nDialysis readings: {len(rd)}')
print(f'  bp_sys present: {bp.notna().sum()}, range: {bp.min():.0f}-{bp.max():.0f}')

# Hypotension during dialysis
hypo_intra = bp < 90
print(f'  Intra-dialysis hypotension (SBP<90): {hypo_intra.sum()} readings')

# 4. Labs for key markers
labs = pd.read_csv(f'{ML}/data/features/lab_pivot_canonical.csv')
labs['date'] = pd.to_datetime(labs['date'])
print(f'\nLab dates: {len(labs)}, range: {labs.date.min()} to {labs.date.max()}')
for col in ['Hemoglobin','Hematocrit','Potassium','Calcium','Glucose','PTH','LDH',
            'Phosphorus','CaxP','Reticulocyte','RDW','Iron','Ferritin','ISAT']:
    v = pd.to_numeric(labs[col], errors='coerce')
    n = v.notna().sum()
    if n > 0:
        print(f'  {col}: N={n}, mean={v.mean():.1f}, range={v.min():.1f}-{v.max():.1f}')

# 5. Vomit
v = pd.read_csv(f'{ML}/data/processed/vomit_log.csv')
v['date'] = pd.to_datetime(v['date'])
print(f'\nVomit events: {len(v)}, range: {v.date.min()} to {v.date.max()}')
print(f'  Vomit dates (unique): {v.date.nunique()}')

# 6. Count sessions per date to align
print(f'\nSession dates (unique): {sess.session_date.nunique()}')
print(f'Elimination dates (unique): {elim.date.nunique()}')

# 7. Clinical thresholds check
K = pd.to_numeric(labs['Potassium'], errors='coerce').dropna()
print(f'\nHypokalemia (K<3.5): {(K<3.5).sum()} / {len(K)} labs')
Ca = pd.to_numeric(labs['Calcium'], errors='coerce').dropna()
print(f'Hypocalcemia (Ca<8.5): {(Ca<8.5).sum()} / {len(Ca)} labs')
PTH = pd.to_numeric(labs['PTH'], errors='coerce').dropna()
print(f'High PTH (>300): {(PTH>300).sum()} / {len(PTH)} labs')
Hgb = pd.to_numeric(labs['Hemoglobin'], errors='coerce').dropna()
print(f'Low Hgb (<10): {(Hgb<10).sum()} / {len(Hgb)} labs')
Glu = pd.to_numeric(labs['Glucose'], errors='coerce').dropna()
print(f'Low glucose (<70): {(Glu<70).sum()} / {len(Glu)} labs')
CaxP = pd.to_numeric(labs['CaxP'], errors='coerce').dropna()
print(f'High CaxP (>55): {(CaxP>55).sum()} / {len(CaxP)} labs (calcification risk)')
LDH = pd.to_numeric(labs['LDH'], errors='coerce').dropna()
print(f'High LDH (>250): {(LDH>250).sum()} / {len(LDH)} labs (hemolysis marker)')
