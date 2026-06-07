#!/usr/bin/env python3
"""Parse September worksheet PDF and append Jul+Sep 2025 data to pdf_labs_extracted.csv."""
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / 'data' / 'raw' / 'pdf' / 'pdf_labs_extracted.csv'

rows = []

def add(test, unit, sep_val, jul_val):
    src = 'September labs AA.pdf'
    if sep_val and sep_val not in ('-', 'Error', 'N/A'):
        try:
            num = float(sep_val)
        except ValueError:
            num = None
        rows.append({
            'date': '2025-09-03', 'source_file': src, 'code': '',
            'test_name': test, 'result': sep_val, 'flag': None,
            'unit': unit, 'ref_low': None, 'ref_high': None,
            'status': 'Final', 'result_numeric': num,
        })
    if jul_val and jul_val not in ('-', 'Error', 'N/A'):
        try:
            num = float(jul_val)
        except ValueError:
            num = None
        rows.append({
            'date': '2025-07-17', 'source_file': src, 'code': '',
            'test_name': test, 'result': jul_val, 'flag': None,
            'unit': unit, 'ref_low': None, 'ref_high': None,
            'status': 'Final', 'result_numeric': num,
        })

# Extracted from the IDT Patient Profile Worksheet
# Columns: SEP 2025 (09/03), AUG 2025 (08/13, already covered), JUL 2025 (07/17)
add('HGB',      'g/dL',      '13.2',  '12.8')
add('HCT%',     '%',         '43.8',  '42.3')
add('FERR',     'ng/mL',     '182',   '178')
add('MCV',      'fL',        '94.3',  '92.2')
add('WBC',      'x10^3/uL', '4.2',   '3.6')
add('BUN',      'mg/dL',     '79',    '115')
add('BUN-P',    'mg/dL',     '20',    '22')
add('URR%',     '%',         '75',    '81')
add('CRE',      'mg/dL',     '9.46',  '11.91')
add('ALB',      'g/dL',      '4.4',   '4.4')
add('K+',       'mEq/L',     None,    '6.7')
add('Na',       'mEq/L',     '130',   '132')
add('CO2',      'mEq/L',     '24',    '21')
add('CA',       'mg/dL',     '8.0',   '8.1')
add('CA CORR',  'mg/dL',     '8.0',   '8.1')
add('PHOS',     'mg/dL',     '3.0',   '2.8')
add('PTH',      'pg/mL',     '24',    '22')
add('VIT D',    'ng/mL',     '29.5',  None)
add('CA*POCOR', 'Calc',      '24.0',  '22.7')
add('STDKT/V',  '',          '4.01',  None)
add('SPKT/V',   '',          '1.65',  None)
add('ISAT',     '%',         None,    '28')

df_new = pd.DataFrame(rows)
sep_count = len(df_new[df_new['date'] == '2025-09-03'])
jul_count = len(df_new[df_new['date'] == '2025-07-17'])
print(f"Extracted {len(df_new)} results (Sep: {sep_count}, Jul: {jul_count})")

df_existing = pd.read_csv(CSV_PATH)
df_combined = pd.concat([df_existing, df_new], ignore_index=True)
df_combined = df_combined.sort_values(['date', 'test_name']).reset_index(drop=True)
df_combined.to_csv(CSV_PATH, index=False)

print(f"Total: {len(df_combined)} results, {df_combined['date'].nunique()} unique dates")
print(f"Date range: {df_combined['date'].min()} -> {df_combined['date'].max()}")
