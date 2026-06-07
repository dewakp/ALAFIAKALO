#!/usr/bin/env python3
"""Check date ranges for all existing data sources."""
import pandas as pd
import os
from pathlib import Path

BASE = str(Path(__file__).resolve().parent.parent)

files = {
    'nutrition': 'data/raw/api/nutrition.csv',
    'medications': 'data/raw/api/medications.csv',
    'lab_results': 'data/raw/api/lab_results.csv',
    'elimination': 'data/raw/api/elimination.csv',
    'vitals': 'data/raw/api/vitals.csv',
    'journal_mood': 'data/raw/api/journal_mood.csv',
    'symptoms': 'data/raw/api/symptoms.csv',
    'dialysis_sessions': 'data/raw/api/dialysis_sessions.csv',
    'dialysis_readings': 'data/raw/api/dialysis_readings.csv',
    'pdf_labs': 'data/raw/pdf/pdf_labs_extracted.csv',
}

print("=== FIRESTORE + PDF DATA COVERAGE ===\n")
for name, relpath in files.items():
    path = os.path.join(BASE, relpath)
    try:
        df = pd.read_csv(path)
        dcols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower() or 'created' in c.lower()]
        found = False
        if dcols:
            for dc in dcols[:3]:
                vals = pd.to_datetime(df[dc], errors='coerce').dropna()
                if not vals.empty:
                    print(f"  {name:20s} ({len(df):>5} rows)  {dc}: {vals.min().date()} to {vals.max().date()}")
                    found = True
                    break
        if not found:
            print(f"  {name:20s} ({len(df):>5} rows)  cols: {list(df.columns)[:6]}")
    except Exception as e:
        print(f"  {name:20s} ERROR: {e}")
