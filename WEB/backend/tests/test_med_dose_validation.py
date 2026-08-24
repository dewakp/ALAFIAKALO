"""A dose the record should never accept without a challenge.

From production: a dose log reading "calcium calcitriol 1000 mg". Calcium
carbonate 1000 mg was meant. Read literally it names calcitriol — dosed in
MICROGRAMS — so it is ~1000× a real dose, and it is the exact row any
"infer the usual dose from history" feature would have replayed.
"""

import pytest
import pytest_asyncio

from app.models.med_nutrient import MedNutrientProfile
from app.services.med_dose_validation import validate_dose, blocking
from app.services.rxnorm import DrugFacts

# RxNorm facts as the live API actually returns them (captured, not invented):
#   calcitriol          -> rxcui 1894, largest marketed oral unit 0.0005 MG
#   calcium carbonate   -> rxcui 1897
#   calcium calcitriol  -> no rxcui; approximateTerm suggests "Calcitriol"
#   sevelamer carbonate -> rxcui 660890
RX = {
    "calcitriol": DrugFacts(query="calcitriol", rxcui="1894", max_strength_mg=0.0005),
    "calcium carbonate": DrugFacts(query="calcium carbonate", rxcui="1897", max_strength_mg=1250.0),
    "calcium calcitriol": DrugFacts(query="calcium calcitriol", suggestion="Calcitriol"),
    "sevelamer carbonate": DrugFacts(query="sevelamer carbonate", rxcui="660890", max_strength_mg=800.0),
}


@pytest_asyncio.fixture
async def profiles(db):
    """The two rows this test turns on, with their real sourced values."""
    db.add_all([
        MedNutrientProfile(
            med_name_normalized="calcitriol", med_name_original="Calcitriol",
            active_ingredient="calcitriol", dose_unit_canonical="mcg",
            rxnorm_code="3002", nutrients_per_dose_unit={}, source="seeded",
        ),
        MedNutrientProfile(
            med_name_normalized="calcium carbonate", med_name_original="Calcium Carbonate",
            active_ingredient="calcium carbonate", dose_unit_canonical="mg",
            rxnorm_code="41489", nutrients_per_dose_unit={}, source="seeded",
        ),
    ])
    await db.flush()
    return db


@pytest.mark.asyncio
async def test_calcitriol_in_mg_is_refused(profiles, db):
    """The headline: calcitriol is mcg. 1000 mg is not a rounding error."""
    findings = await validate_dose(db, "Calcitriol", 1000, "mg", rx=RX["calcitriol"])
    assert blocking(findings), "1000 mg of calcitriol must not pass silently"
    assert findings[0].code in ("dose_exceeds_ceiling", "dose_exceeds_marketed_strength")
    assert "mcg" in findings[0].message


@pytest.mark.asyncio
async def test_calcium_calcitriol_is_caught_as_a_typo(profiles, db):
    """The actual production string. Not a real drug — challenge it."""
    findings = await validate_dose(db, "calcium calcitriol", 1000, "mg", rx=RX["calcium calcitriol"])
    assert blocking(findings), "a name that is not a drug must be challenged"
    assert findings[0].code == "unknown_medication"
    assert findings[0].suggestion == "Calcitriol"


@pytest.mark.asyncio
async def test_calcium_carbonate_1000mg_is_fine(profiles, db):
    """What the user actually meant. An ordinary dose must not be obstructed."""
    assert await validate_dose(db, "Calcium Carbonate", 1000, "mg", rx=RX["calcium carbonate"]) == []


@pytest.mark.asyncio
async def test_a_normal_calcitriol_dose_is_fine(profiles, db):
    assert await validate_dose(db, "Calcitriol", 0.5, "mcg", rx=RX["calcitriol"]) == []


@pytest.mark.asyncio
async def test_an_unknown_drug_is_not_obstructed(profiles, db):
    """Sevelamer is a real drug our seed table never had. RxNorm knows it, so it
    must pass — the old table-only check waved it through by accident, not by
    knowing anything about it."""
    assert await validate_dose(db, "Sevelamer Carbonate", 800, "mg", rx=RX["sevelamer carbonate"]) == []


@pytest.mark.asyncio
async def test_an_uncovertible_unit_is_refused(profiles, db):
    findings = await validate_dose(db, "Calcitriol", 2, "mL", rx=RX["calcitriol"])
    assert blocking(findings)
    assert findings[0].code == "unit_mismatch"


@pytest.mark.asyncio
async def test_no_medication_name_says_nothing(profiles, db):
    assert await validate_dose(db, "", 1, "mg") == []
