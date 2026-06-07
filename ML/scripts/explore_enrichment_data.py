#!/usr/bin/env python3
"""Explore nutrition, medications, and dialysis parameters for feature enrichment."""
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, '.')

ML = str(Path(__file__).resolve().parent.parent)

# ── NUTRITION ──
print("=" * 70)
print("NUTRITION DATA")
print("=" * 70)
n = pd.read_csv(f'{ML}/data/processed/unified_nutrition.csv')
print(f"Rows: {len(n)}, Unique dates: {n['date'].nunique()}")
print(f"Date range: {n['date'].min()} to {n['date'].max()}")
if 'meal_type' in n.columns:
    print(f"Meal types: {n['meal_type'].dropna().unique().tolist()[:10]}")

nutr_cols = ['calories','protein','carbs','fat','fiber','sugar',
             'sodium','potassium','calcium','iron','phosphorus',
             'vitamin_d','vitamin_b12','folic_acid','cholesterol']
for c in nutr_cols:
    if c in n.columns:
        pct = n[c].notna().mean() * 100
        if pct > 0:
            print(f"  {c:15s}  fill={pct:5.1f}%  mean={n[c].mean():.1f}")
        else:
            print(f"  {c:15s}  fill={pct:5.1f}%")

# ── MEDICATIONS ──
print("\n" + "=" * 70)
print("MEDICATIONS DATA")
print("=" * 70)
m = pd.read_csv(f'{ML}/data/processed/medications.csv')
print(f"Rows: {len(m)}, Unique dates: {m['date'].nunique()}")
print(f"Date range: {m['date'].min()} to {m['date'].max()}")
print(f"Unique meds: {m['medication_name'].nunique()}")
print("\nTop 15 medications:")
print(m['medication_name'].value_counts().head(15).to_string())

# ── DIALYSIS SESSION PARAMETERS ──
print("\n" + "=" * 70)
print("DIALYSIS SESSION PARAMETERS")
print("=" * 70)
s = pd.read_csv(f'{ML}/data/processed/dialysis_sessions.csv')
print(f"Sessions: {len(s)}")

dial_cols = [
    'total_time', 'dialysate_volume_L', 'total_dialysate_L', 'total_dialysate_liters',
    'avg_blood_flow_rate', 'prescribed_blood_flow_rate',
    'total_bvp', 'total_blood_volume_liters',
    'fluid_to_remove_kg', 'fluid_removed_liters', 'total_uf_kg',
    'bath_ca', 'bath_k', 'bath_na', 'conductivity', 'manual_ph',
    'dialysate_lactate', 'dialysate_k',
    'ktv_actual', 'ktv_spk', 'ktv_ek', 'urr', 'npcr',
    'weight_loss_kg', 'weight_gain_bt',
    'pre_pulse', 'post_pulse', 'avg_pulse',
    'pre_temp', 'post_temp', 'pre_temperature', 'post_temperature',
]
for c in dial_cols:
    if c in s.columns:
        pct = s[c].notna().mean() * 100
        try:
            col = pd.to_numeric(s[c], errors='coerce')
            mn = col.dropna().mean()
            if pct > 0 and pd.notna(mn):
                print(f"  {c:30s}  fill={pct:5.1f}%  mean={mn:.2f}")
            else:
                print(f"  {c:30s}  fill={pct:5.1f}%  (non-numeric)")
        except Exception:
            print(f"  {c:30s}  fill={pct:5.1f}%  (non-numeric)")

# ── DIALYSIS READINGS (inter-dialytic BP/HR) ──
print("\n" + "=" * 70)
print("DIALYSIS READINGS (intra-session)")
print("=" * 70)
r = pd.read_csv(f'{ML}/data/processed/dialysis_readings.csv')
print(f"Readings: {len(r)}, Sessions: {r['session_date'].nunique()}")
rdg_cols = ['bp_sys','bp_dia','pulse','dialysate_rate','dialysate_volume',
            'uf_rate','uf_volume','blood_flow_rate',
            'arterial_pressure','venous_pressure','effluent_pressure']
for c in rdg_cols:
    if c in r.columns:
        pct = r[c].notna().mean() * 100
        if pct > 0:
            mn = r[c].dropna().mean()
            print(f"  {c:25s}  fill={pct:5.1f}%  mean={mn:.2f}")

# ── Check date overlap ──
print("\n" + "=" * 70)
print("DATE OVERLAP ANALYSIS")
print("=" * 70)
s_dates = set(pd.to_datetime(s['session_date']).dt.date)
n_dates = set(pd.to_datetime(n['date']).dt.date)
m_dates = set(pd.to_datetime(m['date']).dt.date)
print(f"Session dates: {len(s_dates)}")
print(f"Nutrition dates: {len(n_dates)}")
print(f"Medication dates: {len(m_dates)}")
print(f"Sessions with nutrition same day: {len(s_dates & n_dates)}")
print(f"Sessions with nutrition day before: {len({d for d in s_dates if any((d - nd).days in [0,1] for nd in n_dates)})}")
print(f"Sessions with medication same day: {len(s_dates & m_dates)}")

# Daily nutrition aggregation preview
print("\n── Daily Nutrition Aggregation Sample ──")
n['date'] = pd.to_datetime(n['date'])
daily_n = n.groupby(n['date'].dt.date).agg({
    'calories': 'sum', 'protein': 'sum', 'carbs': 'sum', 'fat': 'sum',
    'sodium': 'sum', 'potassium': 'sum', 'phosphorus': 'sum', 'calcium': 'sum'
}).dropna(how='all')
print(f"Daily nutrition rows: {len(daily_n)}")
print(daily_n.describe().round(1).to_string())

print("\nDone.")
