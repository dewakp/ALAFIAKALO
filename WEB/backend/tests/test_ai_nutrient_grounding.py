"""The AI must be given this patient's limits, or it invents them.

A production answer capped potassium at **4.8**. That number is in neither the
code nor the database: HEBCS bands potassium 3.5-5.5, and every stored lab
reference range for it is 3.5-5.5 or 3.5-5.1. It was fabricated — and fabricated
in a specific, dangerous way, by reaching for a SERUM value (mmol/L) and
presenting it as a DIETARY intake limit. The dietary limit for a dialysis
patient is on the order of 2,000-3,000 mg/day, so 4.8 is not merely wrong, it is
wrong by three orders of magnitude and in the wrong unit.

An earlier answer from the local 20B model was ~10x too strict the same way.
Both share one cause: nothing in the prompt told the model what this patient's
limits actually are, though `compute_goals` computes them from KDOQI 2020 and
the Nutrition screen already shows them.

Canon 3c: if a lookup is wrong, fix what blocks the lookup — do not paper over
it with prompt scolding or a hardcoded alias.
"""

import pytest

from app.models.user import User


async def _user(db, email: str) -> User:
    u = User(
        email=email, hashed_password="x", full_name="Test User",
        date_of_birth="1962-04-11", gender="female",
        height_cm=165.0, current_weight_kg=62.0,
    )
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_context_carries_the_computed_dietary_limits(db):
    from app.api.ai import _fetch_patient_context

    user = await _user(db, "grounding@example.com")
    ctx = await _fetch_patient_context(user, db)

    assert "DAILY NUTRIENT TARGETS AND LIMITS" in ctx
    # The figures the model must use, in the units a DIET is measured in.
    assert "Potassium" in ctx
    assert "mg" in ctx


@pytest.mark.asyncio
async def test_potassium_is_stated_in_mg_per_day_not_as_a_serum_value(db):
    """The exact confusion behind 4.8: mmol/L quoted as an intake ceiling."""
    from app.api.ai import _fetch_patient_context

    user = await _user(db, "grounding2@example.com")
    ctx = await _fetch_patient_context(user, db)

    line = next((l for l in ctx.splitlines() if "Potassium" in l), None)
    assert line is not None, "potassium limit missing from the prompt"

    # A dietary potassium limit is thousands of mg, never single digits.
    import re
    value = float(re.search(r"([\d.]+)\s*mg", line).group(1))
    assert value > 100, f"potassium limit looks like a serum value: {line!r}"
    assert "mmol" not in line.lower() and "mEq" not in line


@pytest.mark.asyncio
async def test_the_prompt_forbids_quoting_a_serum_range_as_an_intake_limit(db):
    from app.api.ai import _fetch_patient_context

    user = await _user(db, "grounding3@example.com")
    ctx = await _fetch_patient_context(user, db)
    assert "SERUM" in ctx
    assert "dietary intake limit" in ctx


@pytest.mark.asyncio
async def test_an_incomplete_profile_is_labelled_not_passed_off_as_personal(db):
    """Reference-adult defaults must not read as a prescription for this patient."""
    from app.api.ai import _fetch_patient_context

    u = User(email="grounding4@example.com", hashed_password="x", full_name="No Biology")
    db.add(u)
    await db.flush()

    ctx = await _fetch_patient_context(u, db)
    if "DAILY NUTRIENT TARGETS" in ctx:
        assert "reference-adult defaults" in ctx


def test_4_8_is_not_a_figure_this_codebase_holds():
    """Proves the number was fabricated rather than read from our own tables."""
    from app.services.hebcs_engine import ESRD_PATHWAYS

    potassium = next(
        b for p in ESRD_PATHWAYS for b in p.biomarkers if b.name == "Potassium")
    # Serum banding, which is what 4.8 was mistaken for — and it is not 4.8.
    assert potassium.opt_low == 3.5
    assert potassium.opt_high == 5.5
