"""Lock clinical + personalized Daily Nutrient Goal behavior (pure, deterministic).

Conditions take precedence over fitness/diet goals (clinical safety first).
"""
from app.services.nutrient_goals_service import compute_goals


def _goal(result, key):
    return next((g for g in result["goals"] if g["key"] == key), None)


# ── Clinical (condition-driven) ──────────────────────────────────────────
def test_dialysis_potassium_weight_based():
    r = compute_goals(sex="male", current_weight_kg=70,
                      conditions=[{"condition_name": "ESRD on hemodialysis"}])
    g = _goal(r, "potassium_mg")
    assert g["kind"] == "limit" and 2700 <= g["goal"] <= 2900  # ~40 mg/kg, not flat 2500


def test_dialysis_potassium_scales_with_weight():
    light = _goal(compute_goals(sex="male", current_weight_kg=55,
                                conditions=[{"condition_name": "dialysis"}]), "potassium_mg")["goal"]
    heavy = _goal(compute_goals(sex="male", current_weight_kg=95,
                                conditions=[{"condition_name": "dialysis"}]), "potassium_mg")["goal"]
    assert light < heavy and light >= 2000 and heavy <= 3000


def test_general_potassium_is_nih_ai():
    g = _goal(compute_goals(sex="male", current_weight_kg=70), "potassium_mg")
    assert g["kind"] == "target" and g["goal"] == 3400


def test_hypertension_sodium_limit():
    g = _goal(compute_goals(sex="female", current_weight_kg=70,
                            conditions=[{"condition_name": "hypertension"}]), "sodium_mg")
    assert g["goal"] == 1500 and g["kind"] == "limit"


# ── Personalized (fitness / diet goals) ──────────────────────────────────
_BASE = dict(sex="male", date_of_birth="1990-01-01", height_cm=180,
             current_weight_kg=85, activity_level="moderate")


def test_weight_loss_energy_deficit():
    base = compute_goals(**_BASE)
    loss = compute_goals(**_BASE, fitness_goals=["weight_loss"])
    assert loss["energy_kcal"] < base["energy_kcal"]


def test_muscle_gain_raises_protein_and_energy():
    base = compute_goals(**_BASE)
    gain = compute_goals(**_BASE, fitness_goals=["muscle_gain"])
    assert gain["energy_kcal"] > base["energy_kcal"]
    assert _goal(gain, "protein_g")["goal"] >= 1.5 * 85


def test_keto_macro_split():
    r = compute_goals(**_BASE, dietary_preferences=["keto"])
    assert _goal(r, "carbs_g")["goal"] < _goal(r, "fat_g")["goal"]


def test_allergies_surface_as_notes():
    r = compute_goals(**_BASE, allergies=["peanuts", "shellfish"])
    assert any("peanut" in n.lower() for n in r.get("notes", []))


def test_condition_overrides_diet_preference():
    # Dialysis protein target must win over a keto/high-protein preference.
    r = compute_goals(sex="male", current_weight_kg=70,
                      conditions=[{"condition_name": "hemodialysis"}],
                      dietary_preferences=["high-protein"])
    assert "Dialysis" in _goal(r, "protein_g")["rationale"]
