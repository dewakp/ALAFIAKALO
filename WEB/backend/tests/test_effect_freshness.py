# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A notice may not assert something about the record nobody asked the record.

`apply_effects_to_totals` took a single `measurement_fresh` flag and the one
production caller passed the literal `False`. So a gated effect printed:

    "… needs a recent blood test to confirm it. There isn't one, so it is
     shown and not counted."

on every day, for every patient, forever — while the reference record held a
panel drawn five days earlier carrying Calcium 8.9 and Iron 42. Reported from
the live screen: the same notice on 10/1, 10/2, 10/3 and 10/4.

Freshness is per ANALYTE. One boolean cannot say "calcium is measured, zinc is
not", so whoever owned it had to pick the pessimistic answer for everything and
then state it as fact.

**Guards vs coverage.** The static scan is the regression guard — it fails
against the pre-change tree, where `nutrition.py` passes a bare literal, and no
behavioural test would catch that call site being reverted. The rest is
coverage for a function that did not exist.
"""

import ast
import inspect
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services import nutrient_effects_service as svc
from app.services.nutrient_effects_day import apply_effects_to_totals
from app.services.nutrient_effects_service import Effect, analyte_stem
from app.services.nutrient_exposures import AgentExposure


# ─────────────────────────────────────────────────────────────────────
# The nutrient → analyte stem, which replaces a hand-typed alias table
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key,expected", [
    ("calcium_mg", "calcium"),
    ("iron_mg", "iron"),
    ("potassium_mg", "potassium"),
    ("vitamin_b9_folate_mcg", "vitamin_b9_folate"),
    ("calories", "calories"),
    ("protein_g", "protein"),
])
def test_the_stem_drops_the_unit_and_nothing_else(key, expected):
    assert analyte_stem(key) == expected


def test_mcg_is_stripped_before_mg():
    """Ordering trap: "_mg" is a suffix of nothing here, but "_mcg" ends in
    "cg" and a naive "_g"-first pass would leave "vitamin_b9_folate_mc"."""
    assert analyte_stem("folate_mcg") == "folate"
    assert analyte_stem("sodium_mg") == "sodium"
    assert analyte_stem("fat_g") == "fat"


# ─────────────────────────────────────────────────────────────────────
# measured_dates_for — asks the record, per analyte
# ─────────────────────────────────────────────────────────────────────

async def _user(db, email="fresh@example.com"):
    from app.core.security import hash_password
    from app.models.user import User

    u = User(email=email, hashed_password=hash_password("x"),
             full_name="Fresh User", is_active=True)
    db.add(u)
    await db.flush()
    return u


async def _lab(db, user_id, name, when, value=1.0):
    from app.models.labs import LabResult

    db.add(LabResult(user_id=user_id, test_name=name, test_date=when,
                     value=value, status="final"))
    await db.flush()


@pytest.mark.asyncio
async def test_a_recent_result_is_found_for_the_nutrient_it_backs(db):
    u = await _user(db)
    today = date(2026, 10, 6)
    await _lab(db, u.id, "Calcium", date(2026, 10, 1), 8.9)
    await _lab(db, u.id, "Iron", date(2026, 10, 1), 42.0)

    found = await svc.measured_dates_for(
        db, u.id, ["calcium_mg", "iron_mg", "fiber_g"], today)

    assert found["calcium_mg"] == date(2026, 10, 1)
    # Iron is the case the old five-field struct could not represent at all.
    assert found["iron_mg"] == date(2026, 10, 1)
    assert "fiber_g" not in found, "there is no blood test for fibre"


@pytest.mark.asyncio
async def test_a_stale_result_does_not_count_as_recent(db):
    u = await _user(db, "stale@example.com")
    today = date(2026, 10, 6)
    await _lab(db, u.id, "Calcium", today - timedelta(days=45), 8.9)

    found = await svc.measured_dates_for(db, u.id, ["calcium_mg"], today)
    assert found == {}, "beyond the stale window it is history, not confirmation"


@pytest.mark.asyncio
async def test_the_newest_result_wins(db):
    u = await _user(db, "newest@example.com")
    today = date(2026, 10, 6)
    await _lab(db, u.id, "Calcium", date(2026, 9, 20), 8.1)
    await _lab(db, u.id, "Calcium", date(2026, 10, 1), 8.9)

    found = await svc.measured_dates_for(db, u.id, ["calcium_mg"], today)
    assert found["calcium_mg"] == date(2026, 10, 1)


@pytest.mark.asyncio
async def test_a_spelling_variant_resolves_through_the_shared_vocabulary(db):
    """§3ax: "K+" and "Potassium" are one analyte, and this must not grow a
    second alias table to know that."""
    u = await _user(db, "spelling@example.com")
    today = date(2026, 10, 6)
    await _lab(db, u.id, "K+", date(2026, 10, 2), 4.8)

    found = await svc.measured_dates_for(db, u.id, ["potassium_mg"], today)
    assert found.get("potassium_mg") == date(2026, 10, 2)


@pytest.mark.asyncio
async def test_another_patients_labs_are_not_borrowed(db):
    mine = await _user(db, "mine@example.com")
    theirs = await _user(db, "theirs@example.com")
    today = date(2026, 10, 6)
    await _lab(db, theirs.id, "Calcium", date(2026, 10, 1), 8.9)

    assert await svc.measured_dates_for(db, mine.id, ["calcium_mg"], today) == {}


# ─────────────────────────────────────────────────────────────────────
# The notice itself
# ─────────────────────────────────────────────────────────────────────

def _goal(key="calcium_mg", name="Calcium", kind="target"):
    return {"key": key, "name": name, "unit": "mg", "goal": 1000.0, "kind": kind}


def _binder():
    return Effect(
        agent_kind="medication", agent_key="calcium carbonate",
        agent_label="Calcium Carbonate", nutrient_key="calcium_mg",
        direction="adds", magnitude=0.4, magnitude_unit="g",
        basis="per_dose_unit", dose_unit="mg", mechanism="elemental calcium",
        provenance="llm", evidence_level="high", confidence=0.6,
    )


def _exposure():
    # `kind`/`key`/`label`, NOT the `agent_*` names the database column list
    # uses — `Effect` spells them `agent_kind`/`agent_label` and `AgentExposure`
    # does not, and writing the table's names here cost four failures.
    return AgentExposure(
        kind="medication", key="calcium carbonate", label="Calcium Carbonate",
        occurrences=1, dose_amount=1000.0, dose_unit="mg",
    )


def _withheld_for(measured_on):
    _, day = apply_effects_to_totals(
        [_goal()], [_exposure()], [_binder()], measured_on=measured_on)
    return day.applied[0].withheld or ""


def test_without_a_recent_result_the_notice_names_the_nutrient():
    """It may say a result is missing. It may not say no blood test exists."""
    text = _withheld_for({})
    assert "Calcium" in text
    assert "blood test for Calcium" in text
    assert "There isn't one," not in text, (
        "that phrasing claims the whole record has no blood test")


def test_with_a_recent_result_the_blood_test_notice_is_gone():
    text = _withheld_for({"calcium_mg": date(2026, 10, 1)})
    assert "needs a recent blood test" not in text, (
        "a panel five days old is exactly the confirmation this asked for")


def test_a_confirmed_effect_still_is_not_counted_while_uncalibrated():
    """Honesty fix only — it must NOT start moving a clinical total.

    Every one of the 26 stored effect rows is `llm` or `literature_prior`, and
    `calibrated` is `provenance in ("clinician","measured")`, so none of them
    is calibrated and nothing may be credited yet. Confirming the blood test
    changes the SENTENCE, not the number.
    """
    adjusted, day = apply_effects_to_totals(
        [_goal()], [_exposure()], [_binder()],
        measured_on={"calcium_mg": date(2026, 10, 1)})

    applied = day.applied[0]
    assert applied.applied is False
    assert applied.delta == 0.0
    assert adjusted[0]["goal"] == 1000.0
    assert "has not been confirmed" in (applied.withheld or "")


def test_the_legacy_flag_still_works_when_no_mapping_is_supplied():
    """24 existing tests pass `measurement_fresh=`; none may change meaning."""
    _, gated = apply_effects_to_totals(
        [_goal()], [_exposure()], [_binder()], measurement_fresh=False)
    assert "blood test" in (gated.applied[0].withheld or "")

    _, fresh = apply_effects_to_totals(
        [_goal()], [_exposure()], [_binder()], measurement_fresh=True)
    assert "blood test" not in (fresh.applied[0].withheld or "")


# ─────────────────────────────────────────────────────────────────────
# GUARD — fails against the pre-change tree
# ─────────────────────────────────────────────────────────────────────

def test_no_caller_hardcodes_the_freshness_flag():
    """A literal here is a claim about the record made without reading it.

    §3ag: a static check beats a behavioural one for this. Stubbing the service
    never reaches the call site, which is precisely where the lie lived.
    """
    root = Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "measurement_fresh" and isinstance(kw.value, ast.Constant):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not offenders, (
        "these state whether a blood test exists without asking: " f"{offenders}")


def test_the_reader_goes_through_the_shared_analyte_vocabulary():
    """Never a second alias table (§3ax, §3c: don't add aliases)."""
    src = inspect.getsource(svc.measured_dates_for)
    assert "analyte_key" in src
    assert "_SERUM_TESTS" not in src
