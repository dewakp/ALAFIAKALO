#!/usr/bin/env python3
"""
Import ALAFIA.APP Firestore data into ALAFIA PostgreSQL.

Migration path: ALAFIA.APP (Firebase/Firestore) → ALAFIA (PostgreSQL)

Source: Firestore user sKhP73PXMQXL7uVnWq28Sm0p0Ts2 (developer@hntsolutions.com)
Target: ALAFIA user_id=1 (demo@alafia.app)

Collections imported:
  1. vitalsLog       → vitals_logs
  2. nutritionLog    → nutrition_logs (enriched w/ AI macros)
  3. medicationLog   → medication_logs (new table)
  4. eliminationLog  → bowel_movements + vomiting_logs + urination_logs
  5. symptomLog      → symptom_logs
  6. journalEntries  → mood_entries
  7. hemodialysisFlowsheets → therapy_sessions + intradialytic_readings
  8. labReports      → lab_results
  9. scheduledEvents → calendar_events
"""

import firebase_admin
from firebase_admin import credentials, firestore
import psycopg2

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _target import resolve_user, resolve_condition  # noqa: E402
from datetime import datetime, date, time, timedelta
import re
import traceback

SERVICE_ACCOUNT = '/Users/woleakpose/Downloads/alafia-9i0hh-firebase-adminsdk-fbsvc-fb3e9a5364.json'
FIREBASE_UID = 'sKhP73PXMQXL7uVnWq28Sm0p0Ts2'

DB_PARAMS = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'alafia',
    'user': 'alafia',
    'password': 'alafia'
}
ALAFIA_USER_ID = 1
# ── Target ────────────────────────────────────────────────────────────────
# USER_ID was hardcoded to a literal row id that exists in no database here.
# Resolve the patient by EMAIL instead — see scripts/_target.py. Test data
# belongs to developer@hntsolutions.com by convention.
#
#   USER_ID = resolve_user(conn, "developer@hntsolutions.com")
#
# Left as None so an accidental run fails loudly instead of writing clinical
# rows against the wrong patient.
CONDITION_ID = None


def parse_firestore_date(val):
    """Parse Firestore date field to Python date."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        # Try ISO format
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']:
            try:
                return datetime.strptime(val.split('T')[0] if 'T' in val else val, fmt.split('T')[0]).date()
            except ValueError:
                continue
    return None


def parse_firestore_time(val):
    """Parse Firestore time field to Python time."""
    if isinstance(val, time):
        return val
    if isinstance(val, datetime):
        return val.time()
    if isinstance(val, str):
        m = re.match(r'(\d{1,2}):(\d{2})', val)
        if m:
            h, mn = int(m.group(1)), int(m.group(2))
            if h < 24 and mn < 60:
                return time(h, mn)
    return None


def safe_int(val):
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_str(val, max_len=None):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if max_len:
        s = s[:max_len]
    return s


# ── Import functions ──────────────────────────────────────

def import_vitals(db, conn):
    """vitalsLog → vitals_logs"""
    docs = db.collection('users').document(FIREBASE_UID).collection('vitalsLog').get()
    cur = conn.cursor()

    # Dedup by date
    cur.execute("SELECT log_date FROM vitals_logs WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing = {row[0] for row in cur.fetchall()}

    imported = 0
    for doc in docs:
        d = doc.to_dict()
        log_date = parse_firestore_date(d.get('date'))
        if not log_date or log_date in existing:
            continue

        # Temperature: Alafia stores Fahrenheit values in bodyTemperature
        temp_f = safe_float(d.get('bodyTemperature'))
        temp_c = None
        if temp_f and temp_f > 50:  # Fahrenheit
            temp_c = round((temp_f - 32) * 5 / 9, 1)
        elif temp_f:
            temp_c = temp_f  # Already Celsius

        # Weight: stored in kg or lbs
        weight = safe_float(d.get('currentWeight'))
        weight_unit = d.get('currentWeightUnit', 'kg')
        if weight and weight_unit and 'lb' in str(weight_unit).lower():
            weight = round(weight * 0.453592, 1)

        cur.execute("""
            INSERT INTO vitals_logs (user_id, log_date, blood_pressure_systolic, blood_pressure_diastolic,
                heart_rate_bpm, body_temperature_c, weight_kg, blood_oxygen_pct, blood_glucose_mg_dl,
                notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            ALAFIA_USER_ID, log_date,
            safe_int(d.get('bloodPressureSystolic')),
            safe_int(d.get('bloodPressureDiastolic')),
            safe_int(d.get('heartRate')),
            temp_c, weight,
            safe_float(d.get('bloodOxygenLevel')),
            safe_float(d.get('bloodSugarMgDl')),
            safe_str(d.get('notes'))
        ))
        existing.add(log_date)
        imported += 1

    conn.commit()
    return imported


def import_nutrition(db, conn):
    """nutritionLog → nutrition_logs (with AI-analyzed macros)"""
    docs = db.collection('users').document(FIREBASE_UID).collection('nutritionLog').get()
    cur = conn.cursor()

    # Dedup: date + food_item prefix
    cur.execute("SELECT log_date, LEFT(food_name, 80) FROM nutrition_logs WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing = {(row[0], row[1]) for row in cur.fetchall()}

    imported = 0
    for doc in docs:
        d = doc.to_dict()
        log_date = parse_firestore_date(d.get('date'))
        food_item = safe_str(d.get('foodItem'))
        if not log_date or not food_item:
            continue

        dedup_key = (log_date, food_item[:80])
        if dedup_key in existing:
            continue

        meal_type = safe_str(d.get('mealType')) or 'meal'
        start_time = safe_str(d.get('startTime'))
        end_time = safe_str(d.get('endTime'))
        pre_weight = safe_float(d.get('preMealWeightKg'))
        post_weight = safe_float(d.get('postMealWeightKg'))

        notes_parts = []
        if start_time:
            notes_parts.append(f"Eaten: {start_time}" + (f"-{end_time}" if end_time else ""))
        if pre_weight:
            notes_parts.append(f"Pre-weight: {pre_weight}kg")
        if post_weight:
            notes_parts.append(f"Post-weight: {post_weight}kg")
        ai_summary = safe_str(d.get('aiProcessedSummary'))
        if ai_summary:
            notes_parts.append(f"AI: {ai_summary[:200]}")
        notes = '; '.join(notes_parts) if notes_parts else None

        cur.execute("""
            INSERT INTO nutrition_logs (user_id, log_date, meal_type, food_name,
                calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g,
                sodium_mg, potassium_mg, calcium_mg, iron_mg, phosphorus_mg,
                vitamin_d_iu, vitamin_b12_mcg, vitamin_b9_folate_mcg, cholesterol_mg,
                notes, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """, (
            ALAFIA_USER_ID, log_date, meal_type, food_item,
            safe_float(d.get('calories')),
            safe_float(d.get('protein')),
            safe_float(d.get('carbs')),
            safe_float(d.get('fat')),
            safe_float(d.get('fiber')),
            safe_float(d.get('sugar')),
            safe_float(d.get('sodium')),
            safe_float(d.get('potassium')),
            safe_float(d.get('calcium')),
            safe_float(d.get('iron')),
            safe_float(d.get('phosphate')),
            safe_float(d.get('vitaminD')),
            safe_float(d.get('vitaminB12')),
            safe_float(d.get('folicAcid')),
            safe_float(d.get('cholesterol')),
            notes
        ))
        existing.add(dedup_key)
        imported += 1

    conn.commit()
    return imported


def import_medications(db, conn):
    """medicationLog → medication_logs"""
    docs = db.collection('users').document(FIREBASE_UID).collection('medicationLog').get()
    cur = conn.cursor()

    # Dedup: date + time + medication_name
    cur.execute("SELECT log_date, log_time, medication_name FROM medication_logs WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing = {(row[0], row[1], row[2]) for row in cur.fetchall()}

    imported = 0
    for doc in docs:
        d = doc.to_dict()
        log_date = parse_firestore_date(d.get('date'))
        med_name = safe_str(d.get('medicationName'))
        if not log_date or not med_name:
            continue

        log_time = parse_firestore_time(d.get('time'))
        dedup_key = (log_date, log_time, med_name)
        if dedup_key in existing:
            continue

        cur.execute("""
            INSERT INTO medication_logs (user_id, log_date, log_time, medication_name, dosage,
                notes, source_provider,
                pre_systolic_bp, pre_diastolic_bp, pre_heart_rate,
                post_systolic_bp, post_diastolic_bp, post_heart_rate,
                created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """, (
            ALAFIA_USER_ID, log_date, log_time, med_name,
            safe_str(d.get('dosage')),
            safe_str(d.get('notes')),
            safe_str(d.get('sourceProvider')),
            safe_int(d.get('preMedicationBloodPressureSystolic')),
            safe_int(d.get('preMedicationBloodPressureDiastolic')),
            safe_int(d.get('preMedicationHeartRate')),
            safe_int(d.get('postMedicationBloodPressureSystolic')),
            safe_int(d.get('postMedicationBloodPressureDiastolic')),
            safe_int(d.get('postMedicationHeartRate')),
        ))
        existing.add(dedup_key)
        imported += 1

    conn.commit()
    return imported


def import_elimination(db, conn):
    """eliminationLog → bowel_movements + vomiting_logs + urination_logs"""
    docs = db.collection('users').document(FIREBASE_UID).collection('eliminationLog').get()
    cur = conn.cursor()

    # Dedup sets
    cur.execute("SELECT log_date, log_time FROM bowel_movements WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing_poop = {(row[0], row[1]) for row in cur.fetchall()}

    cur.execute("SELECT log_date, log_time FROM vomiting_logs WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing_vomit = {(row[0], row[1]) for row in cur.fetchall()}

    cur.execute("SELECT log_date, log_time FROM urination_logs WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing_urine = {(row[0], row[1]) for row in cur.fetchall()}

    poop_count = 0
    vomit_count = 0
    urine_count = 0

    for doc in docs:
        d = doc.to_dict()
        log_date = parse_firestore_date(d.get('date'))
        if not log_date:
            continue

        log_time = parse_firestore_time(d.get('time'))
        if log_time is None:
            log_time = time(0, 0)

        raw_event_type = d.get('eventType', '') or ''
        event_type = str(raw_event_type).strip().lower()
        description = safe_str(d.get('description'))
        pre_weight = safe_float(d.get('preEventWeightKg'))
        post_weight = safe_float(d.get('postEventWeightKg'))

        notes_parts = []
        if pre_weight:
            notes_parts.append(f"Pre: {pre_weight}kg")
        if post_weight:
            notes_parts.append(f"Post: {post_weight}kg")
        if description:
            notes_parts.append(description)
        notes = '; '.join(notes_parts) if notes_parts else None

        weight_delta_ml = None
        if pre_weight and post_weight:
            weight_delta_ml = round((pre_weight - post_weight) * 1000)

        if event_type == 'poop':
            dedup_key = (log_date, log_time)
            if dedup_key in existing_poop:
                continue
            cur.execute("""
                INSERT INTO bowel_movements (user_id, log_date, log_time, notes, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (ALAFIA_USER_ID, log_date, log_time, notes))
            existing_poop.add(dedup_key)
            poop_count += 1

        elif event_type == 'vomiting':
            dedup_key = (log_date, log_time)
            if dedup_key in existing_vomit:
                continue
            cur.execute("""
                INSERT INTO vomiting_logs (user_id, log_date, log_time, volume, notes, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (ALAFIA_USER_ID, log_date, log_time,
                  weight_delta_ml if weight_delta_ml and weight_delta_ml > 0 else None,
                  notes))
            existing_vomit.add(dedup_key)
            vomit_count += 1

        elif event_type == 'urination':
            dedup_key = (log_date, log_time)
            if dedup_key in existing_urine:
                continue
            cur.execute("""
                INSERT INTO urination_logs (user_id, log_date, log_time,
                    volume_ml, notes, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (ALAFIA_USER_ID, log_date, log_time,
                  weight_delta_ml if weight_delta_ml and weight_delta_ml > 0 else None,
                  notes))
            existing_urine.add(dedup_key)
            urine_count += 1

    conn.commit()
    return poop_count, vomit_count, urine_count


def import_symptoms(db, conn):
    """symptomLog → symptom_logs"""
    docs = db.collection('users').document(FIREBASE_UID).collection('symptomLog').get()
    cur = conn.cursor()

    cur.execute("SELECT log_date, symptom_name FROM symptom_logs WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing = {(row[0], row[1]) for row in cur.fetchall()}

    imported = 0
    for doc in docs:
        d = doc.to_dict()
        log_date = parse_firestore_date(d.get('date'))
        symptom = safe_str(d.get('symptom'))
        if not log_date or not symptom:
            continue

        dedup_key = (log_date, symptom[:255])
        if dedup_key in existing:
            continue

        dur_min = safe_float(d.get('durationMinutes'))
        dur_hours = round(dur_min / 60, 2) if dur_min else None

        cur.execute("""
            INSERT INTO symptom_logs (user_id, log_date, symptom_name, severity,
                duration_hours, triggers, relievers, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            ALAFIA_USER_ID, log_date, symptom[:255],
            safe_int(d.get('severity')),
            dur_hours,
            safe_str(d.get('triggers')),
            safe_str(d.get('reliefMeasures')),
            safe_str(d.get('notes'))
        ))
        existing.add(dedup_key)
        imported += 1

    conn.commit()
    return imported


def import_journal(db, conn):
    """journalEntries → mood_entries"""
    docs = db.collection('users').document(FIREBASE_UID).collection('journalEntries').get()
    cur = conn.cursor()

    cur.execute("SELECT entry_date FROM mood_entries WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing = {row[0] for row in cur.fetchall()}

    imported = 0
    for doc in docs:
        d = doc.to_dict()
        entry_date = parse_firestore_date(d.get('date'))
        if not entry_date or entry_date in existing:
            continue

        mood_str = safe_str(d.get('mood'))
        # Map mood text to numeric score 1-10
        mood_map = {
            'terrible': 1, 'awful': 2, 'bad': 2, 'sad': 3, 'low': 3,
            'anxious': 4, 'meh': 4, 'ok': 5, 'okay': 5, 'neutral': 5,
            'alright': 5, 'fine': 6, 'hopeful': 6, 'hopefull': 6,
            'good': 7, 'positive': 7, 'happy': 8, 'great': 8,
            'excellent': 9, 'amazing': 10, 'wonderful': 10,
        }
        mood_score = mood_map.get(mood_str.lower(), 5) if mood_str else 5

        sleep_hours = safe_float(d.get('hoursSlept'))

        # Combine all text into journal entry
        journal_parts = []
        if d.get('feelings'):
            journal_parts.append(safe_str(d.get('feelings')))
        if d.get('nutrition'):
            journal_parts.append(f"Nutrition: {safe_str(d.get('nutrition'))}")
        if d.get('activities'):
            journal_parts.append(f"Activities: {safe_str(d.get('activities'))}")
        journal_text = '\n'.join([p for p in journal_parts if p]) or None

        cur.execute("""
            INSERT INTO mood_entries (user_id, entry_date, mood_score, sleep_hours,
                emotions, journal_entry, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            ALAFIA_USER_ID, entry_date, mood_score, sleep_hours,
            mood_str, journal_text
        ))
        existing.add(entry_date)
        imported += 1

    conn.commit()
    return imported


def import_hd_flowsheets(db, conn):
    """hemodialysisFlowsheets → therapy_sessions + intradialytic_readings"""
    docs = db.collection('users').document(FIREBASE_UID).collection('hemodialysisFlowsheets').get()
    cur = conn.cursor()

    # Dedup by scheduled_date (datetime)
    cur.execute("SELECT scheduled_date FROM therapy_sessions WHERE user_id = %s AND therapy_type = 'HEMODIALYSIS'",
                (ALAFIA_USER_ID,))
    existing = {row[0] for row in cur.fetchall()}

    sessions_imported = 0
    readings_imported = 0

    for doc in docs:
        d = doc.to_dict()
        session_date = parse_firestore_date(d.get('date'))
        if not session_date:
            continue

        scheduled_dt = datetime.combine(session_date, time(0, 0))
        if scheduled_dt in existing:
            continue

        start_time = parse_firestore_time(d.get('treatmentStartTime'))
        end_time = parse_firestore_time(d.get('treatmentEndTime'))
        actual_start = datetime.combine(session_date, start_time) if start_time else None
        actual_end = datetime.combine(session_date, end_time) if end_time else None
        if actual_start and actual_end and actual_end < actual_start:
            actual_end += timedelta(days=1)

        # Duration from totalMachineTimeHours (format: "4:14")
        duration_minutes = None
        tmt = safe_str(d.get('totalMachineTimeHours'))
        if tmt:
            m = re.match(r'(\d+):(\d+)', tmt)
            if m:
                duration_minutes = int(m.group(1)) * 60 + int(m.group(2))

        # Weights
        pre_weight = safe_float(d.get('preWeightKg'))
        post_weight = safe_float(d.get('postWeightKg'))
        target_weight = safe_float(d.get('targetWeightKg'))
        fluid_removed = safe_float(d.get('fluidRemovedLiters'))
        fluid_removed_ml = round(fluid_removed * 1000) if fluid_removed else None

        # Build session
        session = {
            'user_id': ALAFIA_USER_ID,
            'condition_id': CONDITION_ID,
            'therapy_type': 'HEMODIALYSIS',
            'therapy_name': 'Home Hemodialysis (HHD)',
            'scheduled_date': scheduled_dt,
            'actual_start_time': actual_start,
            'actual_end_time': actual_end,
            'duration_minutes': duration_minutes,
            'status': 'COMPLETED',
            'facility_name': safe_str(d.get('dialysisCenterName')) or 'DaVita Home',
            'attending_physician': safe_str(d.get('prescriberName')),
            'rn_reviewer': safe_str(d.get('reviewerName')),
            'dialysis_access_type': safe_str(d.get('accessSite')),
            'pre_dialysis_weight_kg': pre_weight,
            'post_dialysis_weight_kg': post_weight,
            'dry_weight_kg': target_weight,
            'fluid_removed_ml': fluid_removed_ml,
            'pre_systolic_bp': safe_int(d.get('preTreatmentBPSittingSystolic')),
            'pre_diastolic_bp': safe_int(d.get('preTreatmentBPSittingDiastolic')),
            'pre_heart_rate': safe_int(d.get('preTreatmentHRSitting')),
            'pre_standing_systolic_bp': safe_int(d.get('preTreatmentBPStandingSystolic')),
            'pre_standing_diastolic_bp': safe_int(d.get('preTreatmentBPStandingDiastolic')),
            'pre_standing_heart_rate': safe_int(d.get('preTreatmentHRStanding')),
            'post_systolic_bp': safe_int(d.get('postTreatmentBPSittingSystolic')),
            'post_diastolic_bp': safe_int(d.get('postTreatmentBPSittingDiastolic')),
            'post_heart_rate': safe_int(d.get('postTreatmentHRSitting')),
            'post_standing_systolic_bp': safe_int(d.get('postTreatmentBPStandingSystolic')),
            'post_standing_diastolic_bp': safe_int(d.get('postTreatmentBPStandingDiastolic')),
            'post_standing_heart_rate': safe_int(d.get('postTreatmentHRStanding')),
            'total_dialysate_liters': safe_float(d.get('totalDialysateUsedLiters')),
            'total_blood_volume_processed': safe_float(d.get('totalBloodVolumeProcessedLiters')),
            'clinical_notes': safe_str(d.get('generalNotes')),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        }

        # Handle temperature (may be F or C)
        pre_temp = safe_float(d.get('preTreatmentTemperatureCelsius'))
        pre_unit = safe_str(d.get('preTreatmentTemperatureUnit'))
        if pre_temp and pre_unit and 'fahrenheit' in pre_unit.lower():
            pre_temp = round((pre_temp - 32) * 5 / 9, 1)
        session['pre_temperature'] = pre_temp

        post_temp = safe_float(d.get('postTreatmentTemperatureCelsius'))
        post_unit = safe_str(d.get('postTreatmentTemperatureUnit'))
        if post_temp and post_unit and 'fahrenheit' in post_unit.lower():
            post_temp = round((post_temp - 32) * 5 / 9, 1)
        session['post_temperature'] = post_temp

        # Equipment
        session['cartridge_lot'] = safe_str(d.get('dialyzerLotNumber'))
        session['sak_lot'] = safe_str(d.get('dialysateLotNumber'))

        # Insert session
        cols = list(session.keys())
        vals = [session[c] for c in cols]
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        cur.execute(
            f"INSERT INTO therapy_sessions ({col_names}) VALUES ({placeholders}) RETURNING id",
            vals
        )
        session_id = cur.fetchone()[0]
        existing.add(scheduled_dt)
        sessions_imported += 1

        # Import intradialytic readings
        readings = d.get('intraDialyticReadings') or []
        for i, r in enumerate(readings):
            reading_time = parse_firestore_time(r.get('time'))
            if reading_time is None:
                reading_time = time(0, 0)

            # Parse BP "120/80" format or individual fields
            sys_bp = safe_int(r.get('bloodPressureSystolic'))
            dia_bp = safe_int(r.get('bloodPressureDiastolic'))
            bp_str = safe_str(r.get('bloodPressure'))
            if bp_str and not sys_bp:
                bp_m = re.match(r'(\d+)\s*/\s*(\d+)', bp_str)
                if bp_m:
                    sys_bp = int(bp_m.group(1))
                    dia_bp = int(bp_m.group(2))

            cur.execute("""
                INSERT INTO intradialytic_readings (user_id, session_id, reading_time, reading_number,
                    systolic_bp, diastolic_bp, pulse, blood_flow_rate,
                    dialysate_rate, uf_rate, uf_volume_removed,
                    arterial_pressure, venous_pressure, effluent_pressure,
                    access_state, remarks, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (
                ALAFIA_USER_ID, session_id, reading_time, i + 1,
                sys_bp, dia_bp,
                safe_int(r.get('heartRate')),
                safe_float(r.get('bloodFlowRateMlMin')),
                safe_float(r.get('dialysateFlowRate')),
                safe_float(r.get('ufRemovalRate')),
                safe_float(r.get('ufLeftToRemove')),
                safe_float(r.get('arterialPressure')),
                safe_float(r.get('venousPressure')),
                safe_float(r.get('effluentPressure')),
                safe_str(r.get('accessState')),
                safe_str(r.get('notes')),
            ))
            readings_imported += 1

    conn.commit()
    return sessions_imported, readings_imported


def import_lab_reports(db, conn):
    """labReports → lab_results"""
    docs = db.collection('users').document(FIREBASE_UID).collection('labReports').get()
    cur = conn.cursor()

    # Dedup by test_date + test_name
    cur.execute("SELECT test_date, test_name FROM lab_results WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing = {(row[0], row[1]) for row in cur.fetchall()}

    imported = 0
    for doc in docs:
        d = doc.to_dict()
        test_date = parse_firestore_date(d.get('date'))
        if not test_date:
            continue

        panel_name = safe_str(d.get('panelName'))
        lab_name = safe_str(d.get('labName'))
        items = d.get('items') or []

        for item in items:
            test_name = safe_str(item.get('name'))
            if not test_name:
                continue

            dedup_key = (test_date, test_name)
            if dedup_key in existing:
                continue

            value_str = safe_str(item.get('value'))
            result_value = None
            if value_str:
                # Try to extract numeric value
                m = re.search(r'[\d.]+', value_str)
                if m:
                    try:
                        result_value = float(m.group())
                    except ValueError:
                        pass

            ref_range = safe_str(item.get('referenceRange'))
            unit = safe_str(item.get('unit'))

            # Parse reference range into low/high
            ref_low = None
            ref_high = None
            if ref_range:
                m_range = re.match(r'([\d.]+)\s*[-–]\s*([\d.]+)', ref_range)
                if m_range:
                    ref_low = safe_float(m_range.group(1))
                    ref_high = safe_float(m_range.group(2))

            is_abnormal = None
            if result_value is not None and ref_low is not None and ref_high is not None:
                is_abnormal = result_value < ref_low or result_value > ref_high

            cur.execute("""
                INSERT INTO lab_results (user_id, test_date, test_name, value, value_string,
                    unit, reference_range_low, reference_range_high, is_abnormal,
                    category, performing_lab, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                ALAFIA_USER_ID, test_date, test_name,
                result_value, value_str, unit, ref_low, ref_high, is_abnormal,
                panel_name, lab_name, 'final'
            ))
            existing.add(dedup_key)
            imported += 1

    conn.commit()
    return imported


def import_scheduled_events(db, conn):
    """scheduledEvents → calendar_events"""
    docs = db.collection('users').document(FIREBASE_UID).collection('scheduledEvents').get()
    cur = conn.cursor()

    # Check calendar_events schema
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name='calendar_events' ORDER BY ordinal_position
    """)
    cal_cols = [row[0] for row in cur.fetchall()]

    # Dedup
    cur.execute("SELECT event_date, title FROM calendar_events WHERE user_id = %s", (ALAFIA_USER_ID,))
    existing = {(row[0], row[1]) for row in cur.fetchall()}

    imported = 0
    for doc in docs:
        d = doc.to_dict()
        event_date = parse_firestore_date(d.get('date'))
        title = safe_str(d.get('title'))
        if not event_date or not title:
            continue

        dedup_key = (event_date, title)
        if dedup_key in existing:
            continue

        event_time = parse_firestore_time(d.get('time'))
        category = safe_str(d.get('eventType')) or 'appointment'

        start_t = event_time if event_time else time(9, 0)

        cur.execute("""
            INSERT INTO calendar_events (user_id, title, category, event_date,
                start_time, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            ALAFIA_USER_ID, title, category, event_date,
            start_t, safe_str(d.get('notes'))
        ))
        existing.add(dedup_key)
        imported += 1

    conn.commit()
    return imported


# ── Main ──────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ALAFIA.APP → ALAFIA Firestore Migration")
    print("=" * 60)

    # Connect to Firestore
    print(f"\nConnecting to Firestore (alafia-9i0hh)...")
    cred = credentials.Certificate(SERVICE_ACCOUNT)
    app = firebase_admin.initialize_app(cred)
    db = firestore.client()
    print(f"  Source user: {FIREBASE_UID}")

    # Connect to PostgreSQL
    print(f"Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_PARAMS)
    print(f"  Target user_id: {ALAFIA_USER_ID}")

    # Current state
    cur = conn.cursor()
    for tbl in ['vitals_logs', 'nutrition_logs', 'medication_logs', 'bowel_movements',
                'vomiting_logs', 'urination_logs', 'symptom_logs', 'mood_entries',
                'therapy_sessions', 'intradialytic_readings', 'lab_results', 'calendar_events']:
        cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE user_id = %s", (ALAFIA_USER_ID,))
        print(f"  {tbl}: {cur.fetchone()[0]}")

    # Import each collection
    results = {}

    print(f"\n--- Importing vitalsLog ---")
    try:
        results['vitals'] = import_vitals(db, conn)
        print(f"  Imported: {results['vitals']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['vitals'] = 0

    print(f"\n--- Importing nutritionLog ---")
    try:
        results['nutrition'] = import_nutrition(db, conn)
        print(f"  Imported: {results['nutrition']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['nutrition'] = 0

    print(f"\n--- Importing medicationLog ---")
    try:
        results['medications'] = import_medications(db, conn)
        print(f"  Imported: {results['medications']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['medications'] = 0

    print(f"\n--- Importing eliminationLog ---")
    try:
        p, v, u = import_elimination(db, conn)
        results['poop'] = p
        results['vomit'] = v
        results['urine'] = u
        print(f"  Imported: {p} poop, {v} vomit, {u} urination")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['poop'] = results['vomit'] = results['urine'] = 0

    print(f"\n--- Importing symptomLog ---")
    try:
        results['symptoms'] = import_symptoms(db, conn)
        print(f"  Imported: {results['symptoms']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['symptoms'] = 0

    print(f"\n--- Importing journalEntries ---")
    try:
        results['journal'] = import_journal(db, conn)
        print(f"  Imported: {results['journal']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['journal'] = 0

    print(f"\n--- Importing hemodialysisFlowsheets ---")
    try:
        s, r = import_hd_flowsheets(db, conn)
        results['hd_sessions'] = s
        results['hd_readings'] = r
        print(f"  Imported: {s} sessions, {r} readings")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['hd_sessions'] = results['hd_readings'] = 0

    print(f"\n--- Importing labReports ---")
    try:
        results['labs'] = import_lab_reports(db, conn)
        print(f"  Imported: {results['labs']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['labs'] = 0

    print(f"\n--- Importing scheduledEvents ---")
    try:
        results['events'] = import_scheduled_events(db, conn)
        print(f"  Imported: {results['events']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
        results['events'] = 0

    # Final state
    print(f"\n{'='*60}")
    print(f"MIGRATION COMPLETE")
    print(f"{'='*60}")
    cur = conn.cursor()
    for tbl in ['vitals_logs', 'nutrition_logs', 'medication_logs', 'bowel_movements',
                'vomiting_logs', 'urination_logs', 'symptom_logs', 'mood_entries',
                'therapy_sessions', 'intradialytic_readings', 'lab_results', 'calendar_events']:
        cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE user_id = %s", (ALAFIA_USER_ID,))
        count = cur.fetchone()[0]
        # Get date range if applicable
        date_col = None
        for dc in ['log_date', 'entry_date', 'test_date', 'event_date']:
            cur.execute(f"""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name=%s AND column_name=%s
            """, (tbl, dc))
            if cur.fetchone():
                date_col = dc
                break
        if not date_col and tbl in ('therapy_sessions',):
            date_col = 'scheduled_date'

        if date_col and count > 0:
            cur.execute(f"SELECT MIN({date_col})::date, MAX({date_col})::date FROM {tbl} WHERE user_id = %s",
                        (ALAFIA_USER_ID,))
            dr = cur.fetchone()
            print(f"  {tbl}: {count:,}  ({dr[0]} → {dr[1]})")
        else:
            print(f"  {tbl}: {count:,}")

    conn.close()
    firebase_admin.delete_app(app)


if __name__ == '__main__':
    main()
