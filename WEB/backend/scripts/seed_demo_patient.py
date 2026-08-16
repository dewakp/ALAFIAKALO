#!/usr/bin/env python3
"""Seed a FICTIONAL patient for App Store screenshots and demos.

App Store screenshots are public and indexed. The reference record on this
system belongs to a real person — 2005 dialysis sessions, 422 lab results, a
potassium of 6.0 — and none of that should appear in a listing. This builds a
patient who does not exist, with clinically plausible numbers, so the marketing
surface never shows anyone's health data.

Everything is deterministic (seeded RNG), so re-running produces the same
record rather than a slightly different one each time.

DEV ONLY. It refuses to run against anything but the local dev database,
because seeded fiction in a production table is indistinguishable from a real
patient once it is there.

    docker compose --profile test run --rm \
      -e DATABASE_URL_SYNC=postgresql://alafia:alafia@db:5432/alafia \
      backend-test python scripts/seed_demo_patient.py --grant-to deji.adesida@alafia.app
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date, datetime, time, timedelta

import psycopg2

# A name that cannot be mistaken for a real record. The address is on
# alafia.app — the only domain this project owns — because `.invalid` and
# `.example` are rejected by the email validator, and inventing a domain we do
# not control risks colliding with a real mailbox.
DEMO_EMAIL = "demo.patient@alafia.app"
DEMO_NAME = "Ada Demo"

RNG = random.Random(20260816)


def _connect(dsn: str):
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    return conn


def _guard_is_dev(cur) -> None:
    """Refuse anything that is not the local dev database."""
    cur.execute("SELECT current_database(), inet_server_addr()::text")
    dbname, host = cur.fetchone()
    host = host or "local"
    if dbname != "alafia" or any(h in host for h in ("10.", "35.", "34.")):
        raise SystemExit(
            f"REFUSING to seed: database={dbname} host={host}. "
            "This script writes fictional patients and must never run against "
            "production."
        )


def _resolve(cur, email: str) -> int | None:
    cur.execute("SELECT id FROM users WHERE lower(email) = lower(%s)", (email,))
    row = cur.fetchone()
    return row[0] if row else None


def _demo_user(cur) -> int:
    """The demo patient, cloned from the column shape of an existing row.

    Two earlier approaches failed for instructive reasons:

      - Hand-writing the INSERT meant reproducing every NOT NULL column the
        registration path fills in. It failed on `ai_coaching_enabled`, and that
        duplicate would drift the moment a column was added.
      - Registering through the API returns 410 in dev: two-step signup is
        required there (it is deliberately OFF in production, canon §5a), and
        that flow needs a verified email round trip.

    So the row is built by copying an existing user's non-identity values and
    overriding what makes this account itself. New NOT NULL columns are picked
    up automatically, because the column list is read from the table.
    """
    uid = _resolve(cur, DEMO_EMAIL)
    if uid:
        return uid

    cur.execute("""
        -- table_schema matters: this database has public.users AND
        -- identity.users, so an unscoped lookup returns every column twice and
        -- the INSERT fails with "column email specified more than once".
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users'
          AND column_name <> 'id'
        ORDER BY ordinal_position
    """)
    cols = [r[0] for r in cur.fetchall()]

    # A template row only for its column DEFAULTS — every identifying field is
    # overridden below, so nothing personal is copied.
    overrides = {
        "email": DEMO_EMAIL,
        "full_name": DEMO_NAME,
        "hashed_password": os.environ["DEMO_PW_HASH"],
        "is_active": True,
        "is_superuser": False,
        # EVERY unique column must be cleared, or the clone collides with the
        # template row. On public.users those are: email, firebase_uid,
        # identity_uid, phone_number, system_id (id is the PK). Copying
        # system_id is what failed first, and finding them one exception at a
        # time is how the next added constraint gets missed.
        "identity_uid": None,
        "phone_number": None,
        "firebase_uid": None,
        "system_id": None,
        "date_of_birth": date(1968, 4, 12),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_login": None,
    }
    selects, params = [], []
    for c in cols:
        if c in overrides:
            selects.append("%s")
            params.append(overrides[c])
        else:
            selects.append(f"t.{c}")

    cur.execute(
        f"""INSERT INTO users ({', '.join(cols)})
            SELECT {', '.join(selects)}
            FROM users t
            WHERE t.id = (SELECT min(id) FROM users WHERE is_active)
            RETURNING id""",
        params,
    )
    return cur.fetchone()[0]


def _wipe(cur, uid: int) -> None:
    """Idempotent: clear this demo patient's rows before reseeding."""
    for table in ("intradialytic_readings", "therapy_sessions", "lab_results",
                  "nutrition_logs", "medication_dose_logs", "medications",
                  "chronic_conditions", "vitals_logs", "mood_entries"):
        cur.execute(f"DELETE FROM {table} WHERE user_id = %s", (uid,))


def seed_conditions(cur, uid: int) -> int:
    cur.execute(
        """INSERT INTO chronic_conditions
             (user_id, condition_name, category, severity, is_active,
              diagnosis_date, created_at, updated_at)
           VALUES (%s,%s,%s,%s,TRUE,%s,NOW(),NOW()) RETURNING id""",
        (uid, "End-Stage Renal Disease (ESRD)", "RENAL", "SEVERE",
         date.today() - timedelta(days=1500)))
    esrd = cur.fetchone()[0]
    # Labels are UPPERCASE in the enum types, and HEMATOLOGY is not one of them
    # — BLOOD_DISORDER is. Checked with pg_enum rather than assumed.
    for name, cat, sev, days in (("Renal anaemia", "BLOOD_DISORDER", "MODERATE", 900),
                                 ("Secondary hyperparathyroidism", "ENDOCRINE", "MODERATE", 700),
                                 ("Hypertension", "CARDIOVASCULAR", "MODERATE", 1800)):
        cur.execute(
            """INSERT INTO chronic_conditions
                 (user_id, condition_name, category, severity, is_active,
                  diagnosis_date, created_at, updated_at)
               VALUES (%s,%s,%s,%s,TRUE,%s,NOW(),NOW())""",
            (uid, name, cat, sev, date.today() - timedelta(days=days)))
    return esrd


def seed_dialysis(cur, uid: int, condition_id: int, weeks: int = 26) -> int:
    """Three treatments a week, each with an intradialytic curve."""
    sessions = 0
    dry = 72.0
    for w in range(weeks):
        for dow in (0, 2, 4):                       # Mon / Wed / Fri
            day = date.today() - timedelta(days=(weeks - w) * 7 - dow)
            if day > date.today():
                continue
            gain = round(RNG.uniform(1.8, 3.2), 1)  # interdialytic weight gain
            pre = round(dry + gain, 1)
            post = round(pre - gain + RNG.uniform(-0.2, 0.2), 1)
            uf = int((pre - post) * 1000)
            start_h = RNG.choice([7, 8, 12, 13])
            start = datetime.combine(day, time(start_h, RNG.choice([0, 15, 30])))
            duration = RNG.choice([210, 225, 240])
            end = start + timedelta(minutes=duration)
            pre_sys, pre_dia = RNG.randint(128, 158), RNG.randint(72, 88)
            post_sys, post_dia = pre_sys - RNG.randint(8, 26), pre_dia - RNG.randint(2, 12)
            cur.execute(
                """INSERT INTO therapy_sessions
                     (user_id, condition_id, therapy_type, therapy_name, status,
                      scheduled_date, actual_start_time, actual_end_time,
                      duration_minutes, facility_name, dialysis_access_type,
                      pre_dialysis_weight_kg, post_dialysis_weight_kg, dry_weight_kg,
                      fluid_removed_ml, blood_flow_rate, dialysate_flow_rate,
                      pre_systolic_bp, pre_diastolic_bp, pre_heart_rate,
                      post_systolic_bp, post_diastolic_bp, post_heart_rate,
                      patient_tolerance, created_at, updated_at)
                   VALUES (%s,%s,'HEMODIALYSIS','Home Hemodialysis (HHD)','COMPLETED',
                           %s,%s,%s,%s,'Riverside Home Program','AV Fistula',
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
                   RETURNING id""",
                (uid, condition_id, start, start, end, duration,
                 pre, post, dry, uf, RNG.choice([350, 400, 420]), 500,
                 pre_sys, pre_dia, RNG.randint(68, 84),
                 post_sys, post_dia, RNG.randint(70, 92),
                 RNG.choice(["Well tolerated", "Well tolerated", "Mild cramping"])))
            sid = cur.fetchone()[0]
            sessions += 1

            removed = 0
            for i in range(RNG.randint(4, 6)):
                t = (start + timedelta(minutes=45 * (i + 1))).time()
                removed += uf // 5
                cur.execute(
                    """INSERT INTO intradialytic_readings
                         (session_id, user_id, reading_time, reading_number,
                          systolic_bp, diastolic_bp, pulse, mean_arterial_pressure,
                          uf_rate, uf_volume_removed, blood_flow_rate,
                          arterial_pressure, venous_pressure, access_state, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Patent',NOW())""",
                    (sid, uid, t, i + 1,
                     pre_sys - RNG.randint(4, 20), pre_dia - RNG.randint(0, 10),
                     RNG.randint(68, 90), round(RNG.uniform(78, 96), 1),
                     round(uf / (duration / 60), 0), min(removed, uf),
                     RNG.choice([350, 400, 420]),
                     -RNG.randint(110, 160), RNG.randint(120, 170)))
    return sessions


def seed_labs(cur, uid: int) -> int:
    """A renal panel drawn monthly, with a few values out of range on purpose —
    the physician board's job is to surface exactly those."""
    panel = [
        ("Potassium", "mEq/L", 3.5, 5.5, (4.2, 5.9)),
        ("BUN", "mg/dL", 9, 23, (48, 72)),
        ("Creatinine", "mg/dL", 0.6, 1.3, (7.4, 10.2)),
        ("Phosphorus", "mg/dL", 2.5, 4.5, (4.1, 6.3)),
        ("Calcium", "mg/dL", 8.5, 10.2, (8.4, 9.6)),
        ("Hemoglobin", "g/dL", 13.5, 17.5, (9.8, 11.6)),
        ("Hematocrit", "%", 41, 53, (30, 36)),
        ("Albumin", "g/dL", 3.4, 4.8, (3.6, 4.3)),
        ("Ferritin", "ng/mL", 24, 336, (180, 420)),
        ("PTH, Intact", "pg/mL", 15, 65, (180, 460)),
        ("Sodium", "mEq/L", 135, 145, (136, 142)),
        ("Bicarbonate", "mEq/L", 22, 29, (19, 24)),
    ]
    n = 0
    for m in range(6):
        drawn = date.today() - timedelta(days=30 * m + 3)
        for name, unit, lo, hi, (vlo, vhi) in panel:
            value = round(RNG.uniform(vlo, vhi), 1)
            cur.execute(
                """INSERT INTO lab_results
                     (user_id, test_name, value, unit, reference_range_low,
                      reference_range_high, test_date, status, performing_lab,
                      created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'final','Riverside Renal Lab',NOW())""",
                (uid, name, value, unit, lo, hi, drawn))
            n += 1
    return n


def seed_nutrition(cur, uid: int, days: int = 90) -> int:
    meals = [("Breakfast", "Egg white omelette with peppers"),
             ("Lunch", "Grilled chicken, white rice, green beans"),
             ("Dinner", "Baked cod, couscous, roasted courgette"),
             ("Snack", "Apple slices")]
    n = 0
    for d in range(days):
        day = date.today() - timedelta(days=d)
        if RNG.random() < 0.08:                       # a few unlogged days
            continue
        for meal, food in meals:
            if meal == "Snack" and RNG.random() < 0.5:
                continue
            cur.execute(
                """INSERT INTO nutrition_logs
                     (user_id, log_date, meal_type, food_name, serving_size,
                      calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g,
                      sodium_mg, potassium_mg, phosphorus_mg, calcium_mg, iron_mg,
                      magnesium_mg, zinc_mg, vitamin_c_mg, vitamin_d_iu,
                      vitamin_b12_mcg, vitamin_b9_folate_mcg, water_ml,
                      nutrient_status, created_at)
                   VALUES (%s,%s,%s,%s,'1 serving',
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           'done',NOW())""",
                (uid, day, meal.lower(), food,
                 RNG.randint(280, 520), round(RNG.uniform(14, 34), 1),
                 round(RNG.uniform(22, 58), 1), round(RNG.uniform(6, 22), 1),
                 round(RNG.uniform(2, 7), 1), round(RNG.uniform(2, 12), 1),
                 RNG.randint(180, 420), RNG.randint(160, 420),
                 RNG.randint(90, 230), RNG.randint(60, 180),
                 round(RNG.uniform(1.2, 4.5), 1), RNG.randint(30, 90),
                 round(RNG.uniform(1.5, 4.0), 1), round(RNG.uniform(6, 40), 1),
                 RNG.randint(20, 140), round(RNG.uniform(0.6, 2.4), 1),
                 RNG.randint(40, 160), RNG.randint(150, 300)))
            n += 1
    return n


def seed_medications(cur, uid: int) -> tuple[int, int]:
    meds = [("Calcitriol", "0.25 mcg", 0.25, "mcg", "Once daily"),
            ("Calcium Carbonate", "500 mg", 500, "mg", "Three times daily with meals"),
            ("Epoetin alfa", "4000 units", 4000, "units", "Twice weekly"),
            ("Sevelamer", "800 mg", 800, "mg", "Three times daily with meals")]
    doses = 0
    for name, dose, amount, unit, freq in meds:
        cur.execute(
            """INSERT INTO medications
                 (user_id, name, dosage, frequency, is_active, start_date,
                  route, source, created_at)
               VALUES (%s,%s,%s,%s,TRUE,%s,'oral','demo',NOW())""",
            (uid, name, dose, freq, date.today() - timedelta(days=400)))
        per_day = 3 if "Three" in freq else 1
        for d in range(60):
            day = date.today() - timedelta(days=d)
            for k in range(per_day):
                if RNG.random() < 0.06:               # realistic adherence gaps
                    continue
                cur.execute(
                    """INSERT INTO medication_dose_logs
                         (user_id, medication_name, dose_amount, dose_unit,
                          log_date, log_time, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,NOW())""",
                    (uid, name, amount, unit, day, time(8 + k * 5, 0)))
                doses += 1
    return len(meds), doses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grant-to", required=True,
                    help="clinician email that should see this demo patient")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL", "")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        raise SystemExit("DATABASE_URL_SYNC is not set")

    conn = _connect(dsn)
    cur = conn.cursor()
    _guard_is_dev(cur)

    uid = _demo_user(cur)
    _wipe(cur, uid)
    esrd = seed_conditions(cur, uid)
    sessions = seed_dialysis(cur, uid, esrd)
    labs = seed_labs(cur, uid)
    nutrition = seed_nutrition(cur, uid)
    meds, doses = seed_medications(cur, uid)

    clinician = _resolve(cur, args.grant_to)
    if not clinician:
        raise SystemExit(f"no clinician with email {args.grant_to!r}")
    cur.execute("DELETE FROM data_grants WHERE owner_id = %s AND grantee_user_id = %s",
                (uid, clinician))
    # read_access is NOT NULL: a grant that does not say what it permits is not
    # a grant. Read-only — a demo record is for viewing, and nothing about
    # screenshots needs write access to a patient's chart.
    cur.execute(
        """INSERT INTO data_grants (owner_id, grantee_user_id, data_type,
                                    read_access, write_access, is_active,
                                    created_at, updated_at)
           VALUES (%s,%s,'all',TRUE,FALSE,TRUE,NOW(),NOW())""",
        (uid, clinician))

    conn.commit()
    print(f"  demo patient   : {DEMO_NAME} <{DEMO_EMAIL}> (id {uid})")
    print(f"  conditions     : 4 (ESRD severe + 3)")
    print(f"  HD sessions    : {sessions} with intradialytic readings")
    print(f"  lab results    : {labs} across 6 monthly panels")
    print(f"  nutrition logs : {nutrition}")
    print(f"  medications    : {meds} with {doses} dose logs")
    print(f"  shared with    : {args.grant_to} (all)")


if __name__ == "__main__":
    main()
