#!/usr/bin/env python3
"""
Extract lab results from DaVita Lab Draw Report PDFs.

Format per line:
  CODE  LAB_TEST_NAME  RESULT [H/L]  UNIT  REF_RANGE  STATUS

Output: ML/data/raw/pdf/pdf_labs_extracted.csv
"""

import pdfplumber
import pandas as pd
import re
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
PDF_DIR = PROJECT_ROOT / 'data' / 'raw' / 'pdf'
OUTPUT_FILE = PDF_DIR / 'pdf_labs_extracted.csv'

# Regex to match lab result lines:
# CODE  TEST_NAME  RESULT [H/L]  UNIT  REF_LOW - REF_HIGH  STATUS
# Examples:
#   1002 ALB 4 g/dL 3.40 - 4.80 Final
#   1004 BUN 90 H mg/dL 9.00 - 23.00 Final
#   1005 CA 7.5 L mg/dL 8.70 - 10.40 Final
#   2243 HCT% 37.2 L % 41.00 - 53.00 Final
LAB_LINE_RE = re.compile(
    r'^(\d{4})\s+'              # CODE (4 digits)
    r'([A-Za-z][A-Za-z0-9/\*\-_%#\s\.]+?)\s+'  # TEST NAME
    r'([\d.]+|N/A|NEG|POS|<[\d.]+|>[\d.]+)\s*'  # RESULT (numeric, N/A, NEG, etc.)
    r'([HL])?\s*'               # H/L flag (optional)
    r'([A-Za-z%/\^x\s\d.*]+?)?\s*'  # UNIT (optional)
    r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s+'  # REF RANGE (low - high)
    r'(Final|Pending)'          # STATUS
)

# Simpler pattern for lines without reference range
LAB_LINE_SIMPLE_RE = re.compile(
    r'^(\d{4})\s+'              # CODE
    r'([A-Za-z][A-Za-z0-9/\*\-_%#\s\.]+?)\s+'  # TEST NAME
    r'([\d.]+|N/A|NEG|POS|<[\d.]+|>[\d.]+)\s*'  # RESULT
    r'([HL])?\s*'               # H/L flag
    r'([A-Za-z%/\^x\s\d.*]*?)\s*'  # UNIT
    r'(Final|Pending)'          # STATUS
)

# Date pattern in header: MM/DD/YYYY
COLLECTION_DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4})\s+\d{2}/\d{2}/\d{4}')


def extract_collection_date(text):
    """Extract collection date from PDF header."""
    m = COLLECTION_DATE_RE.search(text)
    if m:
        try:
            return datetime.strptime(m.group(1), '%m/%d/%Y').date().isoformat()
        except ValueError:
            pass
    return None


def extract_labs_from_pdf(pdf_path):
    """Extract all lab results from a DaVita Lab Draw Report PDF."""
    results = []
    collection_date = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            lines = text.split('\n')

            # Get collection date from first page
            if collection_date is None:
                collection_date = extract_collection_date(text)

            for line in lines:
                line = line.strip()
                if not line or not line[0].isdigit():
                    continue

                # Try full pattern (with reference range)
                m = LAB_LINE_RE.match(line)
                if m:
                    code, name, result, flag, unit, ref_low, ref_high, status = m.groups()
                    results.append({
                        'date': collection_date,
                        'source_file': pdf_path.name,
                        'code': code.strip(),
                        'test_name': name.strip(),
                        'result': result.strip(),
                        'flag': flag.strip() if flag else None,
                        'unit': unit.strip() if unit else None,
                        'ref_low': float(ref_low),
                        'ref_high': float(ref_high),
                        'status': status.strip(),
                    })
                    continue

                # Try simple pattern (no reference range)
                m = LAB_LINE_SIMPLE_RE.match(line)
                if m:
                    code, name, result, flag, unit, status = m.groups()
                    results.append({
                        'date': collection_date,
                        'source_file': pdf_path.name,
                        'code': code.strip(),
                        'test_name': name.strip(),
                        'result': result.strip(),
                        'flag': flag.strip() if flag else None,
                        'unit': unit.strip() if unit else None,
                        'ref_low': None,
                        'ref_high': None,
                        'status': status.strip(),
                    })

    return results


def main():
    print("=" * 60)
    print("DaVita Lab PDF Extraction")
    print("=" * 60)

    pdf_files = sorted(PDF_DIR.glob('*.pdf'))
    print(f"\nFound {len(pdf_files)} PDFs in {PDF_DIR}/")

    all_results = []
    for pdf_file in pdf_files:
        results = extract_labs_from_pdf(pdf_file)
        print(f"  {pdf_file.name:40s} → {len(results):3d} lab tests (date: {results[0]['date'] if results else '?'})")
        all_results.extend(results)

    df = pd.DataFrame(all_results)

    # Convert result to numeric where possible
    df['result_numeric'] = pd.to_numeric(df['result'], errors='coerce')

    # Sort by date, test name
    df = df.sort_values(['date', 'test_name']).reset_index(drop=True)

    df.to_csv(OUTPUT_FILE, index=False)

    print(f"\n{'='*60}")
    print(f"✅ Extracted {len(df):,} lab results from {len(pdf_files)} PDFs")
    print(f"   Output: {OUTPUT_FILE}")
    print(f"   Date range: {df['date'].min()} → {df['date'].max()}")
    print(f"   Unique tests: {df['test_name'].nunique()}")
    print(f"   Unique dates: {df['date'].nunique()}")

    # Summary of key tests
    print(f"\n   Key test coverage:")
    key_tests = ['ALB', 'BUN', 'CA', 'CRE', 'FE', 'FERR', 'HGB', 'K+', 'Na', 'PHOS',
                 'PLT', 'WBC', 'HCT%', 'MG', 'CO2', 'GLU', 'PTH']
    for test in key_tests:
        matches = df[df['test_name'].str.upper().str.strip() == test]
        if len(matches) > 0:
            print(f"     {test:10s}: {len(matches):3d} results")


if __name__ == '__main__':
    main()
