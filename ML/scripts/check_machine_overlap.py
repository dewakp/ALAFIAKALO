#!/usr/bin/env python3
"""Check overlap between Machine sheet and Lab sheet."""
import pandas as pd
from pathlib import Path

BASE = str(Path(__file__).resolve().parent.parent)

ef = pd.read_csv(f"{BASE}/data/raw/excel/records_early_flowsheets_raw.csv")
lab = pd.read_csv(f"{BASE}/data/raw/excel/records_lab.csv")

early_dates = set(ef['date'].unique())
lab_dates_early = set(lab[lab['date'] < '2017-06-01']['date'].unique())

print("=== Machine sheet lab-related metrics ===")
lab_metrics = [
    'BUN Pre', 'BUN Post', 'BUN Delta', 'URR', 'nPCR',
    'Actual Kt/V', 'Target Kt/V', 'spKdt/V Dialysis', 'eKdt/V Dialysis',
    'TBV (Watson)', 'VM (Kt/V Mean Volume)', 'Treatment Volume',
]
for m in lab_metrics:
    m_dates = set(ef[ef['metric'] == m]['date'].unique())
    print(f"  {m:25s}  {len(m_dates):>3} dates in Machine")

print(f"\nMachine total dates: {len(early_dates)}")
print(f"Lab sheet dates (pre-Jun 2017): {len(lab_dates_early)}")
print(f"Overlap: {len(early_dates & lab_dates_early)} dates in both")

# BUN overlap
lab_bun = lab[lab['test_name'].str.contains('BUN', case=False, na=False)]
lab_bun_dates = set(lab_bun['date'].unique())
machine_bun = ef[ef['metric'].str.contains('BUN', case=False)]
machine_bun_dates = set(machine_bun['date'].unique())
only_machine = machine_bun_dates - lab_bun_dates
print(f"\nBUN dates only in Machine (not in Lab sheet): {len(only_machine)}")
if only_machine:
    print(f"  Sample: {sorted(only_machine)[:10]}")

# Session metrics (non-lab)
session_metrics = [
    'Weight Pre', 'Weight Post', 'Weight Loss', 'Weight Gain (BT)',
    'Pre BP Sitting', 'Post BP Sitting', 'Lowest BP', 'Average BP',
    'Pulse Pre', 'Pulse Post', 'Duration', 'Treatment Length',
    'Blood Flow', 'Dializer State Flow',
    'Bath CA', 'Bath K', 'Bath Na', 'Bath Dextrose', 'Mg',
    'Machine Temp', 'Machine Conductivity', 'Manual Conductivity',
    'Manual PH', 'TCD', 'VP@200',
]
print("\n=== Session/therapy metrics ===")
for m in session_metrics:
    m_dates = set(ef[ef['metric'] == m]['date'].unique())
    if m_dates:
        print(f"  {m:25s}  {len(m_dates):>3} dates")

# Metadata
meta_metrics = ['Facility', 'Physician', 'Technician', 'Machine Make', 'Machine Model', 'Machine Series']
print("\n=== Metadata ===")
for m in meta_metrics:
    vals = ef[ef['metric'] == m]['value'].unique()
    print(f"  {m:25s}  {len(vals)} unique values: {list(vals[:5])}")
