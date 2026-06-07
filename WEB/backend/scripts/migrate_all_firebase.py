#!/usr/bin/env python3
"""
Migrate ALL Firebase users → ALAFIA PostgreSQL.

This script:
  1. Exports ALL Firebase Auth users (email, providers, UIDs)
  2. Creates corresponding PostgreSQL users with firebase_uid linkage
  3. Imports all Firestore profile data (pi.*) into user fields
  4. Imports all subcollection health data per user
  5. Deduplicates on re-run (safe to run multiple times)

Usage:
  cd /path/to/LAFIAKALO
  .venv/bin/python WEB/backend/scripts/migrate_all_firebase.py [--dry-run]
"""

import sys
import os
import re
import json
import secrets
import traceback
from datetime import datetime, date, time, timedelta, timezone

import firebase_admin
from firebase_admin import credentials, auth, firestore
import psycopg2
from psycopg2.extras import execute_values

# ── Configuration ─────────────────────────────────────────
SERVICE_ACCOUNT = os.environ.get(
    'FIREBASE_SERVICE_ACCOUNT',
    os.path.join(os.path.dirname(__file__), '..', '..', '..',
                 'alafia-9i0hh-firebase-adminsdk-fbsvc-fb3e9a5364.json')
)

DB_PARAMS = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5435')),
    'dbname': os.environ.get('DB_NAME', 'alafia'),
    'user': os.environ.get('DB_USER', 'alafia'),
    'password': os.environ.get('DB_PASSWORD', 'alafia'),
}

DRY_RUN = '--dry-run' in sys.argv
CONDITION_ID_ESRD = 14  # Will be overridden per-user with actual condition id

# Bcrypt for generating temporary passwords
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Helpers ───────────────────────────────────────────────

def parse_firestore_date(val):
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']:
            try:
                return datetime.strptime(val.split('T')[0] if 'T' in val else val, fmt.split('T')[0]).date()
            except ValueError:
                continue
    return None


def parse_firestore_time(val):
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


def safe_json(val):
    """Convert a value to JSON string for storage."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val)


# ── Step 1: Migrate Firebase Auth Users ───────────────────

def migrate_auth_users(conn, fs_db):
    """
    Pull all Firebase Auth users and create PostgreSQL users.
    Maps Firestore profile data (pi.*) into user fields.
    Returns dict: {firebase_uid: pg_user_id}
    """
    print("\n" + "=" * 60)
    print("STEP 1: Migrating Firebase Auth Users")
    print("=" * 60)

    cur = conn.cursor()

    # Get existing firebase_uid mappings
    cur.execute("SELECT firebase_uid, id FROM users WHERE firebase_uid IS NOT NULL")
    existing_map = {row[0]: row[1] for row in cur.fetchall()}
    uid_to_pgid = dict(existing_map)

    # List all Firebase Auth users
    auth_users = []
    page = auth.list_users()
    for user in page.iterate_all():
        auth_users.append(user)

    print(f"  Found {len(auth_users)} Firebase Auth users")
    print(f"  Already migrated: {len(existing_map)}")

    created = 0
    updated = 0

    for fb_user in auth_users:
        uid = fb_user.uid
        email = fb_user.email or f"firebase_{uid[:8]}@alafia.local"
        display_name = fb_user.display_name or email.split('@')[0]
        providers = [p.provider_id for p in fb_user.provider_data]
        primary_provider = providers[0] if providers else 'password'

        # Get Firestore profile data
        fs_doc = fs_db.collection('users').document(uid).get()
        pi = {}
        fs_data = {}
        if fs_doc.exists:
            fs_data = fs_doc.to_dict() or {}
            pi = fs_data.get('pi', {})

        # Extract profile fields from pi.*
        first_name = safe_str(pi.get('firstName'), 100)
        last_name = safe_str(pi.get('lastName'), 100)
        full_name = f"{first_name or ''} {last_name or ''}".strip() or display_name

        dob = safe_str(pi.get('dateOfBirth') or pi.get('dob'), 10)
        gender = safe_str(pi.get('gender') or pi.get('sex'), 20)
        gender_at_birth = safe_str(pi.get('genderAtBirth') or pi.get('biologicalSex'), 20)
        blood_type = safe_str(pi.get('bloodType'), 10)
        height_cm = safe_float(pi.get('heightCm') or pi.get('height'))
        weight_kg = safe_float(pi.get('weightKg') or pi.get('weight') or pi.get('currentWeight'))
        phone = safe_str(pi.get('phone') or pi.get('phoneNumber'), 20)

        # Health profile
        allergies = safe_json(pi.get('allergies'))
        chronic_conditions = safe_json(pi.get('chronicConditions'))
        dietary_restrictions = safe_json(pi.get('dietaryRestrictions'))
        dietary_preferences = safe_json(pi.get('dietaryPreferences'))
        food_intolerances = safe_json(pi.get('foodIntolerances'))

        # Insurance
        insurance_provider = safe_str(pi.get('insuranceProvider') or pi.get('insurance'), 100)
        insurance_id = safe_str(pi.get('insuranceId') or pi.get('memberId'), 100)

        # Preferences
        locale = safe_str(pi.get('locale'), 10)
        tz = safe_str(pi.get('timezone'), 50)
        country = safe_str(pi.get('country'), 100)
        preferred_units = safe_str(pi.get('preferredUnits') or pi.get('unitSystem'), 20)
        preferred_language = safe_str(pi.get('preferredLanguage') or pi.get('language'), 10)

        # Lifestyle
        activity_level = safe_str(pi.get('activityLevel'), 30)
        smoking_status = safe_str(pi.get('smokingStatus'), 20)
        alcohol_consumption = safe_str(pi.get('alcoholConsumption'), 20)
        occupation = safe_str(pi.get('occupation'), 100)

        # AI
        ai_persona = safe_str(pi.get('aiPersona') or fs_data.get('aiPersona'), 50)

        # Firebase metadata
        created_ts = fb_user.user_metadata.creation_timestamp
        created_at = datetime.fromtimestamp(created_ts / 1000, tz=timezone.utc) if created_ts else datetime.now(timezone.utc)

        if uid in existing_map:
            # Update existing user with any new profile data
            pg_id = existing_map[uid]
            cur.execute("""
                UPDATE users SET
                    full_name = COALESCE(NULLIF(%s, ''), full_name),
                    date_of_birth = COALESCE(%s, date_of_birth),
                    gender = COALESCE(%s, gender),
                    gender_at_birth = COALESCE(%s, gender_at_birth),
                    blood_type = COALESCE(%s, blood_type),
                    height_cm = COALESCE(%s, height_cm),
                    current_weight_kg = COALESCE(%s, current_weight_kg),
                    allergies = COALESCE(%s, allergies),
                    chronic_conditions = COALESCE(%s, chronic_conditions),
                    dietary_restrictions = COALESCE(%s, dietary_restrictions),
                    dietary_preferences = COALESCE(%s, dietary_preferences),
                    food_intolerances = COALESCE(%s, food_intolerances),
                    insurance_provider = COALESCE(%s, insurance_provider),
                    insurance_id = COALESCE(%s, insurance_id),
                    locale = COALESCE(%s, locale),
                    timezone = COALESCE(%s, timezone),
                    country = COALESCE(%s, country),
                    preferred_units = COALESCE(%s, preferred_units),
                    preferred_language = COALESCE(%s, preferred_language),
                    activity_level = COALESCE(%s, activity_level),
                    smoking_status = COALESCE(%s, smoking_status),
                    alcohol_consumption = COALESCE(%s, alcohol_consumption),
                    occupation = COALESCE(%s, occupation),
                    ai_persona = COALESCE(%s, ai_persona),
                    updated_at = NOW()
                WHERE id = %s
            """, (
                full_name, dob, gender, gender_at_birth, blood_type,
                height_cm, weight_kg,
                allergies, chronic_conditions, dietary_restrictions,
                dietary_preferences, food_intolerances,
                insurance_provider, insurance_id,
                locale, tz, country, preferred_units, preferred_language,
                activity_level, smoking_status, alcohol_consumption, occupation,
                ai_persona, pg_id,
            ))
            updated += 1
            print(f"  Updated: {email} (pg_id={pg_id})")
        else:
            # Create new user
            # Generate a temporary bcrypt password — user must reset via Firebase re-auth
            temp_password = secrets.token_urlsafe(32)
            hashed = pwd_context.hash(temp_password)

            cur.execute("""
                INSERT INTO users (
                    email, hashed_password, full_name, firebase_uid, auth_provider,
                    date_of_birth, gender, gender_at_birth, blood_type,
                    height_cm, current_weight_kg,
                    allergies, chronic_conditions, dietary_restrictions,
                    dietary_preferences, food_intolerances,
                    insurance_provider, insurance_id,
                    locale, timezone, country, preferred_units, preferred_language,
                    activity_level, smoking_status, alcohol_consumption, occupation,
                    ai_persona, ai_coaching_enabled, data_sharing_consent, ai_training_consent,
                    is_active, is_superuser, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, true, false, false,
                    true, false, %s, NOW()
                ) RETURNING id
            """, (
                email, hashed, full_name, uid, primary_provider,
                dob, gender, gender_at_birth, blood_type,
                height_cm, weight_kg,
                allergies, chronic_conditions, dietary_restrictions,
                dietary_preferences, food_intolerances,
                insurance_provider, insurance_id,
                locale, tz, country, preferred_units, preferred_language,
                activity_level, smoking_status, alcohol_consumption, occupation,
                ai_persona,
                created_at,
            ))
            pg_id = cur.fetchone()[0]
            uid_to_pgid[uid] = pg_id
            created += 1
            print(f"  Created: {email} (firebase_uid={uid[:12]}... → pg_id={pg_id})")

    if not DRY_RUN:
        conn.commit()
    print(f"\n  Summary: {created} created, {updated} updated, {len(uid_to_pgid)} total")
    return uid_to_pgid


# ── Step 2: Import Health Data Per User ───────────────────

def import_vitals(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('vitalsLog').get()
    if not docs:
        return 0
    cur = conn.cursor()
    cur.execute("SELECT log_date FROM vitals_logs WHERE user_id = %s", (pg_user_id,))
    existing = {row[0] for row in cur.fetchall()}
    imported = 0
    for doc in docs:
        d = doc.to_dict()
        log_date = parse_firestore_date(d.get('date'))
        if not log_date or log_date in existing:
            continue
        temp_f = safe_float(d.get('bodyTemperature'))
        temp_c = None
        if temp_f and temp_f > 50:
            temp_c = round((temp_f - 32) * 5 / 9, 1)
        elif temp_f:
            temp_c = temp_f
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
            pg_user_id, log_date,
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


def import_nutrition(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('nutritionLog').get()
    if not docs:
        return 0
    cur = conn.cursor()
    cur.execute("SELECT log_date, LEFT(food_name, 80) FROM nutrition_logs WHERE user_id = %s", (pg_user_id,))
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
        notes_parts = []
        start_time = safe_str(d.get('startTime'))
        end_time = safe_str(d.get('endTime'))
        if start_time:
            notes_parts.append(f"Eaten: {start_time}" + (f"-{end_time}" if end_time else ""))
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
            pg_user_id, log_date, meal_type, food_item,
            safe_float(d.get('calories')), safe_float(d.get('protein')),
            safe_float(d.get('carbs')), safe_float(d.get('fat')),
            safe_float(d.get('fiber')), safe_float(d.get('sugar')),
            safe_float(d.get('sodium')), safe_float(d.get('potassium')),
            safe_float(d.get('calcium')), safe_float(d.get('iron')),
            safe_float(d.get('phosphate')),
            safe_float(d.get('vitaminD')), safe_float(d.get('vitaminB12')),
            safe_float(d.get('folicAcid')), safe_float(d.get('cholesterol')),
            notes
        ))
        existing.add(dedup_key)
        imported += 1
    conn.commit()
    return imported


def import_medications(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('medicationLog').get()
    if not docs:
        return 0
    cur = conn.cursor()
    # Check if medication_logs table exists, else use medications table
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables WHERE table_name = 'medication_logs'
        )
    """)
    has_med_logs = cur.fetchone()[0]

    if has_med_logs:
        cur.execute("SELECT log_date, log_time, medication_name FROM medication_logs WHERE user_id = %s", (pg_user_id,))
        existing = {(row[0], row[1], row[2]) for row in cur.fetchall()}
    else:
        existing = set()

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

        if has_med_logs:
            cur.execute("""
                INSERT INTO medication_logs (user_id, log_date, log_time, medication_name, dosage,
                    notes, source_provider,
                    pre_systolic_bp, pre_diastolic_bp, pre_heart_rate,
                    post_systolic_bp, post_diastolic_bp, post_heart_rate,
                    created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (
                pg_user_id, log_date, log_time, med_name,
                safe_str(d.get('dosage')), safe_str(d.get('notes')),
                safe_str(d.get('sourceProvider')),
                safe_int(d.get('preMedicationBloodPressureSystolic')),
                safe_int(d.get('preMedicationBloodPressureDiastolic')),
                safe_int(d.get('preMedicationHeartRate')),
                safe_int(d.get('postMedicationBloodPressureSystolic')),
                safe_int(d.get('postMedicationBloodPressureDiastolic')),
                safe_int(d.get('postMedicationHeartRate')),
            ))
        else:
            # Fall back to medications table
            cur.execute("""
                INSERT INTO medications (user_id, name, dosage, frequency, start_date, notes, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, true, NOW())
            """, (
                pg_user_id, med_name, safe_str(d.get('dosage')),
                safe_str(d.get('frequency')), log_date, safe_str(d.get('notes')),
            ))
        existing.add(dedup_key)
        imported += 1
    conn.commit()
    return imported


def import_elimination(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('eliminationLog').get()
    if not docs:
        return 0, 0, 0
    cur = conn.cursor()
    cur.execute("SELECT log_date, log_time FROM bowel_movements WHERE user_id = %s", (pg_user_id,))
    existing_poop = {(row[0], row[1]) for row in cur.fetchall()}
    cur.execute("SELECT log_date, log_time FROM vomiting_logs WHERE user_id = %s", (pg_user_id,))
    existing_vomit = {(row[0], row[1]) for row in cur.fetchall()}
    cur.execute("SELECT log_date, log_time FROM urination_logs WHERE user_id = %s", (pg_user_id,))
    existing_urine = {(row[0], row[1]) for row in cur.fetchall()}

    poop_count = vomit_count = urine_count = 0
    for doc in docs:
        d = doc.to_dict()
        log_date = parse_firestore_date(d.get('date'))
        if not log_date:
            continue
        log_time = parse_firestore_time(d.get('time')) or time(0, 0)
        event_type = str(d.get('eventType', '')).strip().lower()
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
        weight_delta_ml = round((pre_weight - post_weight) * 1000) if pre_weight and post_weight else None

        if event_type == 'poop':
            if (log_date, log_time) not in existing_poop:
                cur.execute("INSERT INTO bowel_movements (user_id, log_date, log_time, notes, created_at) VALUES (%s,%s,%s,%s,NOW())",
                            (pg_user_id, log_date, log_time, notes))
                existing_poop.add((log_date, log_time))
                poop_count += 1
        elif event_type == 'vomiting':
            if (log_date, log_time) not in existing_vomit:
                cur.execute("INSERT INTO vomiting_logs (user_id, log_date, log_time, volume, notes, created_at) VALUES (%s,%s,%s,%s,%s,NOW())",
                            (pg_user_id, log_date, log_time,
                             weight_delta_ml if weight_delta_ml and weight_delta_ml > 0 else None, notes))
                existing_vomit.add((log_date, log_time))
                vomit_count += 1
        elif event_type == 'urination':
            if (log_date, log_time) not in existing_urine:
                cur.execute("INSERT INTO urination_logs (user_id, log_date, log_time, volume_ml, notes, created_at) VALUES (%s,%s,%s,%s,%s,NOW())",
                            (pg_user_id, log_date, log_time,
                             weight_delta_ml if weight_delta_ml and weight_delta_ml > 0 else None, notes))
                existing_urine.add((log_date, log_time))
                urine_count += 1
    conn.commit()
    return poop_count, vomit_count, urine_count


def import_symptoms(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('symptomLog').get()
    if not docs:
        return 0
    cur = conn.cursor()
    cur.execute("SELECT log_date, symptom_name FROM symptom_logs WHERE user_id = %s", (pg_user_id,))
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
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """, (
            pg_user_id, log_date, symptom[:255],
            safe_int(d.get('severity')), dur_hours,
            safe_str(d.get('triggers')), safe_str(d.get('reliefMeasures')),
            safe_str(d.get('notes'))
        ))
        existing.add(dedup_key)
        imported += 1
    conn.commit()
    return imported


def import_journal(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('journalEntries').get()
    if not docs:
        return 0
    cur = conn.cursor()
    cur.execute("SELECT entry_date FROM mood_entries WHERE user_id = %s", (pg_user_id,))
    existing = {row[0] for row in cur.fetchall()}
    imported = 0
    mood_map = {
        'terrible': 1, 'awful': 2, 'bad': 2, 'sad': 3, 'low': 3,
        'anxious': 4, 'meh': 4, 'ok': 5, 'okay': 5, 'neutral': 5,
        'alright': 5, 'fine': 6, 'hopeful': 6, 'hopefull': 6,
        'good': 7, 'positive': 7, 'happy': 8, 'great': 8,
        'excellent': 9, 'amazing': 10, 'wonderful': 10,
    }
    for doc in docs:
        d = doc.to_dict()
        entry_date = parse_firestore_date(d.get('date'))
        if not entry_date or entry_date in existing:
            continue
        mood_str = safe_str(d.get('mood'))
        mood_score = mood_map.get(mood_str.lower(), 5) if mood_str else 5
        sleep_hours = safe_float(d.get('hoursSlept'))
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
            VALUES (%s,%s,%s,%s,%s,%s,NOW())
        """, (pg_user_id, entry_date, mood_score, sleep_hours, mood_str, journal_text))
        existing.add(entry_date)
        imported += 1
    conn.commit()
    return imported


def import_hd_flowsheets(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('hemodialysisFlowsheets').get()
    if not docs:
        return 0, 0
    cur = conn.cursor()
    # Ensure an ESRD chronic_conditions record exists for this user
    cur.execute("SELECT id FROM chronic_conditions WHERE user_id=%s AND condition_name='End-Stage Renal Disease (ESRD)'", (pg_user_id,))
    row = cur.fetchone()
    if row:
        condition_id = row[0]
    else:
        cur.execute("""
            INSERT INTO chronic_conditions (user_id, condition_name, category, severity, is_active, created_at, updated_at)
            VALUES (%s, 'End-Stage Renal Disease (ESRD)', 'RENAL', 'SEVERE', true, NOW(), NOW())
            RETURNING id
        """, (pg_user_id,))
        condition_id = cur.fetchone()[0]
        conn.commit()

    cur.execute("SELECT scheduled_date FROM therapy_sessions WHERE user_id = %s AND therapy_type = 'HEMODIALYSIS'",
                (pg_user_id,))
    existing = {row[0] for row in cur.fetchall()}
    sessions_imported = readings_imported = 0

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

        duration_minutes = None
        tmt = safe_str(d.get('totalMachineTimeHours'))
        if tmt:
            m = re.match(r'(\d+):(\d+)', tmt)
            if m:
                duration_minutes = int(m.group(1)) * 60 + int(m.group(2))

        pre_weight = safe_float(d.get('preWeightKg'))
        post_weight = safe_float(d.get('postWeightKg'))
        target_weight = safe_float(d.get('targetWeightKg'))
        fluid_removed = safe_float(d.get('fluidRemovedLiters'))
        fluid_removed_ml = round(fluid_removed * 1000) if fluid_removed else None

        # Temperature conversions
        pre_temp = safe_float(d.get('preTreatmentTemperatureCelsius'))
        pre_unit = safe_str(d.get('preTreatmentTemperatureUnit'))
        if pre_temp and pre_unit and 'fahrenheit' in pre_unit.lower():
            pre_temp = round((pre_temp - 32) * 5 / 9, 1)
        post_temp = safe_float(d.get('postTreatmentTemperatureCelsius'))
        post_unit = safe_str(d.get('postTreatmentTemperatureUnit'))
        if post_temp and post_unit and 'fahrenheit' in post_unit.lower():
            post_temp = round((post_temp - 32) * 5 / 9, 1)

        cur.execute("""
            INSERT INTO therapy_sessions (
                user_id, condition_id, therapy_type, therapy_name,
                scheduled_date, actual_start_time, actual_end_time, duration_minutes, status,
                facility_name, attending_physician, rn_reviewer, dialysis_access_type,
                pre_dialysis_weight_kg, post_dialysis_weight_kg, dry_weight_kg, fluid_removed_ml,
                pre_systolic_bp, pre_diastolic_bp, pre_heart_rate,
                pre_standing_systolic_bp, pre_standing_diastolic_bp, pre_standing_heart_rate,
                post_systolic_bp, post_diastolic_bp, post_heart_rate,
                post_standing_systolic_bp, post_standing_diastolic_bp, post_standing_heart_rate,
                pre_temperature, post_temperature,
                total_dialysate_liters, total_blood_volume_processed,
                cartridge_lot, sak_lot,
                patient_notes, created_at, updated_at
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW()
            ) RETURNING id
        """, (
            pg_user_id, condition_id, 'HEMODIALYSIS', 'Home Hemodialysis (HHD)',
            scheduled_dt, actual_start, actual_end, duration_minutes, 'COMPLETED',
            safe_str(d.get('dialysisCenterName')) or 'DaVita Home',
            safe_str(d.get('prescriberName')), safe_str(d.get('reviewerName')),
            safe_str(d.get('accessSite')),
            pre_weight, post_weight, target_weight, fluid_removed_ml,
            safe_int(d.get('preTreatmentBPSittingSystolic')),
            safe_int(d.get('preTreatmentBPSittingDiastolic')),
            safe_int(d.get('preTreatmentHRSitting')),
            safe_int(d.get('preTreatmentBPStandingSystolic')),
            safe_int(d.get('preTreatmentBPStandingDiastolic')),
            safe_int(d.get('preTreatmentHRStanding')),
            safe_int(d.get('postTreatmentBPSittingSystolic')),
            safe_int(d.get('postTreatmentBPSittingDiastolic')),
            safe_int(d.get('postTreatmentHRSitting')),
            safe_int(d.get('postTreatmentBPStandingSystolic')),
            safe_int(d.get('postTreatmentBPStandingDiastolic')),
            safe_int(d.get('postTreatmentHRStanding')),
            pre_temp, post_temp,
            safe_float(d.get('totalDialysateUsedLiters')),
            safe_float(d.get('totalBloodVolumeProcessedLiters')),
            safe_str(d.get('dialyzerLotNumber')), safe_str(d.get('dialysateLotNumber')),
            safe_str(d.get('generalNotes')),
        ))
        session_id = cur.fetchone()[0]
        existing.add(scheduled_dt)
        sessions_imported += 1

        # Intradialytic readings
        readings = d.get('intraDialyticReadings') or []
        for i, r in enumerate(readings):
            reading_time = parse_firestore_time(r.get('time')) or time(0, 0)
            sys_bp = safe_int(r.get('bloodPressureSystolic'))
            dia_bp = safe_int(r.get('bloodPressureDiastolic'))
            bp_str = safe_str(r.get('bloodPressure'))
            if bp_str and not sys_bp:
                bp_m = re.match(r'(\d+)\s*/\s*(\d+)', bp_str)
                if bp_m:
                    sys_bp, dia_bp = int(bp_m.group(1)), int(bp_m.group(2))
            cur.execute("""
                INSERT INTO intradialytic_readings (user_id, session_id, reading_time, reading_number,
                    systolic_bp, diastolic_bp, pulse, blood_flow_rate,
                    dialysate_rate, uf_rate, uf_volume_removed,
                    arterial_pressure, venous_pressure, effluent_pressure,
                    access_state, remarks, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (
                pg_user_id, session_id, reading_time, i + 1,
                sys_bp, dia_bp, safe_int(r.get('heartRate')),
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


def import_lab_reports(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('labReports').get()
    if not docs:
        return 0
    cur = conn.cursor()
    cur.execute("SELECT test_date, test_name FROM lab_results WHERE user_id = %s", (pg_user_id,))
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
                m = re.search(r'[\d.]+', value_str)
                if m:
                    try:
                        result_value = float(m.group())
                    except ValueError:
                        pass
            ref_range = safe_str(item.get('referenceRange'))
            unit = safe_str(item.get('unit'))
            ref_low = ref_high = None
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
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (
                pg_user_id, test_date, test_name, result_value, value_str,
                unit, ref_low, ref_high, is_abnormal, panel_name, lab_name, 'final'
            ))
            existing.add(dedup_key)
            imported += 1
    conn.commit()
    return imported


def import_scheduled_events(fs_db, conn, firebase_uid, pg_user_id):
    docs = fs_db.collection('users').document(firebase_uid).collection('scheduledEvents').get()
    if not docs:
        return 0
    cur = conn.cursor()
    cur.execute("SELECT event_date, title FROM calendar_events WHERE user_id = %s", (pg_user_id,))
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
        event_time = parse_firestore_time(d.get('time')) or time(9, 0)
        category = safe_str(d.get('eventType')) or 'appointment'
        cur.execute("""
            INSERT INTO calendar_events (user_id, title, category, event_date, start_time, all_day, status, notes, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,false,'scheduled',%s,NOW(),NOW())
        """, (pg_user_id, title, category, event_date, event_time, safe_str(d.get('notes'))))
        existing.add(dedup_key)
        imported += 1
    conn.commit()
    return imported


def import_all_user_data(fs_db, conn, firebase_uid, pg_user_id, email):
    """Import all subcollection data for a single user."""
    print(f"\n  --- {email} (uid={firebase_uid[:12]}..., pg_id={pg_user_id}) ---")
    results = {}

    importers = [
        ('vitalsLog', lambda: import_vitals(fs_db, conn, firebase_uid, pg_user_id)),
        ('nutritionLog', lambda: import_nutrition(fs_db, conn, firebase_uid, pg_user_id)),
        ('medicationLog', lambda: import_medications(fs_db, conn, firebase_uid, pg_user_id)),
        ('eliminationLog', lambda: import_elimination(fs_db, conn, firebase_uid, pg_user_id)),
        ('symptomLog', lambda: import_symptoms(fs_db, conn, firebase_uid, pg_user_id)),
        ('journalEntries', lambda: import_journal(fs_db, conn, firebase_uid, pg_user_id)),
        ('hemodialysisFlowsheets', lambda: import_hd_flowsheets(fs_db, conn, firebase_uid, pg_user_id)),
        ('labReports', lambda: import_lab_reports(fs_db, conn, firebase_uid, pg_user_id)),
        ('scheduledEvents', lambda: import_scheduled_events(fs_db, conn, firebase_uid, pg_user_id)),
    ]

    for name, fn in importers:
        try:
            result = fn()
            if isinstance(result, tuple):
                results[name] = result
                if len(result) == 3:
                    total = sum(result)
                else:
                    total = sum(result)
                if total > 0:
                    print(f"    {name}: {result}")
            else:
                results[name] = result
                if result > 0:
                    print(f"    {name}: {result}")
        except Exception as e:
            print(f"    {name}: ERROR - {e}")
            traceback.print_exc()
            conn.rollback()
            results[name] = 0

    return results


# ── Main ──────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ALAFIA: Full Firebase → PostgreSQL Migration")
    print(f"  Service Account: {os.path.basename(SERVICE_ACCOUNT)}")
    print(f"  Database: {DB_PARAMS['host']}:{DB_PARAMS['port']}/{DB_PARAMS['dbname']}")
    print(f"  Dry Run: {DRY_RUN}")
    print("=" * 60)

    # Connect to Firebase
    print("\nConnecting to Firebase...")
    cred = credentials.Certificate(SERVICE_ACCOUNT)
    app = firebase_admin.initialize_app(cred)
    fs_db = firestore.client()
    print("  Connected.")

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = False
    print("  Connected.")

    try:
        # Step 1: Migrate all users
        uid_to_pgid = migrate_auth_users(conn, fs_db)

        # Step 2: Import health data for each user
        print("\n" + "=" * 60)
        print("STEP 2: Importing Health Data")
        print("=" * 60)

        # Get email for each user
        cur = conn.cursor()
        for firebase_uid, pg_user_id in uid_to_pgid.items():
            cur.execute("SELECT email FROM users WHERE id = %s", (pg_user_id,))
            row = cur.fetchone()
            email = row[0] if row else '?'
            import_all_user_data(fs_db, conn, firebase_uid, pg_user_id, email)

        # Final report
        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE firebase_uid IS NOT NULL")
        print(f"\n  Migrated users: {cur.fetchone()[0]}")

        tables = [
            'vitals_logs', 'nutrition_logs', 'medications', 'bowel_movements',
            'vomiting_logs', 'urination_logs', 'symptom_logs', 'mood_entries',
            'therapy_sessions', 'intradialytic_readings', 'lab_results', 'calendar_events',
        ]
        print("\n  Record counts:")
        for tbl in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                count = cur.fetchone()[0]
                if count > 0:
                    print(f"    {tbl}: {count:,}")
            except Exception:
                conn.rollback()

        if DRY_RUN:
            print("\n  [DRY RUN] Rolling back all changes...")
            conn.rollback()
        else:
            conn.commit()
            print("\n  All changes committed.")

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()
        firebase_admin.delete_app(app)


if __name__ == '__main__':
    main()
