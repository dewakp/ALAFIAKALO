"""
Firebase Sync Pipeline — real-time & batch sync from Firestore → PostgreSQL.

Components:
  1. Firebase Auth token verification (SSO bridge)
  2. Periodic polling sync for Firestore subcollection changes
  3. On-demand sync trigger via API

Designed to run as a background task inside the FastAPI app.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth, firestore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session as _async_session_factory
from app.core.units import to_celsius as units_to_celsius

logger = logging.getLogger(__name__)

# ── Firebase App Singleton ────────────────────────────────

_firebase_app: Optional[firebase_admin.App] = None
_firestore_client = None


def get_firebase_app() -> Optional[firebase_admin.App]:
    """Initialize Firebase Admin SDK (singleton)."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    sa_path = settings.FIREBASE_SERVICE_ACCOUNT
    if not sa_path:
        # Try known location relative to project root
        candidates = [
            os.path.join(os.path.dirname(__file__), '..', '..', '..', '..',
                         'alafia-9i0hh-firebase-adminsdk-fbsvc-fb3e9a5364.json'),
        ]
        for c in candidates:
            if os.path.isfile(c):
                sa_path = os.path.abspath(c)
                break

    if not sa_path or not os.path.isfile(sa_path):
        logger.warning("Firebase service account not found — sync disabled")
        return None

    try:
        cred = credentials.Certificate(sa_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized (project: %s)", _firebase_app.project_id)
        return _firebase_app
    except Exception as e:
        logger.error("Failed to initialize Firebase: %s", e)
        return None


def get_firestore_client():
    """Get Firestore client (singleton)."""
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    app = get_firebase_app()
    if app is None:
        return None
    _firestore_client = firestore.client()
    return _firestore_client


# ── Firebase Auth Token Verification ──────────────────────

async def verify_firebase_token(id_token: str) -> Optional[dict]:
    """
    Verify a Firebase ID token and return decoded claims.
    Returns None if invalid.
    """
    app = get_firebase_app()
    if app is None:
        return None
    try:
        decoded = firebase_auth.verify_id_token(id_token)
        return decoded
    except Exception as e:
        logger.debug("Firebase token verification failed: %s", e)
        return None


async def get_or_create_user_from_firebase(
    db: AsyncSession, firebase_claims: dict
) -> Optional[int]:
    """
    Given decoded Firebase token claims, find or create the local user.
    Returns the PostgreSQL user ID.
    """

    uid = firebase_claims.get('uid')
    email = firebase_claims.get('email', f"firebase_{uid[:8]}@alafia.local")
    name = firebase_claims.get('name', email.split('@')[0])

    # Look up by firebase_uid first
    result = await db.execute(
        text("SELECT id FROM users WHERE firebase_uid = :uid"),
        {"uid": uid}
    )
    row = result.first()
    if row:
        return row[0]

    # Look up by email (might have been created locally)
    result = await db.execute(
        text("SELECT id, firebase_uid FROM users WHERE email = :email"),
        {"email": email}
    )
    row = result.first()
    if row:
        # Link existing local user to Firebase UID
        await db.execute(
            text("UPDATE users SET firebase_uid = :uid, auth_provider = :provider WHERE id = :id"),
            {"uid": uid, "provider": firebase_claims.get('firebase', {}).get('sign_in_provider', 'firebase'), "id": row[0]}
        )
        return row[0]

    # Create new user
    from app.core.security import hash_password
    import secrets
    temp_hash = hash_password(secrets.token_urlsafe(32))

    result = await db.execute(
        text("""
            INSERT INTO users (email, hashed_password, full_name, firebase_uid, auth_provider,
                               is_active, created_at, updated_at)
            VALUES (:email, :hash, :name, :uid, :provider, true, NOW(), NOW())
            RETURNING id
        """),
        {
            "email": email,
            "hash": temp_hash,
            "name": name,
            "uid": uid,
            "provider": firebase_claims.get('firebase', {}).get('sign_in_provider', 'firebase'),
        }
    )
    new_id = result.scalar_one()
    logger.info("Created user %d from Firebase UID %s (%s)", new_id, uid[:12], email)
    return new_id


# ── Sync Pipeline: Polling-based ──────────────────────────

# Sentinel returned by _upsert_domain when a Firebase doc is a known source
# data-entry error that must NOT be imported (and must NOT be ledgered, so a
# later source-side correction can still flow in).
_SKIP_RECORD = object()


class _SkipRecord(Exception):
    """Raised inside a doc savepoint to skip importing a known-bad record."""

# Medication names (normalized: lower-cased, collapsed whitespace) that are known
# source data-entry errors and must never be imported. "Sodium Carbonate" is a
# mislabel for "Sodium Bicarbonate"; per product decision it (incl. the lone
# implausible 22500 mg 2025-06-16 dose) is left at the source and skipped here.
# Removing/merging must be fixed in Firebase; this guard just stops the bad data
# from reaching PostgreSQL on each sync.
_MED_NAME_BLOCKLIST = {"sodium carbonate"}


def _normalize_med_name(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


class FirebaseSyncPipeline:
    """
    Polls Firestore for changes since last sync checkpoint and upserts into PG.
    Designed to be run periodically via BackgroundTasks or APScheduler.
    """

    SUBCOLLECTIONS = [
        'vitalsLog', 'nutritionLog', 'medicationLog', 'eliminationLog',
        'symptomLog', 'journalEntries', 'hemodialysisFlowsheets',
        'labReports', 'scheduledEvents',
    ]

    # Maps subcollection name → the Firestore data field used as the record timestamp.
    # Used to build progressive WHERE clauses so we only fetch docs newer than the watermark.
    _SUBCOL_TS_FIELD: dict[str, str] = {
        'vitalsLog':              'timestamp',
        'nutritionLog':           'timestamp',
        'medicationLog':          'timestamp',
        'eliminationLog':         'timestamp',
        'symptomLog':             'timestamp',
        'journalEntries':         'created_at',
        'hemodialysisFlowsheets': 'date',
        'labReports':             'date',
        'scheduledEvents':        'date',
    }

    def __init__(self):
        self._last_sync: dict[str, datetime] = {}  # {firebase_uid: last_sync_time}

    async def sync_all_users(self, db: AsyncSession) -> dict:
        """Sync all Firebase-linked users. Returns {uid: records_synced}."""
        fs = get_firestore_client()
        if fs is None:
            logger.warning("Firestore client not available — skipping sync")
            return {}

        # Get all users with firebase_uid
        result = await db.execute(
            text("SELECT id, firebase_uid, email FROM users WHERE firebase_uid IS NOT NULL")
        )
        users = result.fetchall()
        logger.info("Syncing %d Firebase-linked users", len(users))

        sync_results = {}
        for pg_id, firebase_uid, email in users:
            # Use a fresh session per user so a corrupted transaction
            # on one user never poisons the next user's sync.
            try:
                async with _async_session_factory() as user_db:
                    count = await self._sync_user(user_db, fs, pg_id, firebase_uid)
                sync_results[firebase_uid] = count
                if count > 0:
                    logger.info("Synced %d records for %s", count, email)
            except Exception as e:
                logger.error("Sync failed for %s: %s", email, e)
                sync_results[firebase_uid] = -1

        return sync_results

    async def _sync_user(self, db: AsyncSession, fs, pg_id: int, firebase_uid: str) -> int:
        """
        Progressive sync: for each subcollection fetch only docs whose timestamp
        field is strictly newer than the latest watermark stored in synced_records.
        Uses savepoints for per-doc error isolation so a bad doc never discards
        the records that were already written in this run.
        Commits once per user after all subcollections are processed.
        """
        total = 0

        for subcol_name in self.SUBCOLLECTIONS:
            try:
                col_ref = (
                    fs.collection('users')
                      .document(firebase_uid)
                      .collection(subcol_name)
                )

                # --- 1. Ids we have already synced for this user/subcollection ----
                # We diff by document id rather than a "newer-than-timestamp" query:
                # Firestore docs carry an arbitrary, often BACK-DATED string `date`
                # field (and inconsistent/absent createdAt), so no server-side time
                # filter reliably finds newly-added docs. Id-diffing always does.
                synced_rows = await db.execute(
                    text("""
                        SELECT external_id FROM synced_records
                        WHERE user_id = :uid AND platform = 'firebase'
                          AND data_type = :dtype
                    """),
                    {"uid": pg_id, "dtype": subcol_name},
                )
                synced_ids = {r[0] for r in synced_rows}

                # --- 2. Cheap aggregation gate to avoid full reads when unchanged -
                # A COUNT() aggregation is ~1 read; only stream the whole collection
                # when it actually holds more docs than we've synced.
                try:
                    agg = col_ref.count().get()
                    fs_count = int(agg[0][0].value)
                except Exception:
                    fs_count = None  # aggregation unsupported → always do full read
                if fs_count is not None and fs_count <= len(synced_ids):
                    continue

                # --- 3. Full fetch, keep only ids we don't already have -----------
                docs = [
                    d for d in col_ref.stream()
                    if f"{subcol_name}/{d.id}" not in synced_ids
                ]
                if not docs:
                    continue

                # --- 4. Upsert each new doc with savepoint isolation --------------
                for doc in docs:
                    data = doc.to_dict()
                    doc_id = doc.id
                    ext_id = f"{subcol_name}/{doc_id}"
                    src_ts = self._extract_ts(data)

                    try:
                        # Savepoint: a failure here rolls back only this doc,
                        # leaving all previously committed records intact.
                        async with db.begin_nested():
                            record_id = await self._upsert_domain(
                                db, subcol_name, pg_id, doc_id, data, src_ts
                            )
                            if record_id is _SKIP_RECORD:
                                # Known source data-entry error — do not import
                                # and do not write a ledger row (so a corrected
                                # source record can still sync later).
                                raise _SkipRecord()
                            await db.execute(
                                text("""
                                    INSERT INTO synced_records
                                        (user_id, platform, data_type, external_id,
                                         target_table, target_record_id,
                                         source_timestamp, synced_at)
                                    VALUES (:uid, 'firebase', :dtype, :ext_id,
                                            :tbl, :rec_id, :src_ts, NOW())
                                    ON CONFLICT (user_id, platform, data_type, external_id)
                                    DO NOTHING
                                """),
                                {
                                    "uid":    pg_id,
                                    "ext_id": ext_id,
                                    "dtype":  subcol_name,
                                    "tbl":    self._domain_table(subcol_name),
                                    "rec_id": record_id,
                                    "src_ts": src_ts,
                                },
                            )
                        total += 1
                    except _SkipRecord:
                        # Intentional skip — the savepoint already rolled back
                        # any partial work; do not count it as synced.
                        logger.info(
                            "Skipped known erroneous %s/%s for user %d (not imported)",
                            subcol_name, doc_id, pg_id,
                        )
                    except Exception as doc_err:
                        logger.warning(
                            "Skipped %s/%s for user %d: %s",
                            subcol_name, doc_id, pg_id, doc_err,
                        )
                        # NOTE: do NOT call db.rollback() here. The
                        # `async with db.begin_nested()` block above already
                        # issued ROLLBACK TO SAVEPOINT on the way out, which
                        # both clears asyncpg's aborted-transaction state AND
                        # preserves every record written earlier in this run.
                        # A full db.rollback() would discard the entire user
                        # transaction (all prior subcollections), so the final
                        # commit would persist almost nothing — the cause of the
                        # "synced N records but 0 rows in DB" bug.

            except Exception as subcol_err:
                logger.error(
                    "Error syncing subcollection %s for user %d: %s",
                    subcol_name, pg_id, subcol_err,
                )
                # Do NOT roll back the whole session — other subcollections may
                # have succeeded.  Skip this one and continue.

        # Commit all insertions for this user in one round-trip
        await db.commit()
        self._last_sync[firebase_uid] = datetime.now(timezone.utc)
        return total

    @staticmethod
    def _domain_table(subcol_name: str) -> str:
        return {
            'vitalsLog':               'vitals_logs',
            'nutritionLog':            'nutrition_logs',
            'medicationLog':           'medication_dose_logs',
            'eliminationLog':          'bowel_movements',
            'symptomLog':              'symptom_logs',
            'journalEntries':          'mood_entries',
            'hemodialysisFlowsheets':  'therapy_sessions',
            'labReports':              'lab_results',
            'scheduledEvents':         'calendar_events',
        }.get(subcol_name, subcol_name)

    @staticmethod
    def _extract_ts(data: dict) -> datetime:
        raw = (
            data.get('timestamp') or data.get('created_at') or
            data.get('recordedAt') or data.get('date')
        )
        if raw is None:
            return datetime.now(timezone.utc)
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        try:
            from dateutil.parser import parse as parse_dt
            return parse_dt(str(raw))
        except Exception:
            return datetime.now(timezone.utc)

    async def _upsert_domain(
        self, db: AsyncSession, subcol_name: str, user_id: int,
        doc_id: str, data: dict, src_ts: datetime
    ) -> Optional[int]:
        """Write Firestore doc into the appropriate domain table. Returns inserted PG row id."""
        log_date = src_ts.date()

        # ── vitalsLog → vitals_logs ───────────────────────────
        if subcol_name == 'vitalsLog':
            log_time = _parse_time_str(data.get('time')) or (src_ts.time() if src_ts else None)
            r = await db.execute(text("""
                INSERT INTO vitals_logs (user_id, log_date, log_time,
                    blood_pressure_systolic, blood_pressure_diastolic,
                    heart_rate_bpm, body_temperature_c, blood_oxygen_pct,
                    weight_kg, blood_glucose_mg_dl, glucose_timing,
                    respiratory_rate, pain_level, notes, created_at)
                VALUES (:uid, :log_date, :log_time,
                    :sys, :dia, :hr, :temp, :spo2,
                    :weight, :glucose, :glucose_timing,
                    :rr, :pain, :notes, NOW())
                RETURNING id
            """), {
                "uid": user_id, "log_date": log_date,
                "log_time": log_time,
                "sys":    _int(data, 'bloodPressureSystolic', 'systolic', 'bp_systolic', 'bpSystolic'),
                "dia":    _int(data, 'bloodPressureDiastolic', 'diastolic', 'bp_diastolic', 'bpDiastolic'),
                "hr":     _int(data, 'heartRate', 'heart_rate', 'pulse', 'heartRate'),
                "temp":   _to_celsius(_float(data, 'temperature', 'bodyTemperature', 'temp_c', 'temperatureCelsius'),
                                      data.get('temperatureUnit') or data.get('bodyTemperatureUnit')),
                "spo2":   _float(data, 'oxygenSaturation', 'spo2', 'bloodOxygen', 'spO2'),
                "weight": _float(data, 'weight', 'weightKg', 'weight_kg', 'currentWeight'),
                "glucose": _float(data, 'bloodGlucose', 'glucose', 'blood_glucose', 'bloodGlucoseMgDl'),
                "glucose_timing": data.get('glucoseTiming') or data.get('glucose_timing'),
                "rr":     _int(data, 'respiratoryRate', 'respiratory_rate', 'respRate'),
                "pain":   _int(data, 'painLevel', 'pain', 'pain_score'),
                "notes":  data.get('notes') or data.get('comment'),
            })
            return r.scalar_one_or_none()

        # ── nutritionLog → nutrition_logs ─────────────────────
        if subcol_name == 'nutritionLog':
            ai_items = data.get('aiAnalyzedItems') or []
            # serving size from first AI-analysed component if available
            serving = (ai_items[0].get('quantityUsed') if ai_items else None) or data.get('servingSize') or data.get('serving_size')
            # compose notes with metadata that has no dedicated column
            notes_parts = []
            if data.get('aiProcessedSummary'): notes_parts.append(data['aiProcessedSummary'])
            if data.get('notes'):         notes_parts.append(data['notes'])
            notes_str = ' | '.join(notes_parts) or None
            # store full AI breakdown and image URIs in extended_nutrients JSON
            image_uris = data.get('foodImageUris') or data.get('foodImageUri')
            ext_nutrients = json.dumps({'aiAnalyzedItems': ai_items, 'foodImageUris': image_uris}) if (ai_items or image_uris) else None
            meal_type = data.get('mealType') or data.get('meal_type') or 'unspecified'
            food_name = data.get('foodItem') or data.get('foodName') or data.get('food_name') or data.get('name') or 'unknown'

            # Content-level dedup: ALAFIA/Firebase sometimes holds more than one
            # nutritionLog document for the same meal (the per-doc external_id
            # dedup cannot catch this because the docs have different ids). If a
            # nutrition row already exists for this (user, date, meal, food) we
            # link the ledger to it instead of inserting a duplicate.
            existing = await db.execute(text("""
                SELECT id FROM nutrition_logs
                WHERE user_id = :uid AND log_date = :log_date
                  AND meal_type = :meal_type AND food_name = :food_name
                LIMIT 1
            """), {
                "uid": user_id, "log_date": log_date,
                "meal_type": meal_type, "food_name": food_name,
            })
            existing_id = existing.scalar_one_or_none()
            if existing_id is not None:
                return existing_id

            r = await db.execute(text("""
                INSERT INTO nutrition_logs (user_id, log_date, meal_type, food_name,
                    serving_size, calories, protein_g, carbs_g, fat_g, fiber_g,
                    sugar_g, cholesterol_mg, sodium_mg, potassium_mg,
                    calcium_mg, iron_mg, phosphorus_mg,
                    vitamin_d_iu, vitamin_b12_mcg, vitamin_b9_folate_mcg,
                    start_time, end_time, pre_meal_weight_kg, post_meal_weight_kg,
                    food_image_uris, recipe_url,
                    extended_nutrients, notes, created_at)
                VALUES (:uid, :log_date, :meal_type, :food_name,
                    :serving, :cal, :protein, :carbs, :fat, :fiber,
                    :sugar, :cholesterol, :sodium, :potassium,
                    :calcium, :iron, :phosphorus,
                    :vitamin_d, :vitamin_b12, :folate,
                    :start_time, :end_time, :pre_weight, :post_weight,
                    :food_image_uris, :recipe_url,
                    CAST(:ext_nutrients AS JSON), :notes, NOW())
                RETURNING id
            """), {
                "uid": user_id, "log_date": log_date,
                "meal_type":     meal_type,
                "food_name":     food_name,
                "serving":       serving,
                "cal":           _float(data, 'calories', 'kcal', 'energy'),
                "protein":       _float(data, 'protein', 'proteinG', 'protein_g'),
                "carbs":         _float(data, 'carbs', 'carbohydrates', 'carbs_g'),
                "fat":           _float(data, 'fat', 'totalFat', 'fat_g'),
                "fiber":         _float(data, 'fiber', 'dietaryFiber', 'fiber_g'),
                "sugar":         _float(data, 'sugar', 'sugars', 'sugar_g'),
                "cholesterol":   _float(data, 'cholesterol', 'cholesterol_mg'),
                "sodium":        _float(data, 'sodium', 'sodiumMg', 'sodium_mg'),
                "potassium":     _float(data, 'potassium', 'potassiumMg', 'potassium_mg'),
                "calcium":       _float(data, 'calcium', 'calcium_mg'),
                "iron":          _float(data, 'iron', 'iron_mg'),
                "phosphorus":    _float(data, 'phosphate', 'phosphorus', 'phosphorus_mg'),
                "vitamin_d":     _float(data, 'vitaminD', 'vitamin_d', 'vitamin_d_iu'),
                "vitamin_b12":   _float(data, 'vitaminB12', 'vitamin_b12', 'vitamin_b12_mcg'),
                "folate":        _float(data, 'folicAcid', 'folate', 'vitamin_b9_folate_mcg'),
                "start_time":    _parse_time_str(data.get('startTime') or data.get('start_time')),
                "end_time":      _parse_time_str(data.get('endTime') or data.get('end_time')),
                "pre_weight":    _float(data, 'preMealWeightKg', 'pre_meal_weight_kg'),
                "post_weight":   _float(data, 'postMealWeightKg', 'post_meal_weight_kg'),
                "food_image_uris": json.dumps(image_uris) if isinstance(image_uris, list) else (str(image_uris) if image_uris else None),
                "recipe_url":    data.get('recipeUrl') or data.get('recipe_url'),
                "ext_nutrients": ext_nutrients,
                "notes":         notes_str,
            })
            return r.scalar_one_or_none()

        # ── medicationLog → medication_dose_logs (+ medications catalog) ──
        # A medicationLog doc is a dose-taking EVENT, not a prescription.
        # We upsert ONE medications catalog row per (user, drug name) and append
        # each event to medication_dose_logs, linked to that catalog row.
        if subcol_name == 'medicationLog':
            # Time + pre/post vitals are first-class columns now. The mobile app's
            # aiNutritionalAnalysis blob (often a Gemini error) is intentionally
            # NOT stored — notes hold only the user's own free text.
            med_log_time = _parse_time_str(data.get('time')) or (src_ts.time() if src_ts else None)
            pre_sys = _int(data, 'preMedicationBloodPressureSystolic')
            pre_dia = _int(data, 'preMedicationBloodPressureDiastolic')
            pre_hr  = _int(data, 'preMedicationHeartRate')
            post_sys = _int(data, 'postMedicationBloodPressureSystolic')
            post_dia = _int(data, 'postMedicationBloodPressureDiastolic')
            post_hr  = _int(data, 'postMedicationHeartRate')
            notes_str = (data.get('notes') or '').strip() or None

            # parse dosage: '2000 mg' → amount=2000.0, unit='mg'
            raw_dosage = data.get('dosage') or data.get('dose') or ''
            parts = str(raw_dosage).split(None, 1)
            dosage_token = parts[0] if parts else ''
            dosage_unit = parts[1] if len(parts) > 1 else (data.get('dosageUnit') or data.get('unit') or '')
            try:
                numeric = re.sub(r'[^0-9.]', '', dosage_token)
                dose_amount = float(numeric) if numeric else 0.0
            except ValueError:
                dose_amount = 0.0
            dose_unit = (str(dosage_unit).strip() or 'unit')
            med_name = data.get('medicationName') or data.get('name') or 'unknown'

            # Skip known source data-entry errors (e.g. "Sodium Carbonate", a
            # mislabel for "Sodium Bicarbonate"). Not imported and not ledgered,
            # so a corrected source record can still sync later.
            if _normalize_med_name(med_name) in _MED_NAME_BLOCKLIST:
                return _SKIP_RECORD

            # 1) Link to an existing medications LIST row if the user already has
            #    this drug on their list — but NEVER create one here.
            #    A medicationLog doc is a dose TAKEN event; "taken" is not the
            #    same as the medication LIST (the curated prescription record).
            #    Auto-creating a list row from a single dose would fabricate
            #    prescriptions. The LIST is owned by its own source (the user /
            #    prescriptions); dose logs may leave medication_id NULL.
            cat = await db.execute(text("""
                SELECT id FROM medications WHERE user_id = :uid AND name = :name
                LIMIT 1
            """), {"uid": user_id, "name": med_name})
            med_id = cat.scalar_one_or_none()  # may be None — that's fine
            dl = await db.execute(text("""
                INSERT INTO medication_dose_logs
                    (user_id, medication_id, medication_name, log_date, log_time,
                     dose_amount, dose_unit,
                     pre_systolic_bp, pre_diastolic_bp, pre_heart_rate,
                     post_systolic_bp, post_diastolic_bp, post_heart_rate,
                     notes, nutrients_resolved, created_at)
                VALUES (:uid, :med_id, :name, :log_date, :log_time,
                     :amt, :unit,
                     :pre_sys, :pre_dia, :pre_hr,
                     :post_sys, :post_dia, :post_hr,
                     :notes, false, NOW())
                ON CONFLICT (user_id, log_date, log_time, medication_name, dose_amount, dose_unit)
                DO NOTHING
                RETURNING id
            """), {
                "uid":      user_id,
                "med_id":   med_id,
                "name":     med_name,
                "log_date": log_date,
                "log_time": med_log_time,
                "amt":      dose_amount,
                "unit":     dose_unit,
                "pre_sys":  pre_sys, "pre_dia": pre_dia, "pre_hr": pre_hr,
                "post_sys": post_sys, "post_dia": post_dia, "post_hr": post_hr,
                "notes":    notes_str,
            })
            dose_id = dl.scalar_one_or_none()
            if dose_id is None:
                # Conflict on an identical same-day dose — link the ledger to the
                # existing dose-log row so the doc is still marked as synced.
                ex = await db.execute(text("""
                    SELECT id FROM medication_dose_logs
                    WHERE user_id = :uid AND log_date = :log_date
                      AND medication_name = :name AND dose_amount = :amt
                      AND dose_unit = :unit
                    LIMIT 1
                """), {
                    "uid": user_id, "log_date": log_date, "name": med_name,
                    "amt": dose_amount, "unit": dose_unit,
                })
                dose_id = ex.scalar_one_or_none()
            return dose_id

        # ── eliminationLog → bowel_movements | urination_logs | vomiting_logs ──
        # Elimination covers poop, urine AND vomit — route each event to its own
        # table by eventType so the matching Elimination tab surfaces it.
        if subcol_name == 'eliminationLog':
            log_time = _parse_time_str(data.get('time')) or (src_ts.time() if src_ts else None)
            elim_notes = data.get('description') or data.get('notes') or None
            etype = (data.get('eventType') or data.get('event_type') or '').strip().lower()
            pre_w  = _float(data, 'preEventWeightKg', 'pre_event_weight_kg')
            post_w = _float(data, 'postEventWeightKg', 'post_event_weight_kg')
            # Weights/image aren't first-class columns on urine/vomit tables —
            # preserve them in notes so nothing is lost.
            extra = []
            if pre_w is not None:  extra.append(f"pre-weight {pre_w}kg")
            if post_w is not None: extra.append(f"post-weight {post_w}kg")
            notes_plus = " | ".join(filter(None, [elim_notes, "; ".join(extra) or None])) or None

            image_uri = data.get('imageUri') or data.get('image_uri')

            if etype in ("vomit", "vomiting", "throw up", "throwup", "emesis"):
                r = await db.execute(text("""
                    INSERT INTO vomiting_logs (user_id, log_date, log_time,
                        pre_event_weight_kg, post_event_weight_kg, image_uri, notes, created_at)
                    VALUES (:uid, :log_date, :log_time, :pre, :post, :img, :notes, NOW())
                    RETURNING id
                """), {"uid": user_id, "log_date": log_date, "log_time": log_time,
                       "pre": pre_w, "post": post_w, "img": image_uri, "notes": elim_notes})
                return r.scalar_one_or_none()

            if etype in ("urine", "urination", "pee", "void", "voiding"):
                r = await db.execute(text("""
                    INSERT INTO urination_logs (user_id, log_date, log_time,
                        pre_event_weight_kg, post_event_weight_kg, image_uri, notes, created_at)
                    VALUES (:uid, :log_date, :log_time, :pre, :post, :img, :notes, NOW())
                    RETURNING id
                """), {"uid": user_id, "log_date": log_date, "log_time": log_time,
                       "pre": pre_w, "post": post_w, "img": image_uri, "notes": elim_notes})
                return r.scalar_one_or_none()

            # Default (poop / bowel / unspecified) → bowel_movements
            r = await db.execute(text("""
                INSERT INTO bowel_movements (user_id, log_date, log_time,
                    bristol_scale, color, consistency, event_type,
                    blood_present, pain_level,
                    pre_event_weight_kg, post_event_weight_kg, image_uri,
                    notes, created_at)
                VALUES (:uid, :log_date, :log_time,
                    :bristol, :color, :consistency, :event_type,
                    :blood, :pain,
                    :pre_weight, :post_weight, :image_uri,
                    :notes, NOW())
                RETURNING id
            """), {
                "uid": user_id, "log_date": log_date,
                "log_time":    log_time,
                "bristol":     _int(data, 'bristolScale', 'bristol', 'stoolType'),
                "color":       data.get('color') or data.get('stoolColor'),
                "consistency": data.get('consistency'),
                "event_type":  data.get('eventType') or data.get('event_type'),
                "blood":       data.get('bloodPresent') or data.get('blood'),
                "pain":        _int(data, 'painLevel', 'pain'),
                "pre_weight":  pre_w,
                "post_weight": post_w,
                "image_uri":   data.get('imageUri') or data.get('image_uri'),
                "notes":       elim_notes,
            })
            return r.scalar_one_or_none()

        # ── symptomLog → symptom_logs ──────────────────────────
        if subcol_name == 'symptomLog':
            # durationMinutes (Firebase) → duration_hours (PG)
            dur_mins = _float(data, 'durationMinutes', 'duration_minutes')
            dur_hours = (dur_mins / 60.0) if dur_mins is not None else _float(data, 'durationHours', 'duration_hours', 'duration')
            r = await db.execute(text("""
                INSERT INTO symptom_logs (user_id, log_date, symptom_name,
                    severity, symptom_type, body_part,
                    onset, duration_hours, triggers, relievers, notes, created_at)
                VALUES (:uid, :log_date, :symptom_name,
                    :severity, :stype, :body_part,
                    :onset, :duration, :triggers, :relievers, :notes, NOW())
                RETURNING id
            """), {
                "uid": user_id, "log_date": log_date,
                "symptom_name": data.get('symptom') or data.get('symptomName') or data.get('name') or 'unspecified',
                "severity":     _int(data, 'severity', 'intensity', 'painLevel'),
                "stype":        data.get('symptomType') or data.get('type'),
                "body_part":    data.get('bodyPart') or data.get('location'),
                "onset":        data.get('onset'),
                "duration":     dur_hours,
                "triggers":     data.get('triggers'),
                "relievers":    data.get('reliefMeasures') or data.get('relievers'),
                "notes":        data.get('notes'),
            })
            return r.scalar_one_or_none()

        # ── journalEntries → mood_entries ─────────────────────
        # The Journal page reads mood_entries, so journal docs must land there
        # (not lifestyle_entries, which the Daily Vitals page reads).
        if subcol_name == 'journalEntries':
            # Map a free-text/emoji mood to the 1-10 score mood_entries expects.
            mood_raw = data.get('mood')
            mood_score = _int(data, 'moodScore', 'mood_score')
            if mood_score is None and mood_raw is not None:
                try:
                    mood_score = max(1, min(10, int(float(mood_raw))))
                except (TypeError, ValueError):
                    mood_score = {
                        'terrible': 2, 'bad': 3, 'low': 4, 'sad': 4, 'okay': 5, 'ok': 5,
                        'neutral': 5, 'fine': 6, 'good': 7, 'happy': 8, 'great': 9, 'excellent': 10,
                    }.get(str(mood_raw).strip().lower())
            if mood_score is None:
                mood_score = 5  # mood_score is NOT NULL; default to neutral

            j_parts = []
            if mood_raw:                j_parts.append(f"mood={mood_raw}")
            if data.get('activities'):  j_parts.append(f"activities: {data['activities']}")
            if data.get('nutrition'):   j_parts.append(f"nutrition: {data['nutrition']}")
            if data.get('content') or data.get('text') or data.get('body'):
                j_parts.append(data.get('content') or data.get('text') or data.get('body') or '')
            notes_str = ' | '.join(j_parts)[:2000] or None

            r = await db.execute(text("""
                INSERT INTO mood_entries (user_id, entry_date, mood_score,
                    sleep_hours, emotions, journal_entry, notes, created_at)
                VALUES (:uid, :entry_date, :mood_score,
                    :sleep_hours, :emotions, :journal_entry, :notes, NOW())
                RETURNING id
            """), {
                "uid": user_id, "entry_date": log_date,
                "mood_score":   mood_score,
                "sleep_hours":  _float(data, 'hoursSlept', 'sleep_hours', 'sleepHours'),
                "emotions":     data.get('feelings') or data.get('emotions'),
                "journal_entry": data.get('content') or data.get('text') or data.get('body'),
                "notes":        notes_str,
            })
            return r.scalar_one_or_none()

        # ── hemodialysisFlowsheets → therapy_sessions ─────────
        if subcol_name == 'hemodialysisFlowsheets':
            # Parse treatment start / end datetimes
            start_dt = _parse_session_dt(data.get('date'), data.get('treatmentStartTime')) or src_ts
            end_dt   = _parse_session_dt(
                data.get('postTreatmentReadingDate') or data.get('date'),
                data.get('treatmentEndTime')
            )
            # If end time < start time, assume it rolled over midnight (+1 day)
            if end_dt and start_dt and end_dt < start_dt:
                end_dt = end_dt + timedelta(days=1)
            # therapy_sessions timestamp columns are TIMESTAMP WITHOUT TIME ZONE;
            # asyncpg rejects tz-aware datetimes for naive columns, so normalize
            # both to naive UTC before binding.
            if start_dt and start_dt.tzinfo is not None:
                start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
            if end_dt and end_dt.tzinfo is not None:
                end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
            # Duration: parse '4:14' → 254 minutes
            duration_min = _parse_hhmm_to_minutes(data.get('totalMachineTimeHours'))
            if duration_min is None:
                duration_min = _int(data, 'durationMinutes', 'duration')
            # Temperature: convert Fahrenheit → Celsius if needed
            pre_temp  = _to_celsius(data.get('preTreatmentTemperatureCelsius'),  data.get('preTreatmentTemperatureUnit'))
            post_temp = _to_celsius(data.get('postTreatmentTemperatureCelsius'), data.get('postTreatmentTemperatureUnit'))
            # fluid: Firebase stores litres, PG stores ml
            fluid_liters = _float(data, 'fluidRemovedLiters', 'fluidRemoved', 'ufVolume')
            fluid_ml = (fluid_liters * 1000) if fluid_liters is not None else None
            # Intra-dialytic readings & medications stored as JSON in patient_notes
            extra_parts = []
            if data.get('intraDialyticReadings'):
                extra_parts.append(f"intradialytic={json.dumps(data['intraDialyticReadings'])}")
            if data.get('medicationsDuringTreatment'):
                extra_parts.append(f"meds={json.dumps(data['medicationsDuringTreatment'])}")
            if data.get('postDialysisAssessment'): extra_parts.append(data['postDialysisAssessment'])
            if data.get('generalNotes'):           extra_parts.append(data['generalNotes'])
            patient_notes = ' | '.join(extra_parts)[:4000] or None
            r = await db.execute(text("""
                INSERT INTO therapy_sessions (
                    user_id, condition_id, therapy_type,
                    scheduled_date, actual_start_time, actual_end_time, duration_minutes,
                    pre_dialysis_weight_kg, post_dialysis_weight_kg, dry_weight_kg,
                    fluid_removed_ml, total_dialysate_liters, total_blood_volume_processed,
                    dialysis_access_type, dialyzer_appearance,
                    facility_name, facility_address,
                    attending_physician, rn_reviewer, cycler_number,
                    sak_lot, cartridge_lot,
                    pre_systolic_bp, pre_diastolic_bp, pre_heart_rate, pre_temperature,
                    post_systolic_bp, post_diastolic_bp, post_heart_rate, post_temperature,
                    pre_standing_systolic_bp, pre_standing_diastolic_bp, pre_standing_heart_rate,
                    post_standing_systolic_bp, post_standing_diastolic_bp, post_standing_heart_rate,
                    complications, patient_notes, status,
                    created_at, updated_at)
                VALUES (
                    :uid, NULL, 'HEMODIALYSIS',
                    :scheduled_date, :actual_start, :actual_end, :duration,
                    :pre_wt, :post_wt, :dry_wt,
                    :fluid_ml, :total_dialysate, :total_blood_vol,
                    :access_site, :dialyzer_type,
                    :facility_name, :facility_addr,
                    :physician, :rn_reviewer, :machine_no,
                    :sak_lot, :cartridge_lot,
                    :pre_sys, :pre_dia, :pre_hr, :pre_temp,
                    :post_sys, :post_dia, :post_hr, :post_temp,
                    :pre_st_sys, :pre_st_dia, :pre_st_hr,
                    :post_st_sys, :post_st_dia, :post_st_hr,
                    :complications, :patient_notes, 'COMPLETED',
                    NOW(), NOW())
                RETURNING id
            """), {
                "uid":           user_id,
                "scheduled_date": start_dt,
                "actual_start":  start_dt,
                "actual_end":    end_dt,
                "duration":      duration_min,
                "pre_wt":        _float(data, 'preWeightKg', 'preDialysisWeight', 'pre_weight'),
                "post_wt":       _float(data, 'postWeightKg', 'postDialysisWeight', 'post_weight'),
                "dry_wt":        _float(data, 'targetWeightKg', 'dryWeight', 'dry_weight_kg'),
                "fluid_ml":      fluid_ml,
                "total_dialysate": _float(data, 'totalDialysateUsedLiters'),
                "total_blood_vol": _float(data, 'totalBloodVolumeProcessedLiters'),
                "access_site":   data.get('accessSite') or data.get('dialysisAccess'),
                "dialyzer_type": data.get('dialyzerType'),
                "facility_name": data.get('dialysisCenterName') or data.get('facilityName'),
                "facility_addr": data.get('treatmentLocation'),
                "physician":     data.get('prescriberName') or data.get('attendingPhysician'),
                "rn_reviewer":   data.get('reviewerName') or data.get('rnReviewer'),
                "machine_no":    data.get('machineNo') or data.get('cyclerNumber'),
                "sak_lot":       data.get('dialyzerLotNumber'),
                "cartridge_lot": data.get('dialysateLotNumber'),
                "pre_sys":       _int(data, 'preTreatmentBPSittingSystolic'),
                "pre_dia":       _int(data, 'preTreatmentBPSittingDiastolic'),
                "pre_hr":        _int(data, 'preTreatmentHRSitting'),
                "pre_temp":      pre_temp,
                "post_sys":      _int(data, 'postTreatmentBPSittingSystolic'),
                "post_dia":      _int(data, 'postTreatmentBPSittingDiastolic'),
                "post_hr":       _int(data, 'postTreatmentHRSitting'),
                "post_temp":     post_temp,
                "pre_st_sys":    _int(data, 'preTreatmentBPStandingSystolic'),
                "pre_st_dia":    _int(data, 'preTreatmentBPStandingDiastolic'),
                "pre_st_hr":     _int(data, 'preTreatmentHRStanding'),
                "post_st_sys":   _int(data, 'postTreatmentBPStandingSystolic'),
                "post_st_dia":   _int(data, 'postTreatmentBPStandingDiastolic'),
                "post_st_hr":    _int(data, 'postTreatmentHRStanding'),
                "complications": data.get('intradialyticEventsOrComplications'),
                "patient_notes": patient_notes,
            })
            return r.scalar_one_or_none()

        # ── labReports → lab_results ──────────────────────────
        # Firebase stores a PANEL (array of items). Expand each item into its own row.
        if subcol_name == 'labReports':
            panel_name = data.get('panelName') or data.get('testName') or 'Panel'
            lab_name   = data.get('labName') or data.get('performingLab') or data.get('lab')
            doctor     = data.get('doctorName')
            items      = data.get('items') or []
            panel_notes = ' | '.join(filter(None, [
                data.get('notes'), data.get('sourceProvider'), data.get('uploadedFileName')
            ])) or None
            if not items:
                # No individual items — store the panel header as a single row
                items = [{'name': panel_name, 'value': None, 'unit': None, 'referenceRange': ''}]
            first_id = None
            for item in items:
                ref_range = item.get('referenceRange') or ''
                ref_low, ref_high = _parse_ref_range(ref_range)
                raw_val = item.get('value')
                num_val = None
                try:
                    num_val = float(raw_val) if raw_val not in (None, '', 'N/A', 'NEG', 'POS') else None
                except (ValueError, TypeError):
                    num_val = None
                r = await db.execute(text("""
                    INSERT INTO lab_results (user_id, test_date, test_name,
                        category, value, value_string, unit,
                        reference_range_low, reference_range_high,
                        performing_lab, ordering_provider, notes, status, created_at)
                    VALUES (:uid, :test_date, :test_name,
                        :category, :value, :value_str, :unit,
                        :ref_low, :ref_high,
                        :lab, :doctor, :notes, 'final', NOW())
                    RETURNING id
                """), {
                    "uid":        user_id,
                    "test_date":  log_date,
                    "test_name":  item.get('name') or panel_name,
                    "category":   panel_name,
                    "value":      num_val,
                    "value_str":  str(raw_val) if raw_val is not None else None,
                    "unit":       item.get('unit'),
                    "ref_low":    ref_low,
                    "ref_high":   ref_high,
                    "lab":        lab_name,
                    "doctor":     doctor,
                    "notes":      panel_notes,
                })
                row_id = r.scalar_one_or_none()
                if first_id is None:
                    first_id = row_id
            return first_id

        # ── scheduledEvents → calendar_events ─────────────────
        if subcol_name == 'scheduledEvents':
            # Combine date + time into a full datetime for event_date
            event_dt = _parse_session_dt(data.get('date'), data.get('time'))
            if event_dt is None:
                event_dt = datetime.combine(log_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            is_completed = data.get('isCompleted') or False
            cal_status = 'completed' if is_completed else 'scheduled'
            r = await db.execute(text("""
                INSERT INTO calendar_events (user_id, title, category,
                    event_date, all_day, status, description, notes,
                    created_at, updated_at)
                VALUES (:uid, :title, :category,
                    :event_date, false, :status, :description, :notes,
                    NOW(), NOW())
                RETURNING id
            """), {
                "uid": user_id,
                "title":      data.get('title') or data.get('name') or 'Event',
                "category":   data.get('eventType') or data.get('category') or data.get('type') or 'custom',
                "event_date": event_dt,
                "status":     cal_status,
                "description": data.get('description') or data.get('details'),
                "notes":       data.get('notes'),
            })
            return r.scalar_one_or_none()

        return None

    async def sync_single_user(self, db: AsyncSession, firebase_uid: str) -> int:
        """On-demand sync for a single user."""
        fs = get_firestore_client()
        if fs is None:
            return 0

        result = await db.execute(
            text("SELECT id FROM users WHERE firebase_uid = :uid"),
            {"uid": firebase_uid}
        )
        row = result.first()
        if not row:
            return 0

        return await self._sync_user(db, fs, row[0], firebase_uid)


# Singleton pipeline instance
sync_pipeline = FirebaseSyncPipeline()


# ── Field extraction helpers ──────────────────────────────

def _to_celsius(value: Optional[float], unit: Optional[str] = None) -> Optional[float]:
    """Convert temperature to Celsius (delegates to the canonical units module).

    Metric is LAFIAKALO's canonical system; temperatures are normalized to
    Celsius on import. See ``app.core.units`` for the full unit policy.
    """
    return units_to_celsius(value, unit)


def _float(data: dict, *keys) -> Optional[float]:
    for k in keys:
        v = data.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _int(data: dict, *keys) -> Optional[int]:
    v = _float(data, *keys)
    return int(v) if v is not None else None


def _parse_time_str(t: Optional[str]) -> Optional[object]:
    """Parse 'HH:MM' or 'HH:MM:SS' string → datetime.time, or None."""
    if not t or not isinstance(t, str):
        return None
    try:
        from datetime import time as dtime
        parts = t.strip().split(':')
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return dtime(h, m, s)
    except Exception:
        return None


def _parse_session_dt(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    """Combine a 'YYYY-MM-DD' date string and 'HH:MM' time string into a UTC datetime."""
    if not date_str:
        return None
    try:
        from dateutil.parser import parse as _parse
        base = _parse(str(date_str))
        t = _parse_time_str(time_str)
        if t:
            base = base.replace(hour=t.hour, minute=t.minute, second=t.second)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return base
    except Exception:
        return None


def _parse_hhmm_to_minutes(val) -> Optional[int]:
    """Parse '4:14' or 4.23 (decimal hours) → integer minutes, or None."""
    if val is None:
        return None
    s = str(val).strip()
    if ':' in s:
        try:
            h, m = s.split(':', 1)
            return int(h) * 60 + int(m)
        except Exception:
            return None
    try:
        return int(float(s) * 60)
    except Exception:
        return None


def _parse_ref_range(ref: str):
    """Parse '1.00 - 2.50' → (1.0, 2.5). Returns (None, None) on failure."""
    if not ref:
        return None, None
    try:
        parts = ref.replace('\u2013', '-').split('-')
        if len(parts) == 2:
            return float(parts[0].strip()), float(parts[1].strip())
    except Exception:
        pass
    return None, None


def _parse_time_str(t: Optional[str]) -> Optional[object]:
    """Parse 'HH:MM' or 'HH:MM:SS' string → datetime.time, or None."""
    if not t or not isinstance(t, str):
        return None
    try:
        from datetime import time as dtime
        parts = t.strip().split(':')
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return dtime(h, m, s)
    except Exception:
        return None


def _parse_session_dt(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    """Combine a 'YYYY-MM-DD' date string and 'HH:MM' time string into a UTC datetime."""
    if not date_str:
        return None
    try:
        from dateutil.parser import parse as _parse
        base = _parse(str(date_str))
        t = _parse_time_str(time_str)
        if t:
            base = base.replace(hour=t.hour, minute=t.minute, second=t.second)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return base
    except Exception:
        return None


def _parse_hhmm_to_minutes(val) -> Optional[int]:
    """Parse '4:14' or 4.23 (decimal hours) → integer minutes, or None."""
    if val is None:
        return None
    s = str(val).strip()
    if ':' in s:
        try:
            h, m = s.split(':', 1)
            return int(h) * 60 + int(m)
        except Exception:
            return None
    try:
        return int(float(s) * 60)
    except Exception:
        return None


def _parse_ref_range(ref: str):
    """Parse '1.00 - 2.50' → (1.0, 2.5). Returns (None, None) on failure."""
    if not ref:
        return None, None
    try:
        parts = ref.replace('\u2013', '-').split('-')
        if len(parts) == 2:
            return float(parts[0].strip()), float(parts[1].strip())
    except Exception:
        pass
    return None, None
