"""One drug, one row — no matter how many tables it is written in.

The medication picture is split across four sources (see
`clinical_sources.medications_unified`). Before this, the Medications screen
rendered three of them as three separate lists and grouped names with
`lower()`, so a patient on ONE iron product could read their own chart as
three different drugs — "Venofer" on the flowsheet, "venofer" in their dose
log, "Iron sucrose" from the portal — and a dose given at a treatment and then
logged by hand counted twice.

These tests pin both halves: names collapse, and a day recorded in two sources
is one day.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.models.chronic_conditions import TherapySession, TherapyStatus, TherapyType
from app.models.med_nutrient import MedicationDoseLog
from app.models.medications import Medication
from app.models.user import User
from app.services import clinical_sources


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Unified Tester")
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_one_drug_in_four_sources_is_one_row(db):
    """Five records, three spellings, four sources — one iron."""
    u = await _user(db, "unified-iron@example.com")

    # 1. a prescription the patient entered
    db.add(Medication(user_id=u.id, name="Venofer", dosage="100", dosage_unit="mg",
                      is_active=True))
    # 2. the SAME drug arriving from a portal import under its generic name
    db.add(Medication(user_id=u.id, name="Iron sucrose", source="Test Clinic",
                      is_active=True))
    # 3. the patient logging it by hand, lower-cased
    db.add(MedicationDoseLog(user_id=u.id, medication_name="venofer",
                             log_date=date(2026, 9, 1), dose_amount=100,
                             dose_unit="mg"))
    # 4. the flowsheet for the SAME DAY — this is the duplicate that used to
    #    read as a second dose
    db.add(TherapySession(user_id=u.id, therapy_type=TherapyType.HEMODIALYSIS,
                          status=TherapyStatus.COMPLETED,
                          scheduled_date=datetime(2026, 9, 1, 6, 0),
                          drugs_administered="Venofer (100 mg)"))
    # a second, genuinely different day
    db.add(TherapySession(user_id=u.id, therapy_type=TherapyType.HEMODIALYSIS,
                          status=TherapyStatus.COMPLETED,
                          scheduled_date=datetime(2026, 9, 3, 6, 0),
                          drugs_administered="Venofer (100 mg)"))
    await db.flush()

    rows = await clinical_sources.medications_unified(db, u.id)

    assert len(rows) == 1, f"expected one drug, got {[r.name for r in rows]}"
    iron = rows[0]
    assert iron.name == "Iron sucrose"          # canonical, not the brand
    assert iron.drug_class == "IV iron"
    assert sorted(iron.sources) == ["administered", "imported", "logged", "prescribed"]
    # Both spellings are kept: merging is shown to the patient, not hidden.
    assert set(iron.written_as) == {"Venofer", "Iron sucrose", "venofer"}
    # THE assertion. Sep 1 is in the dose log AND on the flowsheet; Sep 3 is
    # only on the flowsheet. Two days, not the three records that make them up.
    assert iron.days == 2
    assert iron.first == "2026-09-01"
    assert iron.last == "2026-09-03"
    # The raw per-source counts stay visible rather than being smoothed away.
    assert iron.by_source == {"prescribed": 1, "imported": 1, "logged": 1,
                              "administered": 2}


@pytest.mark.asyncio
async def test_distinct_drugs_are_not_merged(db):
    """Harmonising must not over-merge: two drugs stay two."""
    u = await _user(db, "unified-two@example.com")
    db.add(TherapySession(user_id=u.id, therapy_type=TherapyType.HEMODIALYSIS,
                          status=TherapyStatus.COMPLETED,
                          scheduled_date=datetime(2026, 9, 1, 6, 0),
                          drugs_administered="Venofer (100 mg); Epogene (3,000 SQ)"))
    await db.flush()

    rows = await clinical_sources.medications_unified(db, u.id)
    assert sorted(r.name for r in rows) == ["Epoetin alfa", "Iron sucrose"]


@pytest.mark.asyncio
async def test_flowsheet_only_drug_still_appears(db):
    """The decade of ESA nobody could see — it has to be in the list."""
    u = await _user(db, "unified-esa@example.com")
    db.add(TherapySession(user_id=u.id, therapy_type=TherapyType.HEMODIALYSIS,
                          status=TherapyStatus.COMPLETED,
                          scheduled_date=datetime(2026, 9, 1, 6, 0),
                          drugs_administered="Doxercalcif (4mcg)"))
    await db.flush()

    rows = await clinical_sources.medications_unified(db, u.id)
    assert [r.name for r in rows] == ["Doxercalciferol"]
    assert rows[0].sources == ["administered"]
    assert rows[0].active is True


@pytest.mark.asyncio
async def test_prescribed_but_never_taken_is_kept(db):
    """A drug ordered and never taken is a clinical fact, not an empty row."""
    u = await _user(db, "unified-untaken@example.com")
    db.add(Medication(user_id=u.id, name="Calcitriol", is_active=True))
    await db.flush()

    rows = await clinical_sources.medications_unified(db, u.id)
    assert [r.name for r in rows] == ["Calcitriol"]
    assert rows[0].days == 0
    assert rows[0].last is None
    assert rows[0].sources == ["prescribed"]


@pytest.mark.asyncio
async def test_a_flowsheet_only_day_is_not_an_empty_day(db):
    """The empty state that creates the duplicate.

    A treatment day whose drugs are only on the flowsheet used to render as
    "No intake logged for this date" — so the patient logged the dose again.
    """
    u = await _user(db, "unified-day-empty@example.com")
    db.add(TherapySession(user_id=u.id, therapy_type=TherapyType.HEMODIALYSIS,
                          status=TherapyStatus.COMPLETED,
                          scheduled_date=datetime(2026, 9, 11, 6, 0),
                          drugs_administered="Venofer (100 mg)"))
    await db.flush()

    rows = await clinical_sources.administrations_on_day(db, u.id, date(2026, 9, 11))
    assert [r.name for r in rows] == ["Iron sucrose"]
    assert rows[0].sources == ["administered"]
    # Nothing here for this screen to delete — a flowsheet is corrected on the
    # flowsheet.
    assert rows[0].dose_log_id is None


@pytest.mark.asyncio
async def test_one_dose_in_both_sources_is_one_row_for_the_day(db):
    """Logged by hand AND on the flowsheet: one administration, one row."""
    u = await _user(db, "unified-day-both@example.com")
    db.add(MedicationDoseLog(user_id=u.id, medication_name="venofer",
                             log_date=date(2026, 9, 11), dose_amount=100,
                             dose_unit="mg"))
    db.add(TherapySession(user_id=u.id, therapy_type=TherapyType.HEMODIALYSIS,
                          status=TherapyStatus.COMPLETED,
                          scheduled_date=datetime(2026, 9, 11, 6, 0),
                          drugs_administered="Venofer (100 mg)"))
    await db.flush()

    rows = await clinical_sources.administrations_on_day(db, u.id, date(2026, 9, 11))
    assert len(rows) == 1, f"one dose, two records → {[r.name for r in rows]}"
    assert sorted(rows[0].sources) == ["administered", "logged"]
    # The dose log still owns the row, so the patient can still delete what
    # they typed.
    assert rows[0].dose_log_id is not None


@pytest.mark.asyncio
async def test_calendar_marks_treatment_days_not_just_logged_ones(db):
    u = await _user(db, "unified-days@example.com")
    db.add(MedicationDoseLog(user_id=u.id, medication_name="Calcium Carbonate",
                             log_date=date(2026, 9, 10), dose_amount=1000,
                             dose_unit="mg"))
    db.add(TherapySession(user_id=u.id, therapy_type=TherapyType.HEMODIALYSIS,
                          status=TherapyStatus.COMPLETED,
                          scheduled_date=datetime(2026, 9, 11, 6, 0),
                          drugs_administered="Venofer (100 mg)"))
    await db.flush()

    assert await clinical_sources.administration_days(db, u.id) == [
        "2026-09-10", "2026-09-11",
    ]


class TestCasingIsNotADifferentDrug:
    """Found by running the unified view against a real record.

    It reported "Calcium Carbonate" (422 days) and "Calcium carbonate"
    (5 days) as two medications — the exact duplicate the function exists to
    remove, and the one the dose-log grouping was already careful about
    (canon 3aa: "Group dose logs case-insensitively ... two rows misstate the
    regimen").

    `canonical_drug_name` returns an UNRECOGNISED name exactly as written,
    which is right — guessing a drug name is worse than leaving it alone — but
    bucketing on that string splits one drug by capitalisation.
    """

    def test_an_unrecognised_drug_folds_across_casings(self):
        from app.services.flowsheet_drugs import canonical_drug_name

        a, _, known_a = canonical_drug_name("Calcium Carbonate")
        b, _, known_b = canonical_drug_name("Calcium carbonate")
        # Both unrecognised, and the raw spelling is deliberately preserved…
        assert (known_a, known_b) == (False, False)
        assert a != b
        # …so the BUCKET KEY, not the display name, is what must fold.
        assert a.casefold() == b.casefold()

    def test_a_recognised_drug_still_folds_by_alias(self):
        from app.services.flowsheet_drugs import canonical_drug_name

        # The case that already worked and must keep working: three spellings,
        # one drug.
        names = {canonical_drug_name(n)[0]
                 for n in ("Venofer", "venofer", "Iron sucrose")}
        assert names == {"Iron sucrose"}

    def test_genuinely_different_names_are_NOT_merged(self):
        from app.services.flowsheet_drugs import canonical_drug_name

        # "Docusolate" is almost certainly a misspelling of "Docusate", and
        # merging them would be guessing a drug name — the thing this module
        # refuses to do anywhere else.
        a, _, _ = canonical_drug_name("Docusate")
        b, _, _ = canonical_drug_name("Docusolate")
        assert a.casefold() != b.casefold()
