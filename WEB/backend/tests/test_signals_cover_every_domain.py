# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Every domain reaches the aggregates. This is canon, and it had failed thrice.

Operator, 2026-10-11: *"Contibutor to weight, vitals data are from flowsheets,
nutrition, medication, eliminations, vitals, labs, lifestyle, hospitalization
records and events, therapies. But right now they are not included in the
aggregates (overview, trends and insight). They MUST! This is canon and have
been repeated multiple times. This is not a set of isolated data points but a
collection of data for integrated viewing, advising and decisioning."*

`health_signals.collect_signals` is the single substrate under `/insights/signals`,
`/insights/relationships` and `/insights/forecast`. Measured on the reference
record BEFORE this change:

    weight     read 41 from vitals_logs, ignored 5,221 in therapy_sessions   0.8%
    systolic   read 43,                  ignored 18,526 in the flowsheets   0.23%

    never queried at all:  bowel_movements 2,436 · therapy_sessions 2,035
                           vomiting_logs 1,993 · medication_dose_logs 1,029
                           hospitalizations · surgical_procedures

So `vital.weight_kg` was forecast from 41 points while 5,221 existed, and no
relationship could involve dialysis, medication or eliminations because they
were not on the timeline. §3am found this in the AI tool (`get_vitals` read
`vitals_logs` alone — 41 rows on a patient with 16,236 intradialytic readings)
and §3ba found it in the wellness score ("read one row of `vitals_logs` and
never opened `therapy_sessions`"). This file is the guard for the third surface.
"""

from datetime import date, datetime, time, timedelta

import pytest

from app.models.chronic_conditions import (
    IntradialyticReading,
    TherapySession,
    TherapyStatus,
    TherapyType,
)
from app.models.elimination import BowelMovement
from app.models.user import User
from app.models.vitals import VitalsLog
from app.services.health_signals import (
    MAX,
    MEAN,
    MIN,
    SIGNAL_META,
    SUM,
    collect_signals,
    signal_domain,
)

#: The domains the operator named. A domain missing from SIGNAL_META cannot
#: reach any aggregate, whatever the database holds.
REQUIRED_DOMAINS = {
    "diet",          # nutrition
    "vital",         # self-recorded vitals
    "dialysis",      # flowsheets / therapies
    "medication",
    "elimination",
    "activity",      # lifestyle
    "sleep",
    "event",         # hospitalisations and procedures
    "symptom",
}


# ── Declarations ────────────────────────────────────────────────────────────

def test_every_named_domain_has_at_least_one_signal():
    declared = {meta["domain"] for meta in SIGNAL_META.values()}
    missing = REQUIRED_DOMAINS - declared
    assert not missing, (
        f"these domains cannot reach any aggregate: {sorted(missing)} — "
        "the operator's canon is that all of them must")


def test_every_declared_aggregation_is_one_the_reducer_KNOWS():
    """A typo'd `agg` silently becomes MEAN, which on a nadir destroys the
    finding. The reducer falls back by design, so the declarations are what
    must be checked."""
    known = {SUM, MEAN, MIN, MAX}
    bad = {k: m.get("agg") for k, m in SIGNAL_META.items() if m.get("agg") not in known}
    assert not bad, f"unknown aggregation, will silently become MEAN: {bad}"


def test_the_nadir_is_declared_MIN_and_the_worst_severity_MAX():
    """§3am: "for intradialytic the NADIR is the finding, not the mean — a
    session ending below 90 systolic is intradialytic hypotension that a mean
    hides." `symptom.severity_max` is here too because it used to be declared
    MEAN and corrected by a hardcoded branch in the reducer; removing that
    branch without fixing the declaration would have averaged it."""
    assert SIGNAL_META["dialysis.nadir_systolic"]["agg"] == MIN
    assert SIGNAL_META["symptom.severity_max"]["agg"] == MAX


def test_the_bp_sources_are_SEPARATE_signals_and_not_merged():
    """§3am: post runs well below pre BY DESIGN, so averaging the sources
    together manufactures a number no instrument read. Rendering pre-systolic
    over post-systolic as `sys/dia` once produced "91/83" — a pulse pressure of
    8, read as catastrophic, from two ordinary means."""
    for key in ("vital.bp_systolic", "dialysis.pre_systolic",
                "dialysis.post_systolic", "dialysis.nadir_systolic"):
        assert key in SIGNAL_META, f"{key} must exist as its own signal"
    assert signal_domain("vital.bp_systolic") != signal_domain("dialysis.pre_systolic")


def test_weight_has_a_flowsheet_source_as_well_as_a_self_recorded_one():
    """The operator's opening sentence: weight data comes from flowsheets.
    Measured 41 self-recorded against 5,221 in therapy_sessions."""
    for key in ("vital.weight_kg", "dialysis.pre_weight_kg",
                "dialysis.post_weight_kg", "dialysis.dry_weight_kg"):
        assert key in SIGNAL_META


def test_there_is_NO_duration_signal_from_the_conflated_column():
    """§3av: `duration_minutes` holds the WALL CLOCK when written by the app and
    the MACHINE's time on dialysis when written by the 2026-06-04 import, with
    no way to tell which from the row — "anything that averages, charts or
    models duration across this record is mixing two different measurements".

    So the signal is `machine_minutes`, from the column that means one thing.
    A `dialysis.duration_min` appearing here later would be that conflation
    wearing a chart."""
    assert "dialysis.machine_minutes" in SIGNAL_META
    assert "dialysis.duration_min" not in SIGNAL_META
    assert "dialysis.duration_minutes" not in SIGNAL_META


def test_medication_is_read_through_clinical_sources_not_the_tables():
    """§3aa: `medication_dose_logs` is guarded and medications live in THREE
    places — the third being drugs the unit administers during dialysis, which
    on this record is Epogene x1,962 / Venofer x1,248 and appears in ZERO dose
    logs because the patient never types them in."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "app" / "services" / "health_signals.py").read_text()
    assert "clinical_sources.dose_counts_by_day" in source
    assert "clinical_sources.administration_days" in source
    assert "MedicationDoseLog" not in source, (
        "read dose logs through clinical_sources — the guard in "
        "test_clinical_sources.py exists because reading one of the split "
        "tables and calling it the answer hides clinical facts")


# ── Behaviour, against a seeded record ──────────────────────────────────────

async def _user(db) -> User:
    """Seed a fresh user on the TEST session.

    The `db` fixture is the only session that can reach the test database:
    `backend-test`'s own DATABASE_URL points at `localhost:5435`, which inside
    that container is the container itself with nothing listening, so anything
    opening `async_session()` fails with "Connect call failed". Four tests here
    did exactly that on the first run.
    """
    user = User(email=f"signals-{datetime.now().timestamp()}@example.com",
                hashed_password="x", full_name="Signal Test",
                first_name="Signal", last_name="Tester", is_active=True)
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_the_nadir_is_the_LOWEST_reading_not_the_average(db):
    """The whole §3am rule, end to end.

    A treatment whose readings run 150 then 59 has a mean of 104 — an entirely
    ordinary number — and a nadir of 59, which is intradialytic hypotension.
    The mean is what the surface reported before MIN existed as an aggregation.
    """
    day = date(2026, 5, 4)
    user = await _user(db)
    session = TherapySession(
        user_id=user.id, therapy_type=TherapyType.HEMODIALYSIS,
        scheduled_date=datetime.combine(day, time.min),
        status=TherapyStatus.COMPLETED,
        pre_systolic_bp=150, pre_diastolic_bp=90,
        post_systolic_bp=95, post_diastolic_bp=60,
        pre_dialysis_weight_kg=58.0, post_dialysis_weight_kg=55.0,
        dry_weight_kg=55.0,
    )
    db.add(session)
    await db.flush()
    for systolic in (150, 59):
        db.add(IntradialyticReading(session_id=session.id, user_id=user.id,
                                    systolic_bp=systolic, diastolic_bp=40))
    # A self-recorded weight on the same day, which must stay its own signal.
    db.add(VitalsLog(user_id=user.id, log_date=day, weight_kg=57.0))
    await db.commit()

    signals = await collect_signals(db, user.id, day - timedelta(days=1),
                                    day + timedelta(days=1))

    assert signals["dialysis.nadir_systolic"][day] == 59, "a mean would read 104"
    assert signals["dialysis.readings_under_90"][day] == 1
    # The four sources stay apart, each reporting what its own instrument read.
    assert signals["dialysis.pre_systolic"][day] == 150
    assert signals["dialysis.post_systolic"][day] == 95
    assert signals["dialysis.pre_weight_kg"][day] == 58.0
    assert signals["dialysis.post_weight_kg"][day] == 55.0
    assert signals["vital.weight_kg"][day] == 57.0
    assert signals["dialysis.treatments"][day] == 1


@pytest.mark.asyncio
async def test_blood_recorded_only_in_PROSE_still_counts(db):
    """§3ba: `blood_present` is TRUE on ZERO of 648 migrated rows while 134 say
    so in the notes — two importers write only `notes` and name no structured
    column. Counting the boolean reports one bowel movement in five as
    unremarkable. `elimination_text.blood_in_row` is the one reader."""
    day = date(2026, 5, 6)
    user = await _user(db)
    db.add(BowelMovement(user_id=user.id, log_date=day,
                         blood_present=None, notes="Bloody"))
    db.add(BowelMovement(user_id=user.id, log_date=day,
                         blood_present=None, notes="normal, no blood"))
    await db.commit()

    signals = await collect_signals(db, user.id, day - timedelta(days=1),
                                    day + timedelta(days=1))

    assert signals["elimination.bowel_movements"][day] == 2
    assert signals["elimination.blood_episodes"][day] == 1, (
        "the prose-only episode must count, and 'no blood' must not")


@pytest.mark.asyncio
async def test_a_lab_split_across_two_spellings_is_ONE_signal(db):
    """§3ax: one record stores `ALP` until July 2025 and `Alk Phos` after,
    because the report format changed. Keyed on the printed wording, each
    spelling became its own signal and a forecast ran on half a series."""
    from app.models.labs import LabResult

    user = await _user(db)
    db.add(LabResult(user_id=user.id, test_date=date(2026, 5, 1),
                     test_name="ALP", value=90.0))
    db.add(LabResult(user_id=user.id, test_date=date(2026, 5, 8),
                     test_name="Alk Phos", value=96.0))
    await db.commit()

    signals = await collect_signals(db, user.id, date(2026, 4, 1),
                                    date(2026, 6, 1))

    alp = [k for k in signals if "alkaline" in k or k == "lab.alp"]
    assert len(alp) == 1, f"one analyte must be one signal, got {alp}"
    assert len(signals[alp[0]]) == 2, "both results must land on one series"


@pytest.mark.asyncio
async def test_a_user_with_only_flowsheet_data_still_gets_signals(db):
    """The failure mode that made this canon: a dialysis patient who never
    self-records a vital had almost nothing on the insight timeline, while
    thousands of their measurements sat in `therapy_sessions`."""
    day = date(2026, 5, 20)
    user = await _user(db)
    db.add(TherapySession(
        user_id=user.id, therapy_type=TherapyType.HEMODIALYSIS,
        scheduled_date=datetime.combine(day, time.min),
        status=TherapyStatus.COMPLETED,
        pre_dialysis_weight_kg=54.3, pre_systolic_bp=99,
    ))
    await db.commit()

    signals = await collect_signals(db, user.id, day - timedelta(days=1),
                                    day + timedelta(days=1))

    assert signals, "a flowsheet-only patient must not have an empty timeline"
    assert {signal_domain(k) for k in signals} == {"dialysis"}
