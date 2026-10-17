# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A printed label outranks anything derived from a food NAME.

Reported in production 2026-10-17 on a Boost Glucose Control carton. The label
says 190 Cal per serving, the carton is one serving, the vision model read it
correctly and the form displayed `190 kcal · 16g protein · 16g carbs · 7g fat`.
The stored row read **108 / 7.8 / 11.7 / 3.4**.

Measured cause, reproduced exactly:

    "Boost Glucose Control (nutritional drink)"
      -> 'boost glucose control'  100.0 g     (not the 244.8 g serving)
       + 'nutritional drink'       30.0 g     (the DESCRIPTOR, as a second food)
      =  107.9 kcal over 130 g

`estimate_meal_nutrients` has treated notes as authoritative label text since
it was written, and it WORKS — fed that row's notes it returns 190/16/16/7.
Nothing asked it. The PATCH route re-estimated only when the NAME changed, so
typing the panel into Notes changed nothing, and `_enrich` never read
`serving_size` at all.

That is the harm worth naming: not a missing capability, but a correct reading
available and a fabricated number stored over it. On a renal patient it also
understated phosphorus and potassium by the same 2.45x.
"""

import datetime
import uuid

import pytest
import pytest_asyncio

from app.core.security import get_current_user
from app.main import app
from app.models.nutrition import NutritionLog
from app.models.user import User
from app.services.meal_parser import extract_nutrition_facts

PANEL = ("190 Calories, 16 g of Protein, 16 g of carbs, 3g of Fiber, "
         "4 g of sugar, 210 mg of Sodium, 7g of Fat")
FOOD = "Boost Glucose Control (nutritional drink)"


# ── the input really is a readable panel ──────────────────────────────────

def test_the_panel_the_patient_typed_is_readable():
    facts = extract_nutrition_facts(PANEL)
    assert facts is not None
    n = facts["nutrients"]
    assert n["calories"] == 190.0
    assert n["protein_g"] == 16.0
    assert n["carbs_g"] == 16.0
    assert n["fat_g"] == 7.0


def test_ordinary_prose_is_not_a_panel():
    """The trigger must be "this text yields a nutrition panel", never "this
    field changed" — appending a comment must not wipe a row's values."""
    assert extract_nutrition_facts("tasted good, had it after dialysis") is None
    assert extract_nutrition_facts("1 cup") is None
    assert extract_nutrition_facts("composite meal (130 g total)") is None


# ── the PATCH route must act on a label arriving in notes ─────────────────

@pytest.fixture
def queued(monkeypatch):
    calls: list[int] = []

    async def _fake(log_id, *a, **k):
        calls.append(log_id)

    monkeypatch.setattr("app.api.nutrition.enrich_log", _fake)
    return calls


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Test User")
    db.add(u)
    await db.flush()
    return u


async def _seed(db, user_id: int) -> NutritionLog:
    """A row in the state production was in: estimated from the name alone."""
    log = NutritionLog(
        user_id=user_id, log_date=datetime.date(2026, 10, 17),
        meal_type="breakfast", food_name=FOOD,
        calories=108.0, protein_g=7.8, carbs_g=11.7, fat_g=3.4,
        nutrient_status="done",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@pytest.mark.asyncio
async def test_a_label_typed_into_notes_triggers_re_estimation(client, db, queued):
    """THE REPORTED BUG. Name unchanged, panel added to notes."""
    user = await _user(db, f"label{uuid.uuid4().hex[:8]}@example.com")
    log = await _seed(db, user.id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.patch(f"/api/v1/nutrition/{log.id}", json={"notes": PANEL})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["nutrient_status"] == "pending", (
        "a printed panel is new evidence and must re-estimate")
    assert body["calories"] is None, "the stale 108 must not survive the label"
    assert queued == [log.id], "enrichment was never queued"


@pytest.mark.asyncio
async def test_a_label_typed_into_serving_size_also_triggers_it(client, db, queued):
    user = await _user(db, f"label{uuid.uuid4().hex[:8]}@example.com")
    log = await _seed(db, user.id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.patch(f"/api/v1/nutrition/{log.id}",
                                  json={"serving_size": PANEL})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.json()["nutrient_status"] == "pending"
    assert queued == [log.id]


@pytest.mark.asyncio
async def test_an_ordinary_note_does_NOT_wipe_the_row(client, db, queued):
    """The other half. Over-triggering would destroy values on every edit."""
    user = await _user(db, f"label{uuid.uuid4().hex[:8]}@example.com")
    log = await _seed(db, user.id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.patch(f"/api/v1/nutrition/{log.id}",
                                  json={"notes": "tasted good"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    body = resp.json()
    assert body["calories"] == 108.0, "an ordinary note must change nothing"
    assert body["nutrient_status"] == "done"
    assert queued == []


@pytest.mark.asyncio
async def test_supplied_nutrients_still_win_over_re_estimation(client, db, queued):
    """A caller sending real numbers alongside the note is stating them, and a
    stated value outranks any estimate (§3am)."""
    user = await _user(db, f"label{uuid.uuid4().hex[:8]}@example.com")
    log = await _seed(db, user.id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.patch(f"/api/v1/nutrition/{log.id}",
                                  json={"notes": PANEL, "calories": 190.0})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.json()["calories"] == 190.0
    assert queued == []


# ── the label path must not POISON the shared cache ───────────────────────

@pytest.mark.asyncio
async def test_a_panel_in_notes_is_named_after_the_FOOD_not_its_numbers(db):
    """§3am: `learned_food_nutrients` is shared and preferred over USDA and AI,
    so one bad row is served to every patient forever.

    Measured before the fix, from this exact row:

        learned_food_nutrients ->
          "190 calories, 16 g of protein, 16 g of carbs, 3g of fiber, 4"

    `extract_nutrition_facts` fills `name` with the panel's own leading text,
    so the old `if not facts.get("name")` guard could never fire.
    """
    from app.services.nutrient_estimator import estimate_meal_nutrients

    meal = await estimate_meal_nutrients(db, FOOD, notes=PANEL)
    names = [c.get("food_name") for c in meal.get("components") or []]
    assert names == [FOOD], names
    assert not any("190 calories" in (n or "").lower() for n in names)


@pytest.mark.asyncio
async def test_a_panel_with_no_serving_WEIGHT_is_not_learned_as_a_density(db, monkeypatch):
    """A panel states values PER SERVING. With no serving mass there is no
    density, and `serving_g or 100.0` silently asserts one — filing a 244.8 g
    carton's 190 kcal as 190 kcal/100 g, a 2.45x overstatement then preferred
    over USDA for every later meal (§3c)."""
    from app.services import nutrient_estimator as ne

    learned: list = []

    async def _spy(db_, name, per100, *, serving_weight_g=None, source=None, **kw):
        learned.append((name, serving_weight_g))

    monkeypatch.setattr(
        "app.services.learned_nutrient_service.record_correction", _spy)

    facts = extract_nutrition_facts(PANEL)
    assert facts["serving_g"] is None, "fixture assumption: this panel states no weight"

    meal = await ne.estimate_meal_nutrients(db, FOOD, notes=PANEL)
    agg = meal["aggregate_nutrients"]
    assert agg["calories"] == 190.0, "the meal itself must still read the label"
    assert learned == [], f"nothing may be learned without a serving weight: {learned}"


# ── a labelled product is measured by its own serving ────────────────────

#: The real seeded row, copied from production rather than invented: per-100 g
#: values and the carton's own 244.8 g serving. Seeding it here is deliberate —
#: a test that passed only because the dev database happened to hold this row
#: would be measuring the database, not the code.
BOOST_PER_100G = {
    "calories": 77.6144, "protein_g": 6.5359, "fat_g": 2.8595,
    "carbs_g": 6.5359, "fiber_g": 1.2255, "sugar_g": 1.634,
    "sodium_mg": 81.6993, "potassium_mg": 102.1242, "phosphorus_mg": 127.6552,
}


@pytest_asyncio.fixture
async def boost_label(db):
    """One carton: 244.8 g, so 190 kcal / 16 g protein / 312.5 mg phosphorus."""
    from app.models.learned_nutrient import LearnedFoodNutrient

    db.add(LearnedFoodNutrient(
        food_name_normalized="boost glucose control",
        food_name_original="Boost Glucose Control",
        nutrients=dict(BOOST_PER_100G),
        serving_weight_g=244.8, source="label", sample_count=1, confidence=1.0,
    ))
    await db.commit()

@pytest.mark.asyncio
async def test_a_learned_product_uses_its_own_serving_not_100g(db, boost_label):
    """51g. `qty_text == "default"` is the parser saying no portion was
    stated, so 100 g is a placeholder. For a product learned from a label it
    is the wrong number: the carton is 244.8 g and 190 kcal, and the patient
    had to type "8 fl oz" to get it."""
    from app.services.nutrient_estimator import estimate_meal_nutrients

    meal = await estimate_meal_nutrients(db, "Boost Glucose Control", notes=None)
    agg = meal["aggregate_nutrients"]
    assert round(agg["calories"]) == 190, agg["calories"]
    assert round(agg["protein_g"]) == 16


@pytest.mark.asyncio
async def test_the_renal_numbers_survive_a_label(db, boost_label):
    """51f. A panel lists what a label must print — not phosphorus, not
    potassium. Filling them from the store is the difference between a
    dialysis patient's two governing numbers being present and being None."""
    from app.services.nutrient_estimator import estimate_meal_nutrients

    meal = await estimate_meal_nutrients(db, FOOD, notes=PANEL)
    agg = meal["aggregate_nutrients"]
    assert round(agg["calories"]) == 190
    assert round(agg.get("phosphorus_mg") or 0) == 312, agg.get("phosphorus_mg")
    assert round(agg.get("potassium_mg") or 0) == 250, agg.get("potassium_mg")


@pytest.mark.asyncio
async def test_a_descriptor_in_brackets_is_not_a_second_food(db, boost_label):
    """The vision caption path produces "NAME (what it is)". Expanded as
    ingredients it added 30 g of an unrelated USDA "nutritional drink"."""
    from app.services.nutrient_estimator import estimate_meal_nutrients

    meal = await estimate_meal_nutrients(db, FOOD, notes=None)
    assert len(meal["components"]) == 1, [c["food_name"] for c in meal["components"]]
    assert round(meal["aggregate_nutrients"]["calories"]) == 190


@pytest.mark.asyncio
async def test_a_bracket_that_holds_real_food_is_still_food(db, boost_label):
    """The other half: "(with 2 eggs)" carries a digit and the word "with",
    so it is an ingredient list and must not be discarded."""
    from app.services.nutrient_estimator import estimate_meal_nutrients

    meal = await estimate_meal_nutrients(db, "Boost Glucose Control (with 2 eggs)", notes=None)
    names = [c["food_name"] for c in meal["components"]]
    assert len(names) > 1, names
