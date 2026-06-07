#!/usr/bin/env python3
"""
Fetch all health data from ALAFIA.APP Firestore and save as CSVs for ML.

Source: Firestore project alafia-9i0hh
User: sKhP73PXMQXL7uVnWq28Sm0p0Ts2 (developer@hntsolutions.com)

Output: ML/data/raw/api/*.csv (one CSV per Firestore collection)

Collections:
  1. vitalsLog              → vitals.csv
  2. nutritionLog           → nutrition.csv
  3. medicationLog          → medications.csv
  4. eliminationLog         → elimination.csv
  5. symptomLog             → symptoms.csv
  6. journalEntries         → journal_mood.csv
  7. hemodialysisFlowsheets → dialysis_sessions.csv + dialysis_readings.csv
  8. labReports             → lab_results.csv
  9. scheduledEvents        → calendar_events.csv
"""

import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
from pathlib import Path
from datetime import datetime, date, time
import re
import sys

# ── Config ────────────────────────────────────────────────
import os as _os
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SERVICE_ACCOUNT = _os.environ.get('FIREBASE_SERVICE_ACCOUNT', str(PROJECT_ROOT / 'service-account.json'))
FIREBASE_UID = _os.environ.get('FIREBASE_UID', 'sKhP73PXMQXL7uVnWq28Sm0p0Ts2')
OUTPUT_DIR = PROJECT_ROOT / 'data' / 'raw' / 'api'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_val(val):
    """Convert Firestore types to Python-native for CSV."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, time):
        return val.strftime('%H:%M')
    if isinstance(val, (list, dict)):
        return str(val)
    return val


def parse_date_str(val):
    """Parse Firestore date to ISO string."""
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, str):
        for fmt in ['%Y-%m-%d', '%m/%d/%Y']:
            try:
                return datetime.strptime(val.split('T')[0], fmt).date().isoformat()
            except ValueError:
                continue
    return None


def fetch_collection(db, collection_name):
    """Fetch all docs from a user subcollection, return list of dicts."""
    docs = db.collection('users').document(FIREBASE_UID).collection(collection_name).get()
    records = []
    for doc in docs:
        d = doc.to_dict()
        d['_doc_id'] = doc.id
        records.append({k: safe_val(v) for k, v in d.items()})
    return records


def fetch_vitals(db):
    """vitalsLog → vitals.csv"""
    records = fetch_collection(db, 'vitalsLog')
    rows = []
    for d in records:
        rows.append({
            'date': parse_date_str(d.get('date')),
            'bp_systolic': d.get('bloodPressureSystolic'),
            'bp_diastolic': d.get('bloodPressureDiastolic'),
            'heart_rate': d.get('heartRate'),
            'body_temperature': d.get('bodyTemperature'),
            'temperature_unit': d.get('bodyTemperatureUnit', 'F'),
            'weight': d.get('currentWeight'),
            'weight_unit': d.get('currentWeightUnit', 'kg'),
            'blood_oxygen': d.get('bloodOxygenLevel'),
            'blood_glucose': d.get('bloodSugarMgDl'),
            'notes': d.get('notes'),
        })
    return pd.DataFrame(rows)


def fetch_nutrition(db):
    """nutritionLog → nutrition.csv"""
    records = fetch_collection(db, 'nutritionLog')
    rows = []
    for d in records:
        rows.append({
            'date': parse_date_str(d.get('date')),
            'meal_type': d.get('mealType'),
            'food_item': d.get('foodItem'),
            'start_time': d.get('startTime'),
            'end_time': d.get('endTime'),
            'pre_meal_weight_kg': d.get('preMealWeightKg'),
            'post_meal_weight_kg': d.get('postMealWeightKg'),
            'calories': d.get('calories'),
            'protein': d.get('protein'),
            'carbs': d.get('carbs'),
            'fat': d.get('fat'),
            'fiber': d.get('fiber'),
            'sugar': d.get('sugar'),
            'sodium': d.get('sodium'),
            'potassium': d.get('potassium'),
            'calcium': d.get('calcium'),
            'iron': d.get('iron'),
            'phosphorus': d.get('phosphate'),
            'vitamin_d': d.get('vitaminD'),
            'vitamin_b12': d.get('vitaminB12'),
            'folic_acid': d.get('folicAcid'),
            'cholesterol': d.get('cholesterol'),
            'ai_summary': d.get('aiProcessedSummary'),
        })
    return pd.DataFrame(rows)


def fetch_medications(db):
    """medicationLog → medications.csv"""
    records = fetch_collection(db, 'medicationLog')
    rows = []
    for d in records:
        rows.append({
            'date': parse_date_str(d.get('date')),
            'time': d.get('time'),
            'medication_name': d.get('medicationName'),
            'dosage': d.get('dosage'),
            'source_provider': d.get('sourceProvider'),
            'pre_bp_systolic': d.get('preMedicationBloodPressureSystolic'),
            'pre_bp_diastolic': d.get('preMedicationBloodPressureDiastolic'),
            'pre_heart_rate': d.get('preMedicationHeartRate'),
            'post_bp_systolic': d.get('postMedicationBloodPressureSystolic'),
            'post_bp_diastolic': d.get('postMedicationBloodPressureDiastolic'),
            'post_heart_rate': d.get('postMedicationHeartRate'),
            'notes': d.get('notes'),
        })
    return pd.DataFrame(rows)


def fetch_elimination(db):
    """eliminationLog → elimination.csv"""
    records = fetch_collection(db, 'eliminationLog')
    rows = []
    for d in records:
        rows.append({
            'date': parse_date_str(d.get('date')),
            'time': d.get('time'),
            'event_type': d.get('eventType'),
            'description': d.get('description'),
            'pre_weight_kg': d.get('preEventWeightKg'),
            'post_weight_kg': d.get('postEventWeightKg'),
        })
    return pd.DataFrame(rows)


def fetch_symptoms(db):
    """symptomLog → symptoms.csv"""
    records = fetch_collection(db, 'symptomLog')
    rows = []
    for d in records:
        rows.append({
            'date': parse_date_str(d.get('date')),
            'symptom': d.get('symptom'),
            'severity': d.get('severity'),
            'duration_minutes': d.get('durationMinutes'),
            'triggers': d.get('triggers'),
            'relief_measures': d.get('reliefMeasures'),
            'notes': d.get('notes'),
        })
    return pd.DataFrame(rows)


def fetch_journal(db):
    """journalEntries → journal_mood.csv"""
    records = fetch_collection(db, 'journalEntries')
    rows = []
    for d in records:
        rows.append({
            'date': parse_date_str(d.get('date')),
            'mood': d.get('mood'),
            'hours_slept': d.get('hoursSlept'),
            'feelings': d.get('feelings'),
            'nutrition_notes': d.get('nutrition'),
            'activities': d.get('activities'),
        })
    return pd.DataFrame(rows)


def fetch_dialysis(db):
    """hemodialysisFlowsheets → dialysis_sessions.csv + dialysis_readings.csv"""
    records = fetch_collection(db, 'hemodialysisFlowsheets')
    sessions = []
    readings = []

    for d in records:
        session_date = parse_date_str(d.get('date'))
        doc_id = d.get('_doc_id', '')

        session = {
            'date': session_date,
            'doc_id': doc_id,
            'facility': d.get('dialysisCenterName'),
            'prescriber': d.get('prescriberName'),
            'reviewer': d.get('reviewerName'),
            'access_site': d.get('accessSite'),
            'treatment_start': d.get('treatmentStartTime'),
            'treatment_end': d.get('treatmentEndTime'),
            'total_machine_time': d.get('totalMachineTimeHours'),
            # Weights
            'pre_weight_kg': d.get('preWeightKg'),
            'post_weight_kg': d.get('postWeightKg'),
            'target_weight_kg': d.get('targetWeightKg'),
            'fluid_removed_liters': d.get('fluidRemovedLiters'),
            # Pre-treatment vitals (sitting)
            'pre_bp_sitting_sys': d.get('preTreatmentBPSittingSystolic'),
            'pre_bp_sitting_dia': d.get('preTreatmentBPSittingDiastolic'),
            'pre_hr_sitting': d.get('preTreatmentHRSitting'),
            # Pre-treatment vitals (standing)
            'pre_bp_standing_sys': d.get('preTreatmentBPStandingSystolic'),
            'pre_bp_standing_dia': d.get('preTreatmentBPStandingDiastolic'),
            'pre_hr_standing': d.get('preTreatmentHRStanding'),
            # Post-treatment vitals (sitting)
            'post_bp_sitting_sys': d.get('postTreatmentBPSittingSystolic'),
            'post_bp_sitting_dia': d.get('postTreatmentBPSittingDiastolic'),
            'post_hr_sitting': d.get('postTreatmentHRSitting'),
            # Post-treatment vitals (standing)
            'post_bp_standing_sys': d.get('postTreatmentBPStandingSystolic'),
            'post_bp_standing_dia': d.get('postTreatmentBPStandingDiastolic'),
            'post_hr_standing': d.get('postTreatmentHRStanding'),
            # Temperature
            'pre_temperature': d.get('preTreatmentTemperatureCelsius'),
            'pre_temp_unit': d.get('preTreatmentTemperatureUnit'),
            'post_temperature': d.get('postTreatmentTemperatureCelsius'),
            'post_temp_unit': d.get('postTreatmentTemperatureUnit'),
            # Volumes
            'total_dialysate_liters': d.get('totalDialysateUsedLiters'),
            'total_blood_volume_liters': d.get('totalBloodVolumeProcessedLiters'),
            # Equipment
            'dialyzer_lot': d.get('dialyzerLotNumber'),
            'dialysate_lot': d.get('dialysateLotNumber'),
            # Notes
            'general_notes': d.get('generalNotes'),
        }
        sessions.append(session)

        # Intradialytic readings
        intra_readings = d.get('intraDialyticReadings')
        if isinstance(intra_readings, str):
            try:
                import ast
                intra_readings = ast.literal_eval(intra_readings)
            except Exception:
                intra_readings = []
        if not isinstance(intra_readings, list):
            intra_readings = []

        for i, r in enumerate(intra_readings):
            if not isinstance(r, dict):
                continue
            # Parse BP if in "120/80" format
            sys_bp = r.get('bloodPressureSystolic')
            dia_bp = r.get('bloodPressureDiastolic')
            bp_str = r.get('bloodPressure')
            if bp_str and not sys_bp:
                m = re.match(r'(\d+)\s*/\s*(\d+)', str(bp_str))
                if m:
                    sys_bp = int(m.group(1))
                    dia_bp = int(m.group(2))

            readings.append({
                'session_date': session_date,
                'session_doc_id': doc_id,
                'reading_number': i + 1,
                'time': safe_val(r.get('time')),
                'bp_systolic': sys_bp,
                'bp_diastolic': dia_bp,
                'heart_rate': r.get('heartRate'),
                'blood_flow_rate': r.get('bloodFlowRateMlMin'),
                'dialysate_flow_rate': r.get('dialysateFlowRate'),
                'uf_removal_rate': r.get('ufRemovalRate'),
                'uf_left_to_remove': r.get('ufLeftToRemove'),
                'arterial_pressure': r.get('arterialPressure'),
                'venous_pressure': r.get('venousPressure'),
                'effluent_pressure': r.get('effluentPressure'),
                'access_state': r.get('accessState'),
                'notes': r.get('notes'),
            })

    return pd.DataFrame(sessions), pd.DataFrame(readings)


def fetch_labs(db):
    """labReports → lab_results.csv (one row per test item)"""
    records = fetch_collection(db, 'labReports')
    rows = []
    for d in records:
        test_date = parse_date_str(d.get('date'))
        panel_name = d.get('panelName')
        lab_name = d.get('labName')

        items = d.get('items')
        if isinstance(items, str):
            try:
                import ast
                items = ast.literal_eval(items)
            except Exception:
                items = []
        if not isinstance(items, list):
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append({
                'date': test_date,
                'panel_name': panel_name,
                'lab_name': lab_name,
                'test_name': item.get('name'),
                'value': item.get('value'),
                'unit': item.get('unit'),
                'reference_range': item.get('referenceRange'),
            })
    return pd.DataFrame(rows)


def fetch_events(db):
    """scheduledEvents → calendar_events.csv"""
    records = fetch_collection(db, 'scheduledEvents')
    rows = []
    for d in records:
        rows.append({
            'date': parse_date_str(d.get('date')),
            'title': d.get('title'),
            'event_type': d.get('eventType'),
            'time': d.get('time'),
            'notes': d.get('notes'),
        })
    return pd.DataFrame(rows)


# ── Main ──────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ALAFIA.APP Firestore → ML Data Export")
    print("=" * 60)

    # Connect to Firestore
    print(f"\nConnecting to Firestore (alafia-9i0hh)...")
    cred = credentials.Certificate(SERVICE_ACCOUNT)
    app = firebase_admin.initialize_app(cred)
    db = firestore.client()
    print(f"  User UID: {FIREBASE_UID}")
    print(f"  Output:   {OUTPUT_DIR}/")

    total_records = 0

    # 1. Vitals
    print(f"\n📊 Fetching vitalsLog...")
    df = fetch_vitals(db)
    df.to_csv(OUTPUT_DIR / 'vitals.csv', index=False)
    print(f"   → {len(df):,} records saved to vitals.csv")
    total_records += len(df)

    # 2. Nutrition
    print(f"🍽️  Fetching nutritionLog...")
    df = fetch_nutrition(db)
    df.to_csv(OUTPUT_DIR / 'nutrition.csv', index=False)
    print(f"   → {len(df):,} records saved to nutrition.csv")
    total_records += len(df)

    # 3. Medications
    print(f"💊 Fetching medicationLog...")
    df = fetch_medications(db)
    df.to_csv(OUTPUT_DIR / 'medications.csv', index=False)
    print(f"   → {len(df):,} records saved to medications.csv")
    total_records += len(df)

    # 4. Elimination
    print(f"🚽 Fetching eliminationLog...")
    df = fetch_elimination(db)
    df.to_csv(OUTPUT_DIR / 'elimination.csv', index=False)
    print(f"   → {len(df):,} records saved to elimination.csv")
    total_records += len(df)

    # 5. Symptoms
    print(f"🤒 Fetching symptomLog...")
    df = fetch_symptoms(db)
    df.to_csv(OUTPUT_DIR / 'symptoms.csv', index=False)
    print(f"   → {len(df):,} records saved to symptoms.csv")
    total_records += len(df)

    # 6. Journal / Mood
    print(f"📝 Fetching journalEntries...")
    df = fetch_journal(db)
    df.to_csv(OUTPUT_DIR / 'journal_mood.csv', index=False)
    print(f"   → {len(df):,} records saved to journal_mood.csv")
    total_records += len(df)

    # 7. Dialysis (sessions + readings)
    print(f"🩸 Fetching hemodialysisFlowsheets...")
    df_sessions, df_readings = fetch_dialysis(db)
    df_sessions.to_csv(OUTPUT_DIR / 'dialysis_sessions.csv', index=False)
    df_readings.to_csv(OUTPUT_DIR / 'dialysis_readings.csv', index=False)
    print(f"   → {len(df_sessions):,} sessions + {len(df_readings):,} readings saved")
    total_records += len(df_sessions) + len(df_readings)

    # 8. Labs
    print(f"🧪 Fetching labReports...")
    df = fetch_labs(db)
    df.to_csv(OUTPUT_DIR / 'lab_results.csv', index=False)
    print(f"   → {len(df):,} test results saved to lab_results.csv")
    total_records += len(df)

    # 9. Calendar Events
    print(f"📅 Fetching scheduledEvents...")
    df = fetch_events(db)
    df.to_csv(OUTPUT_DIR / 'calendar_events.csv', index=False)
    print(f"   → {len(df):,} events saved to calendar_events.csv")
    total_records += len(df)

    # Summary
    print(f"\n{'='*60}")
    print(f"✅ EXPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  Total records: {total_records:,}")
    print(f"  Output dir:    {OUTPUT_DIR}/")
    print(f"  Files:")
    for f in sorted(OUTPUT_DIR.glob('*.csv')):
        size = f.stat().st_size
        print(f"    {f.name:30s}  {size/1024:>8.1f} KB")

    firebase_admin.delete_app(app)
    print(f"\nNext: Open ML/notebooks/01_data_ingestion.ipynb to process these into standardized features.")


if __name__ == '__main__':
    main()
