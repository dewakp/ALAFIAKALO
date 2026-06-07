#!/usr/bin/env python3
"""
Parse DaVita HHD Flowsheet Excel files into structured CSVs.

Handles three formats:
  - 2017-2018 (Flowsheets.xlsx): older layout, column offset +1
  - 2023 (2023FlowSheets-ex.xlsx): same as 2024
  - 2024 (2024FlowSheets.xlsx): current layout
  - CSV (FlowsheetHomeCSV.csv): single-row summary (different structure)

Each sheet = one dialysis session with a form-like layout (~76 rows × 36 cols).
Extracts:
  1. Session summary (pre/post vitals, weights, prescription, totals)
  2. Intra-dialysis readings (time-series BP, UF, flow rates, pressures)
  3. Medications administered
  4. Vomit log sheets (2023/2024 files)

Output:
  - data/raw/excel/flowsheet_sessions.csv    (one row per session)
  - data/raw/excel/flowsheet_readings.csv    (one row per intra-dialysis reading)
  - data/raw/excel/flowsheet_vomit_log.csv   (vomit events from dedicated sheets)
"""

import pandas as pd
import numpy as np
import os
import re
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / 'data' / 'raw' / 'excel'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════

def safe_float(val):
    """Convert a value to float, handling strings with units."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    # Remove common suffixes
    for suffix in [' kg', ' Lb', ' lb', ' L', ' mEq', ' ml', ' mg', ' mcg',
                   ' SQ', ' mins', ' min', '%', ' ml/t']:
        s = s.replace(suffix, '')
    s = s.replace(',', '')
    # Handle tilde or other non-numeric
    if s in ['~', '-', '', 'Y/N', 'NO', 'YES', 'N', 'Y']:
        return np.nan
    try:
        return float(s)
    except (ValueError, TypeError):
        return np.nan


def parse_time(val):
    """Parse a time value from Excel (could be datetime, time string, etc.)."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    # Handle Excel datetime (1900-01-01 HH:MM:SS)
    if '1900-01-01' in s:
        try:
            return pd.Timestamp(s).strftime('%H:%M')
        except:
            pass
    # Handle HH:MM:SS
    m = re.match(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def parse_date_from_sheet_name(sheet_name, file_year_hint=None):
    """
    Parse a date from sheet name formats:
      'July 1-2017', 'Nov 14-2018', '01-02-2024', '03-19-2023'
    """
    s = sheet_name.strip()

    # Format: MM-DD-YYYY
    m = re.match(r'(\d{1,2})-(\d{1,2})-(\d{4})', s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    # Format: Month DD-YYYY (e.g., 'July 1-2017', 'Nov 14-2018')
    m = re.match(r'(\w+)\s+(\d{1,2})-(\d{4})', s)
    if m:
        month_str, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        for fmt in ['%B', '%b']:
            try:
                month = datetime.strptime(month_str, fmt).month
                return datetime(year, month, day)
            except ValueError:
                continue

    # Format: 'Marc 23-2018', 'Sep 17.18-2017' — handle typos
    m = re.match(r'(\w+)\s+(\d{1,2})[\.\-](\d{4})', s)
    if m:
        month_str, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        # Fix common typos
        month_str = month_str.replace('Marc', 'Mar')
        for fmt in ['%B', '%b']:
            try:
                month = datetime.strptime(month_str, fmt).month
                return datetime(year, month, day)
            except ValueError:
                continue

    # Handle 'Apr 14' (no year) — use hint
    m = re.match(r'(\w+)\s+(\d{1,2})$', s)
    if m and file_year_hint:
        month_str, day = m.group(1), int(m.group(2))
        for fmt in ['%B', '%b']:
            try:
                month = datetime.strptime(month_str, fmt).month
                return datetime(file_year_hint, month, day)
            except ValueError:
                continue

    # Handle special case 'Sep 17.18-2017' (day range)
    m = re.match(r'(\w+)\s+(\d{1,2})\.\d+-(\d{4})', s)
    if m:
        month_str, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        for fmt in ['%B', '%b']:
            try:
                month = datetime.strptime(month_str, fmt).month
                return datetime(year, month, day)
            except ValueError:
                continue

    return None


def detect_format(df):
    """
    Detect which format a flowsheet sheet uses.
    Returns 'new' (2023/2024) or 'old' (2017-2018).
    The key difference: old format has col offset +1.
    """
    # Check row 0 or nearby for 'Davita' label
    # New format: row 0, col 0 = 'Davita'
    # Old format: row 0, col 1 = 'Davita' (or similar offset)
    r0c0 = str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else ''
    r10c0 = str(df.iloc[10, 0]) if 10 < len(df) and pd.notna(df.iloc[10, 0]) else ''
    r10c1 = str(df.iloc[10, 1]) if 10 < len(df) and pd.notna(df.iloc[10, 1]) else ''

    # In new format R10C0 = 'Sitting BP', old format R10C1 = 'Sitting BP'
    if 'Sitting BP' in r10c0:
        return 'new'
    elif 'Sitting BP' in r10c1:
        return 'old'
    # Fallback: check date cell position
    r3c6 = str(df.iloc[3, 6]) if 3 < len(df) and pd.notna(df.iloc[3, 6]) else ''
    r3c7 = str(df.iloc[3, 7]) if 3 < len(df) and pd.notna(df.iloc[3, 7]) else ''
    if r3c6 and r3c6 != 'nan':
        return 'old'
    if r3c7 and r3c7 != 'nan':
        return 'new'
    return 'new'  # default


# ═══════════════════════════════════════════════════════════
# Parse one session sheet
# ═══════════════════════════════════════════════════════════

def parse_session(df, sheet_name, source_file, file_year_hint=None):
    """
    Parse a single flowsheet session from one Excel sheet.
    Returns (session_dict, list_of_reading_dicts).
    """
    fmt = detect_format(df)
    # Column offset: old format shifts most data columns by +1
    o = 1 if fmt == 'old' else 0

    session = {'source_file': source_file, 'sheet_name': sheet_name, 'format': fmt}

    # ── Date ──
    date_from_sheet = parse_date_from_sheet_name(sheet_name, file_year_hint)

    # Also try to read date from the cell
    date_cell = df.iloc[3, 7] if fmt == 'new' else df.iloc[3, 6]
    cell_date = None
    if pd.notna(date_cell):
        try:
            cell_date = pd.to_datetime(date_cell)
        except:
            pass

    # Priority: sheet name date is MORE reliable (Excel often misreads date cells).
    # Only use cell date for new-format files where dates are properly formatted.
    if date_from_sheet:
        session['date'] = date_from_sheet.strftime('%Y-%m-%d')
    elif cell_date is not None and cell_date.year >= 2016:
        session['date'] = cell_date.strftime('%Y-%m-%d')
    else:
        session['date'] = None

    # ── Flow Fraction ──
    session['flow_fraction'] = safe_float(df.iloc[5, 7] if fmt == 'new' else df.iloc[5, 7])

    # ── Day of Week ──
    dow_val = df.iloc[6, 11] if fmt == 'new' else df.iloc[6, 12] if 12 < df.shape[1] else np.nan
    session['day_of_week'] = str(dow_val).strip() if pd.notna(dow_val) else None

    # ── Pre-Treatment Vitals ──
    # New: R10 C1=sys, C2=dia, C3=pulse
    # Old: R10 C3=sys, C4=dia (pulse may be separate)
    if fmt == 'new':
        session['pre_bp_sys'] = safe_float(df.iloc[10, 1])
        session['pre_bp_dia'] = safe_float(df.iloc[10, 2])
        session['pre_pulse'] = safe_float(df.iloc[10, 3])
    else:
        session['pre_bp_sys'] = safe_float(df.iloc[10, 3])
        session['pre_bp_dia'] = safe_float(df.iloc[10, 4])
        session['pre_pulse'] = np.nan  # not consistently in old format R10

    # Standing BP
    if fmt == 'new':
        session['pre_stand_bp_sys'] = safe_float(df.iloc[11, 1])
        session['pre_stand_bp_dia'] = safe_float(df.iloc[11, 2])
    else:
        session['pre_stand_bp_sys'] = safe_float(df.iloc[11, 3])
        session['pre_stand_bp_dia'] = safe_float(df.iloc[11, 4])

    # Temperature
    session['pre_temp'] = safe_float(df.iloc[12, 2] if fmt == 'new' else df.iloc[12, 3])
    temp_unit = str(df.iloc[12, 3] if fmt == 'new' else df.iloc[12, 4]) if pd.notna(
        df.iloc[12, 3] if fmt == 'new' else df.iloc[12, 4]) else 'F'
    session['pre_temp_unit'] = temp_unit.strip() if temp_unit not in ['nan', ''] else 'F'

    # Weights
    prev_post_wt = safe_float(df.iloc[13, 2] if fmt == 'new' else df.iloc[13, 3])
    today_wt = safe_float(df.iloc[14, 2] if fmt == 'new' else df.iloc[14, 3])
    dry_wt = safe_float(df.iloc[15, 2] if fmt == 'new' else df.iloc[15, 3])
    fluid_remove = safe_float(df.iloc[16, 2] if fmt == 'new' else df.iloc[16, 3])

    wt_unit = str(df.iloc[14, 3] if fmt == 'new' else df.iloc[14, 4])
    wt_unit = wt_unit.strip() if pd.notna(wt_unit) and wt_unit not in ['nan', ''] else 'kg'

    session['previous_post_weight'] = prev_post_wt
    session['today_weight'] = today_wt
    session['dry_weight'] = dry_wt
    session['fluid_to_remove'] = fluid_remove
    session['weight_unit'] = wt_unit

    # Convert lbs to kg if needed
    if wt_unit.lower() in ['lb', 'lbs']:
        for k in ['previous_post_weight', 'today_weight', 'dry_weight', 'fluid_to_remove']:
            if pd.notna(session[k]) and k != 'fluid_to_remove':
                session[f'{k}_kg'] = session[k] * 0.453592
            elif k == 'fluid_to_remove':
                session[f'{k}_kg'] = session[k] * 0.453592 if pd.notna(session[k]) else np.nan
            else:
                session[f'{k}_kg'] = np.nan
    else:
        for k in ['previous_post_weight', 'today_weight', 'dry_weight', 'fluid_to_remove']:
            session[f'{k}_kg'] = session[k]

    # ── Pre-treatment data (right side) ──
    # Shortness of breath, Swelling, Hospital visits
    sob_val = df.iloc[10, 7] if fmt == 'new' else df.iloc[10, 9]
    session['pre_shortness_of_breath'] = str(sob_val).strip() if pd.notna(sob_val) else None

    # ── Dialysis Prescription ──
    volume_val = df.iloc[18, 8] if fmt == 'new' else df.iloc[18, 10]
    session['dialysate_volume_L'] = safe_float(volume_val)

    lactate_val = df.iloc[19, 8] if fmt == 'new' else df.iloc[19, 10]
    session['dialysate_lactate'] = safe_float(lactate_val)

    k_val = df.iloc[19, 10] if fmt == 'new' else df.iloc[19, 12] if 12 < df.shape[1] else np.nan
    session['dialysate_k'] = safe_float(k_val)

    sak_val = df.iloc[20, 8] if fmt == 'new' else df.iloc[20, 10]
    session['sak_number'] = safe_float(sak_val)

    bfr_text = df.iloc[21, 9] if fmt == 'new' else df.iloc[21, 10]
    session['prescribed_blood_flow_rate'] = str(bfr_text).strip() if pd.notna(bfr_text) else None

    # ── Medications ──
    meds = {}
    # Sodium Citrate (row 23), Epogen (row 24), Venofer (row 26), Doxercalcif (row 27)
    med_rows = [
        (23, 'sodium_citrate'),
        (24, 'epogen'),
        (26, 'venofer'),
        (27, 'doxercalciferol'),
    ]
    for row_idx, med_name in med_rows:
        if row_idx < len(df):
            dose_col = 10 if fmt == 'new' else 12 if 12 < df.shape[1] else 10
            dose_val = df.iloc[row_idx, dose_col] if dose_col < df.shape[1] else np.nan
            if pd.notna(dose_val):
                meds[med_name] = str(dose_val).strip()
    session['medications'] = '; '.join(f'{k}={v}' for k, v in meds.items()) if meds else None

    # ── Intra-dialysis readings (rows 30-41 typically) ──
    readings = []
    reading_start = 30
    reading_end = 42  # row 42 is usually post-treatment or last reading
    if fmt == 'old':
        reading_start = 30
        reading_end = 42

    for r in range(reading_start, min(reading_end, len(df))):
        # Check if row has data (at least a time or BP value)
        time_val = df.iloc[r, 0]
        bp_sys = safe_float(df.iloc[r, 1])
        bp_dia = safe_float(df.iloc[r, 2])

        # Skip rows that are all NaN or zeros
        has_time = pd.notna(time_val) and str(time_val).strip() not in ['', '~', 'nan', 'AVERAGE']
        has_bp = (pd.notna(bp_sys) and bp_sys > 0) or (pd.notna(bp_dia) and bp_dia > 0)

        if not has_time and not has_bp:
            continue

        reading = {
            'session_date': session['date'],
            'reading_number': len(readings) + 1,
            'time': parse_time(time_val),
            'bp_sys': bp_sys if pd.notna(bp_sys) and bp_sys > 0 else np.nan,
            'bp_dia': bp_dia if pd.notna(bp_dia) and bp_dia > 0 else np.nan,
            'pulse': safe_float(df.iloc[r, 3]),
            'dialysate_rate': safe_float(df.iloc[r, 4]),
            'dialysate_volume': safe_float(df.iloc[r, 5]),
            'uf_rate': safe_float(df.iloc[r, 6]),
            'uf_volume': safe_float(df.iloc[r, 7]),
            'blood_flow_rate': safe_float(df.iloc[r, 8]),
            'arterial_pressure': safe_float(df.iloc[r, 9]),
            'venous_pressure': safe_float(df.iloc[r, 10]),
            'effluent_pressure': safe_float(df.iloc[r, 11]),
        }

        # Skip if zero BP and zero pulse (blank sentinel row)
        if (reading['bp_sys'] == 0 or pd.isna(reading['bp_sys'])) and \
           (reading['bp_dia'] == 0 or pd.isna(reading['bp_dia'])) and \
           (reading['pulse'] == 0 or pd.isna(reading['pulse'])):
            continue

        readings.append(reading)

    session['n_readings'] = len(readings)

    # ── Average row ──
    avg_row = None
    for r in [44, 43, 45]:
        if r < len(df) and str(df.iloc[r, 0]).strip() == 'AVERAGE':
            avg_row = r
            break
    if avg_row is not None:
        session['avg_bp_sys'] = safe_float(df.iloc[avg_row, 1])
        session['avg_bp_dia'] = safe_float(df.iloc[avg_row, 2])
        session['avg_pulse'] = safe_float(df.iloc[avg_row, 3])
        session['avg_dialysate_rate'] = safe_float(df.iloc[avg_row, 4])
        session['avg_blood_flow_rate'] = safe_float(df.iloc[avg_row, 8])

    # ── Post-Treatment Vitals ──
    # Find post-treatment section (usually row 47-52 new, 42-46 old)
    post_row_base = None
    for r in range(40, min(55, len(df))):
        cell = str(df.iloc[r, 0]) if pd.notna(df.iloc[r, 0]) else ''
        if 'Post Treatment' in cell or 'Post-Treatment' in cell:
            post_row_base = r
            break

    if post_row_base is not None:
        bp_row = post_row_base + 1
        if bp_row < len(df):
            if fmt == 'new':
                session['post_bp_sys'] = safe_float(df.iloc[bp_row, 1])
                session['post_bp_dia'] = safe_float(df.iloc[bp_row, 2])
                session['post_pulse'] = safe_float(df.iloc[bp_row, 3])
            else:
                session['post_bp_sys'] = safe_float(df.iloc[bp_row, 2])
                session['post_bp_dia'] = safe_float(df.iloc[bp_row, 3])
                # Old format pulse might be at col 5
                pulse_val = safe_float(df.iloc[bp_row, 5])
                session['post_pulse'] = pulse_val

            # Shortness of breath post
            sob_post = df.iloc[bp_row, 8] if 8 < df.shape[1] else np.nan
            session['post_shortness_of_breath'] = str(sob_post).strip() if pd.notna(sob_post) else None

        # Standing BP post
        stand_row = post_row_base + 2
        if stand_row < len(df):
            if fmt == 'new':
                session['post_stand_bp_sys'] = safe_float(df.iloc[stand_row, 1])
                session['post_stand_bp_dia'] = safe_float(df.iloc[stand_row, 2])
            else:
                session['post_stand_bp_sys'] = safe_float(df.iloc[stand_row, 2])
                session['post_stand_bp_dia'] = safe_float(df.iloc[stand_row, 3])
                # Old format standing pulse at col 5
                session['post_stand_pulse'] = safe_float(df.iloc[stand_row, 5])

            # Swelling post
            swell = df.iloc[stand_row, 8] if 8 < df.shape[1] else np.nan
            session['post_swelling'] = str(swell).strip() if pd.notna(swell) else None

        # Temp + Post Weight
        temp_row = post_row_base + 3
        if temp_row < len(df):
            session['post_temp'] = safe_float(df.iloc[temp_row, 1] if fmt == 'new' else df.iloc[temp_row, 2])
            post_wt = safe_float(df.iloc[temp_row, 5])
            session['post_weight'] = post_wt

            # Convert post weight to kg if the file uses lbs
            if wt_unit.lower() in ['lb', 'lbs']:
                session['post_weight_kg'] = post_wt * 0.453592 if pd.notna(post_wt) else np.nan
            else:
                session['post_weight_kg'] = post_wt

            # Digestion problem
            dig = df.iloc[temp_row, 8] if 8 < df.shape[1] else np.nan
            session['post_digestion_problem'] = str(dig).strip() if pd.notna(dig) else None

        # Totals row
        totals_row = post_row_base + 4
        totals_data_row = post_row_base + 5  # values are often one row below labels
        if totals_row < len(df):
            # Try to get total time from the label row or data row
            total_time = df.iloc[totals_row, 2] if 2 < df.shape[1] else np.nan
            if pd.isna(total_time) and totals_data_row < len(df):
                total_time = df.iloc[totals_data_row, 2]
            session['total_time'] = parse_time(total_time)

            # Total dialysate
            for col in [4, 6]:
                val = safe_float(df.iloc[totals_data_row, col]) if totals_data_row < len(df) else np.nan
                if pd.notna(val) and val > 0:
                    session['total_dialysate_L'] = val
                    break
            else:
                # Try from totals_row
                for col in [4, 6]:
                    val = safe_float(df.iloc[totals_row, col]) if totals_row < len(df) else np.nan
                    if pd.notna(val) and val > 0:
                        session['total_dialysate_L'] = val
                        break

            # Total UF
            for col in [6, 4]:
                val = safe_float(df.iloc[totals_data_row, col]) if totals_data_row < len(df) else np.nan
                if pd.notna(val) and 0 < val < 10:  # UF is typically 0-5 kg
                    session['total_uf_kg'] = val
                    break

            # Total BVP
            bvp_val = safe_float(df.iloc[totals_data_row, 10]) if totals_data_row < len(df) and 10 < df.shape[1] else np.nan
            session['total_bvp'] = bvp_val

    # Compute derived fields
    if pd.notna(session.get('today_weight_kg')) and pd.notna(session.get('post_weight_kg')):
        session['weight_loss_kg'] = session['today_weight_kg'] - session['post_weight_kg']

    return session, readings


# ═══════════════════════════════════════════════════════════
# Parse vomit log sheets
# ═══════════════════════════════════════════════════════════

def parse_vomit_log(df, source_file):
    """Parse VomitLog/Vomit Log sheets."""
    records = []
    # These sheets have headers like: Vomit, _, Weight in Kg, _, _, Visual Content, Last Meal, ...
    # Data starts from row 1 or 2
    for r in range(1, len(df)):
        row = df.iloc[r]
        date_val = row.iloc[0] if pd.notna(row.iloc[0]) else None
        if date_val is None:
            continue
        try:
            date = pd.to_datetime(date_val)
        except:
            continue

        weight_pre = safe_float(row.iloc[2]) if 2 < len(row) else np.nan
        weight_post = safe_float(row.iloc[3]) if 3 < len(row) else np.nan
        visual = str(row.iloc[5]).strip() if 5 < len(row) and pd.notna(row.iloc[5]) else None
        last_meal = str(row.iloc[6]).strip() if 6 < len(row) and pd.notna(row.iloc[6]) else None

        records.append({
            'date': date.strftime('%Y-%m-%d'),
            'time': parse_time(row.iloc[1]) if 1 < len(row) else None,
            'weight_pre_kg': weight_pre,
            'weight_post_kg': weight_post,
            'weight_loss_kg': (weight_pre - weight_post) if pd.notna(weight_pre) and pd.notna(weight_post) else np.nan,
            'visual_content': visual,
            'last_meal': last_meal,
            'source_file': source_file,
        })

    return records


# ═══════════════════════════════════════════════════════════
# Main: Process all flowsheet files
# ═══════════════════════════════════════════════════════════

def main():
    files = [
        {
            'path': os.path.expanduser('~/Documents/Developer/WellnessScore/Flowsheets.xlsx'),
            'label': 'Flowsheets.xlsx (2017-2018)',
            'year_hint': 2018,
        },
        {
            'path': '/tmp/FlowsheetGermantown.xlsx',
            'label': 'FlowsheetGermantown.xlsx (2019-2022)',
            'year_hint': 2022,
        },
        {
            'path': os.path.expanduser('~/Documents/2023FlowSheets-ex.xlsx'),
            'label': '2023FlowSheets-ex.xlsx',
            'year_hint': 2023,
        },
        {
            'path': os.path.expanduser('~/Documents/Developer/data/2024FlowSheets.xlsx'),
            'label': '2024FlowSheets.xlsx',
            'year_hint': 2024,
        },
        {
            'path': '/tmp/2025FlowSheets.xlsx',
            'label': '2025FlowSheets.xlsx (OneDrive)',
            'year_hint': 2025,
        },
        {
            'path': '/tmp/2026FlowSheets.xlsx',
            'label': '2026FlowSheets.xlsx',
            'year_hint': 2026,
        },
    ]

    # Sheets to skip (non-session sheets)
    SKIP_SHEETS = {
        'Maintenance Log', 'Master', 'Dummy', 'Hospital', 'Davita',
        'AccessMaintenance', 'Access Maintenance',
        'Supplies Request', 'Supplies RAF', 'Supplies',
        'Cleaning Log', 'Summary',
        'VomitLog2021', 'VomitLog2022', 'VomitLog2023', 'Vomit Log',
    }

    all_sessions = []
    all_readings = []
    all_vomit = []
    errors = []

    for file_info in files:
        fpath = file_info['path']
        if not os.path.exists(fpath):
            print(f"  ⚠ File not found: {fpath}")
            continue

        fname = os.path.basename(fpath)
        print(f"\n{'='*60}")
        print(f"  Processing: {file_info['label']}")
        print(f"{'='*60}")

        try:
            xls = pd.ExcelFile(fpath)
        except Exception as e:
            print(f"  ✗ Cannot open file: {e}")
            continue

        sheets = xls.sheet_names
        session_sheets = [s for s in sheets if s not in SKIP_SHEETS]
        vomit_sheets = [s for s in sheets if s.lower().replace(' ', '').startswith('vomit')]

        print(f"  Total sheets: {len(sheets)}, Session sheets: {len(session_sheets)}, Vomit sheets: {len(vomit_sheets)}")

        # Parse vomit logs
        for vs in vomit_sheets:
            try:
                vdf = pd.read_excel(fpath, sheet_name=vs, header=None)
                vomit_records = parse_vomit_log(vdf, fname)
                all_vomit.extend(vomit_records)
                print(f"  📋 Vomit log '{vs}': {len(vomit_records)} events")
            except Exception as e:
                errors.append(f"Vomit {fname}/{vs}: {e}")

        # Load ALL session sheets in one pass (avoids re-opening the workbook 300+ times)
        print(f"  Loading all {len(session_sheets)} session sheets (this may take a moment)...")
        try:
            all_sheet_data = pd.read_excel(fpath, sheet_name=session_sheets, header=None)
        except Exception as e:
            print(f"  ✗ Failed to bulk-load sheets: {e}")
            continue

        # Parse session sheets
        parsed = 0
        skipped = 0
        for sheet in session_sheets:
            if sheet.lower().replace(' ', '').startswith('vomit'):
                continue  # already handled

            try:
                sdf = all_sheet_data[sheet]

                # Quick validation: must have at least 30 rows (minimum for a flowsheet)
                if len(sdf) < 25:
                    skipped += 1
                    continue

                session, readings = parse_session(sdf, sheet, fname, file_info['year_hint'])

                if session.get('date') is None:
                    # Try harder with the sheet name
                    date = parse_date_from_sheet_name(sheet, file_info['year_hint'])
                    if date:
                        session['date'] = date.strftime('%Y-%m-%d')
                    else:
                        errors.append(f"No date: {fname}/{sheet}")
                        skipped += 1
                        continue

                all_sessions.append(session)
                all_readings.extend(readings)
                parsed += 1

            except Exception as e:
                errors.append(f"Session {fname}/{sheet}: {e}")
                skipped += 1

        print(f"  ✓ Parsed: {parsed} sessions, {skipped} skipped")

    # ── Parse CSV file ──
    csv_path = os.path.expanduser('~/Documents/FlowsheetHomeCSV.csv')
    if os.path.exists(csv_path):
        print(f"\n{'='*60}")
        print(f"  Processing: FlowsheetHomeCSV.csv")
        print(f"{'='*60}")
        try:
            csv_df = pd.read_csv(csv_path, header=None)
            # This is a single sheet in CSV form — same format as Excel sheets
            if len(csv_df) >= 25:
                session, readings = parse_session(csv_df, 'CSV_Sheet', 'FlowsheetHomeCSV.csv')
                if session.get('date'):
                    all_sessions.append(session)
                    all_readings.extend(readings)
                    print(f"  ✓ Parsed: 1 session")
                else:
                    print(f"  ⚠ No date found in CSV")
        except Exception as e:
            errors.append(f"CSV: {e}")

    # ── Save results ──
    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*60}")

    # Sessions
    df_sessions = pd.DataFrame(all_sessions)
    if not df_sessions.empty:
        df_sessions['date'] = pd.to_datetime(df_sessions['date'], errors='coerce')
        df_sessions = df_sessions.sort_values('date').reset_index(drop=True)

        # ── Data cleaning ──
        # Remove sessions with no date
        n_nodate = df_sessions['date'].isna().sum()
        df_sessions = df_sessions.dropna(subset=['date'])

        # Fix known date typo: "May 21-2013" is actually 2018 (in the 2017-2018 workbook)
        mask_2013 = df_sessions['date'].dt.year == 2013
        if mask_2013.any():
            df_sessions.loc[mask_2013, 'date'] = df_sessions.loc[mask_2013, 'date'].apply(
                lambda d: d.replace(year=2018)
            )
            print(f"    ⚠ Fixed {mask_2013.sum()} session(s) with year=2013 → 2018")

        # Clip obvious outlier BPs (dia > 200 is clearly wrong)
        for col in ['pre_bp_dia', 'post_bp_dia']:
            if col in df_sessions.columns:
                df_sessions.loc[df_sessions[col] > 200, col] = np.nan
        # Remove zero BPs (sentinel values)
        for col in ['pre_bp_sys', 'pre_bp_dia', 'post_bp_sys', 'post_bp_dia']:
            if col in df_sessions.columns:
                df_sessions.loc[df_sessions[col] == 0, col] = np.nan
        # Remove physiologically impossible BPs (sys < 45, dia < 20)
        for col in ['pre_bp_sys', 'post_bp_sys']:
            if col in df_sessions.columns:
                df_sessions.loc[df_sessions[col] < 45, col] = np.nan
        for col in ['pre_bp_dia', 'post_bp_dia']:
            if col in df_sessions.columns:
                df_sessions.loc[df_sessions[col] < 20, col] = np.nan
        # Remove impossible weights (< 30 kg for an adult)
        for col in ['today_weight', 'edw', 'pre_weight', 'post_weight']:
            if col in df_sessions.columns:
                df_sessions.loc[df_sessions[col] < 30, col] = np.nan
        # Also clean kg-converted columns
        for col in ['today_weight_kg', 'dry_weight_kg', 'previous_post_weight_kg',
                     'post_weight_kg', 'fluid_to_remove_kg']:
            if col in df_sessions.columns:
                df_sessions.loc[df_sessions[col] < 30, col] = np.nan
        # Recalc weight_loss_kg after cleaning
        if 'today_weight_kg' in df_sessions.columns and 'post_weight_kg' in df_sessions.columns:
            df_sessions['weight_loss_kg'] = df_sessions['today_weight_kg'] - df_sessions['post_weight_kg']

        # Remove duplicate dates (keep first)
        n_before = len(df_sessions)
        df_sessions = df_sessions.drop_duplicates(subset='date', keep='first')
        n_dupes = n_before - len(df_sessions)

        out_path = OUTPUT_DIR / 'flowsheet_sessions.csv'
        df_sessions.to_csv(out_path, index=False)
        print(f"\n  Sessions: {len(df_sessions):,} saved → {out_path.name}")
        print(f"    Date range: {df_sessions['date'].min().date()} → {df_sessions['date'].max().date()}")
        print(f"    Duplicates removed: {n_dupes}")

        # Year breakdown
        year_counts = df_sessions['date'].dt.year.value_counts().sort_index()
        for year, count in year_counts.items():
            print(f"    {year}: {count:>4} sessions")
    else:
        print("\n  ⚠ No sessions parsed!")

    # Readings
    df_readings = pd.DataFrame(all_readings)
    if not df_readings.empty:
        out_path = OUTPUT_DIR / 'flowsheet_readings.csv'
        df_readings.to_csv(out_path, index=False)
        print(f"\n  Readings: {len(df_readings):,} saved → {out_path.name}")

    # Vomit log
    df_vomit = pd.DataFrame(all_vomit)
    if not df_vomit.empty:
        out_path = OUTPUT_DIR / 'flowsheet_vomit_log.csv'
        df_vomit.to_csv(out_path, index=False)
        print(f"\n  Vomit events: {len(df_vomit):,} saved → {out_path.name}")

    # Errors
    if errors:
        print(f"\n  ⚠ Errors ({len(errors)}):")
        for e in errors[:20]:
            print(f"    - {e}")
        if len(errors) > 20:
            print(f"    ... and {len(errors)-20} more")

    print(f"\n{'='*60}")
    print(f"  Done! Output: {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
