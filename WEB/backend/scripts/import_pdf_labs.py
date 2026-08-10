#!/usr/bin/env python3
"""
Import lab results from DaVita PDF lab reports into ALAFIA database.  

Handles two DaVita PDF formats:
1. Standard Lab Draw Report — structured per-test rows with CODE, NAME, RESULT, UNIT, RANGE
2. IDT Patient Profile Worksheet — summary table with categories (September format)

Usage:
    python3 import_pdf_labs.py
"""

import os
import re
import sys
from datetime import datetime, date
import fitz  # PyMuPDF
import psycopg2
from psycopg2.extras import execute_values

# ── Config ──────────────────────────────────────────────────────────────────────
PDF_DIR = os.path.expanduser("~/Downloads/Labs")
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "alafia"
DB_USER = "alafia"
DB_PASS = "alafia"
USER_ID = 1  # demo@alafia.app

# Lab test name normalization map (DaVita abbreviations → standard names)
NAME_MAP = {
    "A/G": "A/G Ratio",
    "A/G RATIO": "A/G Ratio",
    "ALB": "Albumin",
    "ALBUMIN": "Albumin",
    "ALP": "Alk Phos",
    "ALK PHOS": "Alk Phos",
    "ALT/SGPT": "ALT/SGPT",
    "AST/SGOT": "AST/SGOT",
    "BASO": "Basophils %",
    "BASOPHILS": "Basophils %",
    "BASOS-ABS": "Basophils Abs",
    "B12": "Vitamin B12",
    "BUN": "BUN",
    "BUN - POST": "BUN Post",
    "CA CORRECTED": "Calcium Corrected",
    "CA*PO4 CORRCTD": "Ca*PO4 Product Corrected",
    "CA/PHOS PRODUCT": "Ca*PO4 Product",
    "CALCIUM": "Calcium",
    "CHLORIDE": "Chloride",
    "CHOL/HDL RATIO": "Cholesterol/HDL Ratio",
    "CHOLESTEROL": "Cholesterol",
    "CO2": "CO2",
    "CREATININE": "Creatinine",
    "CREATININE - POST": "Creatinine Post",
    "EOS": "Eosinophils %",
    "EOSINOPHILS": "Eosinophils %",
    "EOS-ABS": "Eosinophils Abs",
    "FERRITIN": "Ferritin",
    "FOLATE": "Folate",
    "GLUCOSE": "Glucose",
    "HCT": "Hematocrit",
    "HEMATOCRIT": "Hematocrit",
    "HGB": "Hemoglobin",
    "HEMOGLOBIN": "Hemoglobin",
    "HDL": "HDL Cholesterol",
    "HDL CHOLESTEROL": "HDL Cholesterol",
    "IRON": "Iron",
    "IRON SATURATION": "Iron Saturation",
    "IRON SAT": "Iron Saturation",
    "LDH": "LDH",
    "LDL": "LDL Cholesterol",
    "LDL CALCULATED": "LDL Cholesterol",
    "LYMPH": "Lymphocytes %",
    "LYMPHOCYTES": "Lymphocytes %",
    "LYMPHS-ABS": "Lymphocytes Abs",
    "MCH": "MCH",
    "MCHC": "MCHC",
    "MCV": "MCV",
    "MONO": "Monocytes %",
    "MONOCYTES": "Monocytes %",
    "MONOS-ABS": "Monocytes Abs",
    "NEUT": "Neutrophils %",
    "NEUTROPHILS": "Neutrophils %",
    "NEUTS-ABS": "Neutrophils Abs",
    "NPCR": "NPCR",
    "PHOSPHORUS": "Phosphorus",
    "PLATELET": "Platelet Count",
    "PLATELET COUNT": "Platelet Count",
    "POTASSIUM": "Potassium",
    "POTASSIUM - POST": "Potassium Post",
    "PTH-INTACT": "PTH (Intact)",
    "PTH INTACT": "PTH (Intact)",
    "PTH-I": "PTH (Intact)",
    "PTH": "PTH (Intact)",
    "RBC": "RBC",
    "RDW": "RDW",
    "SODIUM": "Sodium",
    "SPKT/V": "spKt/V",
    "STDKT/V (DIAL)": "stdKt/V Dialysis",
    "STDKT/V TOTAL": "stdKt/V Total",
    "TIBC": "TIBC",
    "TOTAL PROTEIN": "Total Protein",
    "TRANSFERRIN": "Transferrin",
    "TRIGLYCERIDE": "Triglycerides",
    "TRIGLYCERIDES": "Triglycerides",
    "URR%": "URR%",
    "VLDL": "VLDL",
    "VITAMIN D (25-OH)": "Vitamin D 25-OH",
    "VITAMIN D": "Vitamin D 25-OH",
    "WBC": "WBC",
    "ABSL. RETIC CT.": "Absolute Reticulocyte Count",
    "ABSOLUTE RETIC COUNT": "Absolute Reticulocyte Count",
    "RETIC COUNT": "Reticulocyte Count",
    "ALUMINUM - BLOOD": "Aluminum Blood",
    "HEMOGLOBIN A1C": "HbA1c",
    "HBA1C": "HbA1c",
    "GFR": "GFR",
    "EGFR": "eGFR",
    "PSA": "PSA",
    "TSH": "TSH",
    "FREE T4": "Free T4",
    "T4 FREE": "Free T4",
    "URIC ACID": "Uric Acid",
    "HEPATITIS B SURFACE AB": "Hepatitis B Surface Ab",
    "HEPATITIS B SURFACE AG": "Hepatitis B Surface Ag",
    "HEPATITIS C AB": "Hepatitis C Ab",
    "HIV": "HIV",
}

# Category assignment based on test name
def get_category(test_name):
    name_upper = test_name.upper()
    if any(t in name_upper for t in ["HEMOGLOBIN", "HEMATOCRIT", "HGB", "HCT", "RBC", "WBC",
                                      "PLATELET", "MCV", "MCH", "MCHC", "RDW", "NEUT", "LYMPH",
                                      "MONO", "EOS", "BASO", "RETIC", "IRON", "FERRITIN",
                                      "TIBC", "TRANSFERRIN", "IRON SAT"]):
        return "Hematology"
    if any(t in name_upper for t in ["BUN", "CREATININE", "GFR", "EGFR", "URR", "KT/V",
                                      "STDKT", "SPKT", "NPCR"]):
        return "Kidney Function"
    if any(t in name_upper for t in ["CALCIUM", "PHOSPHORUS", "PTH", "VITAMIN D", "CA*PO4",
                                      "CA CORRECTED", "CA/PHOS"]):
        return "Mineral & Bone"
    if any(t in name_upper for t in ["CHOLESTEROL", "HDL", "LDL", "TRIGLYCERIDE", "VLDL",
                                      "CHOL/HDL"]):
        return "Lipid Panel"
    if any(t in name_upper for t in ["ALT", "AST", "ALP", "ALK PHOS", "BILIRUBIN", "TOTAL PROTEIN",
                                      "ALBUMIN", "A/G", "LDH"]):
        return "Liver & Protein"
    if any(t in name_upper for t in ["SODIUM", "POTASSIUM", "CHLORIDE", "CO2", "GLUCOSE"]):
        return "Electrolytes"
    if any(t in name_upper for t in ["HEPATITIS", "HIV"]):
        return "Infectious Disease"
    if any(t in name_upper for t in ["TSH", "T4", "T3"]):
        return "Thyroid"
    if any(t in name_upper for t in ["B12", "FOLATE"]):
        return "Vitamins"
    if any(t in name_upper for t in ["ALUMINUM"]):
        return "Toxicology"
    return "Other"


def normalize_test_name(raw_name):
    """Normalize DaVita test name to standard name."""
    clean = raw_name.strip().upper()
    # Remove trailing whitespace/artifacts
    clean = re.sub(r'\s+', ' ', clean)
    return NAME_MAP.get(clean, raw_name.strip())


def parse_value_and_flags(result_str):
    """
    Parse a result string like '276 H', '< 10', '4.2', 'Error' 
    Returns (numeric_value, value_string, is_high, is_low)
    """
    result_str = result_str.strip()
    
    # Skip error/non-numeric results
    if not result_str or result_str.upper() in ('ERROR', 'N/A', '-', 'TNP', 'CANC', 
                                                   'QNS', 'NONREACTIVE', 'REACTIVE',
                                                   'NEGATIVE', 'POSITIVE', 'NOT DETECTED',
                                                   'DETECTED', 'NON-REACTIVE'):
        if result_str.upper() in ('NONREACTIVE', 'NON-REACTIVE', 'NEGATIVE', 'NOT DETECTED'):
            return None, result_str, False, False
        if result_str.upper() in ('REACTIVE', 'POSITIVE', 'DETECTED'):
            return None, result_str, True, False
        return None, result_str if result_str else None, False, False
    
    is_high = 'H' in result_str.split()[-1:] if result_str else False
    is_low = 'L' in result_str.split()[-1:] if result_str else False
    
    # Check H/L flags
    flag_match = re.search(r'\s+([HL])\s*$', result_str)
    if flag_match:
        is_high = flag_match.group(1) == 'H'
        is_low = flag_match.group(1) == 'L'
    
    # Extract numeric value (handles < 10, > 100, etc.)
    num_match = re.search(r'[<>]?\s*([\d.]+)', result_str)
    if num_match:
        try:
            value = float(num_match.group(1))
            value_string = result_str if '<' in result_str or '>' in result_str else None
            return value, value_string, is_high, is_low
        except ValueError:
            pass
    
    return None, result_str, False, False


def parse_reference_range(range_str):
    """Parse '46.00 - 116.00' → (46.0, 116.0)"""
    if not range_str:
        return None, None
    range_str = range_str.strip()
    match = re.match(r'([\d.]+)\s*-\s*([\d.]+)', range_str)
    if match:
        try:
            return float(match.group(1)), float(match.group(2))
        except ValueError:
            pass
    return None, None


# ── Standard Lab Draw Report Parser ────────────────────────────────────────────
def parse_standard_report(pdf_path):
    """
    Parse DaVita Lab Draw Report format.
    Returns list of dicts with lab result data.
    """
    doc = fitz.open(pdf_path)
    results = []
    
    # Extract collection date and facility from first page
    first_page = doc[0].get_text()
    collection_date = None
    facility = None
    provider = None
    
    lines = first_page.split('\n')
    for i, line in enumerate(lines):
        if 'Collection Date' in line:
            for j in range(i+1, min(i+6, len(lines))):
                date_match = re.match(r'(\d{2}/\d{2}/\d{4})', lines[j].strip())
                if date_match:
                    try:
                        collection_date = datetime.strptime(date_match.group(1), '%m/%d/%Y').date()
                    except ValueError:
                        pass
                    break
            break
    
    # Find facility
    for i, line in enumerate(lines):
        if 'Collection Facility' in line:
            for j in range(i+1, min(i+3, len(lines))):
                fac = lines[j].strip()
                if fac and not fac.startswith('Lab ') and not fac.startswith('DISCLAIMER'):
                    facility = fac
                    break
            break
    
    # Find ordering provider
    for i, line in enumerate(lines):
        if 'Ordering Provider' in line:
            for j in range(i+1, min(i+5, len(lines))):
                prov = lines[j].strip()
                if prov and re.match(r'[A-Z][a-z]', prov):
                    provider = prov
                    break
            break
    
    if not collection_date:
        print(f"  WARNING: Could not find collection date in {os.path.basename(pdf_path)}")
        doc.close()
        return results
    
    # Parse all pages for test results
    # We'll use table extraction for better accuracy
    for page_idx in range(doc.page_count):
        page = doc[page_idx]
        text = page.get_text()
        page_lines = text.split('\n')
        
        i = 0
        while i < len(page_lines):
            line = page_lines[i].strip()
            
            # Look for CODE pattern (4-digit number at start of a result block)
            code_match = re.match(r'^(\d{4})\s*$', line)
            if code_match:
                # Next line(s) should be the test name
                test_name_parts = []
                j = i + 1
                while j < len(page_lines):
                    next_line = page_lines[j].strip()
                    # Stop if we hit a result value pattern or another code
                    if re.match(r'^[\d<>].*$', next_line) and not re.match(r'^\d{4}$', next_line):
                        break
                    if re.match(r'^(Error|TNP|CANC|QNS|Nonreactive|Reactive|Negative|Positive)', next_line, re.I):
                        break
                    if next_line and not re.match(r'^\d{4}$', next_line):
                        test_name_parts.append(next_line)
                    else:
                        break
                    j += 1
                
                if not test_name_parts:
                    i += 1
                    continue
                
                test_name_raw = ' '.join(test_name_parts)
                
                # Next should be result
                result_str = ""
                unit_str = ""
                range_str = ""
                
                if j < len(page_lines):
                    result_str = page_lines[j].strip()
                    j += 1
                
                # Unit line
                if j < len(page_lines):
                    candidate = page_lines[j].strip()
                    # Units typically contain / or specific unit strings
                    if candidate and not re.match(r'^\d{4}$', candidate) and not candidate.startswith('['):
                        if any(u in candidate for u in ['/', '%', 'g', 'mg', 'mL', 'mEq', 'pg', 'ng', 
                                                         'ug', 'U/', 'Cells', 'fL', 'sq ', 'Years',
                                                         'Calc', 'mmol', 'IU', 'x 10']):
                            unit_str = candidate
                            j += 1
                        elif candidate in ('Final', 'Preliminary'):
                            pass  # Status, no unit
                
                # Reference range
                if j < len(page_lines):
                    candidate = page_lines[j].strip()
                    range_match = re.match(r'([\d.]+)\s*-\s*$', candidate)
                    if range_match:
                        # Range spans two lines: "46.00 -" and "116.00"
                        range_part1 = candidate
                        j += 1
                        if j < len(page_lines):
                            range_part2 = page_lines[j].strip()
                            range_str = range_part1 + ' ' + range_part2
                            j += 1
                    elif re.match(r'[\d.]+\s*-\s*[\d.]+', candidate):
                        range_str = candidate
                        j += 1
                
                # Parse the values
                test_name = normalize_test_name(test_name_raw)
                value, value_string, is_high, is_low = parse_value_and_flags(result_str)
                ref_low, ref_high = parse_reference_range(range_str)
                
                # Determine if abnormal
                is_abnormal = None
                if is_high or is_low:
                    is_abnormal = True
                elif value is not None and ref_low is not None and ref_high is not None:
                    is_abnormal = value < ref_low or value > ref_high
                
                # Skip non-clinical entries
                skip_tests = {'AGE', 'AMPADJ', 'AMPUTATE FACTOR', 'ACTUAL DAYS/WEEK TREATED',
                              'ACTUAL DAYS/WEEK', 'BSA DUBOIS', 'BSA', 'BLOOD FLOW-QWB',
                              'BLOOD FLOW', 'IBW', 'SBW'}
                if test_name_raw.strip().upper() in skip_tests:
                    i = j
                    continue
                
                # Skip if no useful value
                if value is None and value_string in (None, 'Error', '', 'TNP', 'CANC', 'QNS'):
                    i = j
                    continue
                
                category = get_category(test_name)
                
                results.append({
                    'test_date': collection_date,
                    'test_name': test_name,
                    'value': value,
                    'value_string': value_string,
                    'unit': unit_str if unit_str else None,
                    'reference_range_low': ref_low,
                    'reference_range_high': ref_high,
                    'is_abnormal': is_abnormal,
                    'performing_lab': facility,
                    'ordering_provider': provider,
                    'category': category,
                })
                
                i = j
                continue
            
            i += 1
    
    doc.close()
    return results


# ── IDT Worksheet Parser (September format) ───────────────────────────────────
def parse_idt_worksheet(pdf_path):
    """
    Parse DaVita IDT Patient Profile Worksheet format.
    This has a summary table with categories and 3 months of data.
    """
    doc = fitz.open(pdf_path)
    results = []
    
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    
    lines = text.split('\n')
    
    # Find category sections and data
    current_category = None
    month_columns = []  # [(month_name, year)]
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Detect category headers like "ANEMIA", "MBD", "ADEQUACY", "NUTRITION"
        if line in ('ANEMIA', 'MBD', 'ADEQUACY', 'NUTRITION', 'INFECTIOUS DISEASE',
                     'HEPATITIS', 'HEMATOLOGY', 'OTHER'):
            current_category = line
            # Next line should have month columns
            month_cols = []
            j = i + 1
            while j < len(lines) and len(month_cols) < 3:
                month_line = lines[j].strip()
                month_match = re.match(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{4})', month_line)
                if month_match:
                    month_cols.append((month_match.group(1), int(month_match.group(2))))
                j += 1
            
            if month_cols:
                month_columns = month_cols
            i = j
            continue
        
        # Detect test name with unit in parentheses, e.g., "HEMOGLOBIN (g/dL)"
        test_match = re.match(r'^([A-Z][A-Z\s/\-\(\)0-9.]+?)(?:\s*\(([^)]+)\))?\s*$', line)
        if test_match and current_category and month_columns:
            test_name_raw = test_match.group(1).strip()
            unit = test_match.group(2)
            
            # Skip non-clinical
            if test_name_raw in ('AGE', 'BSA DUBOIS', 'BLOOD FLOW-QWB', 'AMPADJ',
                                  'HEMOGLOBIN MID', 'HEMOGLOBIN-POST'):
                i += 1
                continue
            
            test_name = normalize_test_name(test_name_raw)
            category_map = {
                'ANEMIA': 'Hematology',
                'MBD': 'Mineral & Bone',
                'ADEQUACY': 'Kidney Function',
                'NUTRITION': 'Electrolytes',
                'INFECTIOUS DISEASE': 'Infectious Disease',
            }
            category = category_map.get(current_category, get_category(test_name))
            
            # Next lines should have values and dates for each month column
            for col_idx, (month_name, year) in enumerate(month_columns):
                j = i + 1 + col_idx * 2  # rough estimate; values alternate with dates
                
                # Look for value followed by date in parentheses
                # Values appear as: "13.2\n(09/03)\n12.4\n(08/13)\n12.8\n(07/17)"
                pass  # Complex multi-column parsing handled below
            
            # Simpler approach: collect next N lines and parse value (date) pairs
            value_lines = []
            j = i + 1
            while j < len(lines) and len(value_lines) < len(month_columns) * 2 + 3:
                vl = lines[j].strip()
                if not vl:
                    j += 1
                    continue
                # Stop at next test name or category
                if re.match(r'^[A-Z][A-Z\s/\-]+(?:\s*\([^)]+\))?\s*$', vl) and vl not in ('-',):
                    if len(value_lines) >= len(month_columns):
                        break
                value_lines.append(vl)
                j += 1
            
            # Parse paired value + (date) entries
            val_idx = 0
            for col_idx, (month_name, year) in enumerate(month_columns):
                if val_idx >= len(value_lines):
                    break
                
                val_str = value_lines[val_idx]
                val_idx += 1
                
                # Check for date in parentheses on next line
                test_date = None
                if val_idx < len(value_lines):
                    date_match = re.match(r'\((\d{2}/\d{2})\)', value_lines[val_idx])
                    if date_match:
                        month_day = date_match.group(1)
                        try:
                            test_date = datetime.strptime(f"{month_day}/{year}", "%m/%d/%Y").date()
                        except ValueError:
                            pass
                        val_idx += 1
                
                if not test_date:
                    # Construct date from month column header
                    month_num = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                                 'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                    mn = month_num.get(month_name, 1)
                    test_date = date(year, mn, 1)
                
                if val_str in ('-', 'N/A', 'Error', ''):
                    continue
                
                value, value_string, is_high, is_low = parse_value_and_flags(val_str)
                if value is None and not value_string:
                    continue
                
                is_abnormal = True if (is_high or is_low) else None
                
                results.append({
                    'test_date': test_date,
                    'test_name': test_name,
                    'value': value,
                    'value_string': value_string,
                    'unit': unit,
                    'reference_range_low': None,
                    'reference_range_high': None,
                    'is_abnormal': is_abnormal,
                    'performing_lab': 'DaVita Labs',
                    'ordering_provider': 'Desai, Anand MD',
                    'category': category,
                })
            
            i = j if j > i + 1 else i + 1
            continue
        
        i += 1
    
    doc.close()
    return results


def is_idt_worksheet(pdf_path):
    """Check if PDF is an IDT Patient Profile Worksheet rather than a standard lab report."""
    doc = fitz.open(pdf_path)
    text = doc[0].get_text()[:1000]
    doc.close()
    return 'IDT Patient Profile' in text or 'MONTHLY LABS' in text or 'Include Sections' in text


def insert_results(conn, results, user_id):
    """Insert parsed lab results into the database."""
    if not results:
        return 0
    
    records = []
    for r in results:
        records.append((
            user_id,
            r['test_date'],
            r['test_name'],
            None,  # loinc_code
            r.get('category'),
            r.get('value'),
            r.get('value_string'),
            r.get('unit'),
            r.get('reference_range_low'),
            r.get('reference_range_high'),
            r.get('is_abnormal'),
            'final',
            r.get('ordering_provider'),
            r.get('performing_lab'),
            None,  # notes
            datetime.now(),  # created_at
        ))
    
    cur = conn.cursor()
    insert_sql = """
        INSERT INTO lab_results (
            user_id, test_date, test_name, loinc_code, category,
            value, value_string, unit, reference_range_low, reference_range_high,
            is_abnormal, status, ordering_provider, performing_lab, notes,
            created_at
        ) VALUES %s
    """
    execute_values(cur, insert_sql, records, page_size=500)
    conn.commit()
    cur.close()
    return len(records)


def main():
    print("=" * 60)
    print("ALAFIA — PDF Lab Results Import")
    print(f"Source: {PDF_DIR}")
    print("=" * 60)
    
    # List PDFs
    pdfs = sorted([f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf')])
    print(f"\nFound {len(pdfs)} PDF files")
    
    # Connect to DB
    print("\nConnecting to database...")
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    print("  Connected successfully")
    
    # Check existing lab count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM lab_results WHERE user_id = %s", (USER_ID,))
    existing_count = cur.fetchone()[0]
    print(f"  Existing lab results: {existing_count}")
    
    # Get existing dates to avoid true duplicates
    cur.execute("SELECT DISTINCT test_date FROM lab_results WHERE user_id = %s", (USER_ID,))
    existing_dates = {row[0] for row in cur.fetchall()}
    cur.close()
    
    total_inserted = 0
    total_skipped = 0
    total_parsed = 0
    
    for pdf_name in pdfs:
        pdf_path = os.path.join(PDF_DIR, pdf_name)
        print(f"\n{'─' * 50}")
        print(f"  Processing: {pdf_name}")
        
        try:
            if is_idt_worksheet(pdf_path):
                print("  Format: IDT Patient Profile Worksheet")
                results = parse_idt_worksheet(pdf_path)
            else:
                print("  Format: Standard Lab Draw Report")
                results = parse_standard_report(pdf_path)
            
            total_parsed += len(results)
            
            # Filter out results for dates we already have (from Excel import)
            new_results = [r for r in results if r['test_date'] not in existing_dates]
            skipped = len(results) - len(new_results)
            
            if skipped > 0:
                print(f"  Parsed: {len(results)} results ({skipped} skipped — date already in DB)")
            else:
                print(f"  Parsed: {len(results)} results")
            
            if new_results:
                # Show date and sample tests
                dates = sorted(set(r['test_date'] for r in new_results))
                for d in dates:
                    day_results = [r for r in new_results if r['test_date'] == d]
                    sample = [r['test_name'] for r in day_results[:5]]
                    print(f"    {d}: {len(day_results)} tests (e.g. {', '.join(sample)})")
                
                count = insert_results(conn, new_results, USER_ID)
                total_inserted += count
                # Track these dates as now existing
                for r in new_results:
                    existing_dates.add(r['test_date'])
                print(f"  ✓ Inserted {count} new lab results")
            else:
                total_skipped += len(results)
                print(f"  → Skipped (all dates already imported)")
                
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    # Final summary
    print(f"\n{'=' * 60}")
    print(f"IMPORT COMPLETE")
    print(f"  Total PDFs processed: {len(pdfs)}")
    print(f"  Total results parsed: {total_parsed}")
    print(f"  New results inserted: {total_inserted}")
    print(f"  Skipped (existing):   {total_skipped}")
    
    # Final count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM lab_results WHERE user_id = %s", (USER_ID,))
    final_count = cur.fetchone()[0]
    cur.execute("SELECT MIN(test_date), MAX(test_date) FROM lab_results WHERE user_id = %s", (USER_ID,))
    date_range = cur.fetchone()
    cur.close()
    
    print(f"\n  Total lab results in DB: {final_count}")
    print(f"  Date range: {date_range[0]} to {date_range[1]}")
    
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
