"""Clinical thresholds must come from data, not from constants in the source.

Canon, stated plainly: **no hardcoded data, no exception.** At the scale this
runs at, a constant is not an approximation — it is wrong for most patients.
The evidence was in this record:

    HEBCS albumin band   4.0 - 5.0     the reporting lab said  3.2 - 4.8
    HEBCS potassium band 3.5 - 5.5     the reporting lab said  3.5 - 5.1
    HEBCS BUN band       once 21       21 is the adult FEMALE ceiling, on a
                                       male patient whose lab reported 9 - 23

Resolution order is now: the range this patient's lab REPORTED -> the range most
commonly reported for that analyte -> a row in `clinical_thresholds` (guideline
targets, for values a lab never prints a range for) -> the biomarker goes
UNSCORED. No step invents a number.

These tests fail the build if that ordering is broken or bypassed.
"""

import pytest

from app.services.hebcs_engine import (
    ESRD_PATHWAYS, apply_reference_range, compute_hebcs,
)


def test_a_reported_range_overrides_the_published_band():
    bun = next(b for p in ESRD_PATHWAYS for b in p.biomarkers if b.name == "BUN")
    anchored = apply_reference_range(bun, (9.0, 23.0))
    assert (anchored.opt_low, anchored.opt_high) == (9.0, 23.0)
    assert (bun.opt_low, bun.opt_high) != (9.0, 23.0), "the constant must not already be it"


def test_every_scored_biomarker_reports_where_its_band_came_from():
    """A constant must never pass for a range someone measured."""
    result = compute_hebcs(
        {"Albumin": 4.1, "BUN": 17.0, "Potassium": 4.2},
        reference_ranges={"Albumin": (3.2, 4.8), "BUN": (9.0, 23.0)},
    )
    scored = [b for p in result["pathways"].values()
              for b in p["biomarkers"] if b["value"] is not None]
    assert scored
    for b in scored:
        assert b["band_source"] in {"reported", "published_band"}, b

    by_name = {b["name"]: b for b in scored}
    assert by_name["Albumin"]["band_source"] == "reported"
    assert by_name["BUN"]["band_source"] == "reported"
    # Nothing was supplied for potassium, so it must SAY it used the constant.
    assert by_name["Potassium"]["band_source"] == "published_band"


def test_the_migration_seeds_the_guideline_targets_with_their_source():
    """The three values a lab never prints a reference range for.

    Checked against the migration rather than a live table because the test
    database is built from models, not migrations — asserting on the table here
    would pass vacuously wherever it happened to be empty.
    """
    from pathlib import Path

    seed = Path(
        "alembic/versions/tt001_clinical_thresholds.py").read_text()
    for analyte in ("KtV (Dialysis Adequacy)",
                    "URR (Urea Reduction Ratio)",
                    "CaxP Product"):
        assert analyte in seed, analyte
    # A threshold with no provenance cannot be reviewed or revised, which is how
    # a wrong band survives.
    assert "KDOQI" in seed
    assert '"source"' in seed


@pytest.mark.asyncio
async def test_the_thresholds_table_is_read_when_no_lab_reported_a_range(db):
    """Guideline targets are DATA: changing one must not need a deploy."""
    from app.models.clinical_threshold import ClinicalThreshold
    from app.models.user import User
    from app.services import reference_ranges as refs

    user = User(email="ranges-t@example.com", hashed_password="x", full_name="T")
    db.add(user)
    db.add(ClinicalThreshold(
        analyte="KtV (Dialysis Adequacy)", crit_low=0.8, opt_low=1.4,
        opt_high=1.8, source="NKF-KDOQI: single-pool Kt/V target >= 1.4"))
    await db.flush()

    resolved = await refs.resolve(db, user.id)
    assert resolved["KtV (Dialysis Adequacy)"] == (1.4, 1.8)


@pytest.mark.asyncio
async def test_resolution_prefers_the_patient_over_the_population(db):
    """The patient's own lab is more specific than anyone else's."""
    from datetime import date
    from app.models.labs import LabResult
    from app.models.user import User
    from app.services import reference_ranges as refs

    mine = User(email="ranges-a@example.com", hashed_password="x", full_name="A")
    theirs = User(email="ranges-b@example.com", hashed_password="x", full_name="B")
    db.add_all([mine, theirs])
    await db.flush()

    # Two other patients report one range; this patient's own lab reports another.
    for _ in range(2):
        db.add(LabResult(user_id=theirs.id, test_name="Albumin", value=4.0,
                         test_date=date(2026, 1, 1),
                         reference_range_low=3.4, reference_range_high=4.8))
    db.add(LabResult(user_id=mine.id, test_name="Albumin", value=4.1,
                     test_date=date(2026, 6, 1),
                     reference_range_low=3.2, reference_range_high=4.8))
    await db.flush()

    population = await refs.population_modes(db)
    assert population["Albumin"] == (3.4, 4.8)

    resolved = await refs.resolve(db, mine.id)
    assert resolved["Albumin"] == (3.2, 4.8), "the patient's own range must win"


@pytest.mark.asyncio
async def test_an_analyte_nobody_reported_is_simply_absent(db):
    """No invented fallback: absent means unscoreable, and the coverage
    reporting already says so."""
    from app.models.user import User
    from app.services import reference_ranges as refs

    user = User(email="ranges-c@example.com", hashed_password="x", full_name="C")
    db.add(user)
    await db.flush()

    resolved = await refs.resolve(db, user.id)
    assert "Some Analyte Nobody Measured" not in resolved


@pytest.mark.asyncio
async def test_a_range_is_never_learned_from_one_patient(db):
    """20 draws from one person describes that person's disease, not a norm.

    Without this guard the reference database would have adopted 21 ranges from
    a single dialysis patient's values as everyone's normal.
    """
    from datetime import date
    from app.models.labs import LabResult
    from app.models.user import User
    from app.services import reference_ranges as refs

    solo = User(email="solo@example.com", hashed_password="x", full_name="Solo")
    db.add(solo)
    await db.flush()
    for i in range(40):
        db.add(LabResult(user_id=solo.id, test_name="Novel Assay",
                         value=100.0 + i, test_date=date(2026, 1, 1)))
    await db.flush()

    # Plenty of observations, one patient — must learn nothing.
    assert "Novel Assay" not in await refs.learn_from_distribution(db)

    # The observation count alone WOULD have admitted it.
    relaxed = await refs.learn_from_distribution(db, min_observations=5, min_patients=1)
    assert "Novel Assay" in relaxed


@pytest.mark.asyncio
async def test_a_learned_range_records_how_many_patients_it_came_from(db):
    """A threshold with no provenance cannot be reviewed."""
    from datetime import date
    from sqlalchemy import select
    from app.models.clinical_threshold import ClinicalThreshold
    from app.models.labs import LabResult
    from app.models.user import User
    from app.services import reference_ranges as refs

    for n in range(12):
        u = User(email=f"cohort{n}@example.com", hashed_password="x", full_name="C")
        db.add(u)
        await db.flush()
        for i in range(3):
            db.add(LabResult(user_id=u.id, test_name="Cohort Assay",
                             value=50.0 + i + n, test_date=date(2026, 1, 1)))
    await db.flush()

    learned = await refs.learn_from_distribution(db)
    assert "Cohort Assay" in learned

    row = (await db.execute(select(ClinicalThreshold).where(
        ClinicalThreshold.analyte == "Cohort Assay"))).scalar_one()
    assert "patients" in row.source
    assert "not a clinical target" in row.source
