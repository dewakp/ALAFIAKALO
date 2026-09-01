"""The allergy guard, pinned against the production record that motivated it.

User 63 lists `Penicilin, Latex, Heparine, Raw Apples, Raw Berries` with
`G6PD Deficiency` under food intolerances, and was served "1 small apple".
"""

from types import SimpleNamespace

from app.services import food_safety as fs


def _patient(**kw):
    base = dict(
        allergies="Penicilin, Latex, Heparine, Raw Apples, Raw Berries",
        food_intolerances="G6PD Deficiency",
        dietary_restrictions=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _cond(name):
    return SimpleNamespace(name=name)


# ── parsing ────────────────────────────────────────────────────────────


def test_comma_separated_profile_text_is_parsed_not_json_decoded():
    # Canon §3ag: these fields are comma-separated text; json.loads() on them
    # is what 500'd /personalization/*.
    assert fs.profile_list("Penicilin, Latex, Heparine") == [
        "Penicilin", "Latex", "Heparine",
    ]


def test_json_array_rows_still_parse():
    assert fs.profile_list('["Shellfish", "Peanuts"]') == ["Shellfish", "Peanuts"]


def test_empty_and_none_are_empty():
    assert fs.profile_list(None) == []
    assert fs.profile_list("") == []
    assert fs.profile_list("   ") == []


# ── the actual production failure ──────────────────────────────────────


def test_the_apple_that_shipped_is_blocked():
    forbidden = fs.forbidden_for(_patient())
    hits = fs.violations("1 small apple (95 kcal, 150mg potassium)", forbidden)
    assert hits, "the exact breakfast item served to an apple-allergic patient"
    assert any("apple" in h.term for h in hits)


def test_the_general_tip_that_shipped_is_blocked():
    forbidden = fs.forbidden_for(_patient())
    assert fs.violations(
        "Choose low-potassium fruits (apples, grapes)", forbidden
    )


def test_compound_words_match_either_half():
    """Found live: "Pork tenderloin with applesauce" reached an allergic patient.

    The suffix case ("blueberries") was handled and the prefix case was not.
    """
    forbidden = fs.forbidden_for(_patient())
    assert fs.violations("Pork tenderloin with applesauce", forbidden)
    assert fs.violations("apple juice", forbidden)
    assert fs.violations("blueberry muffin", forbidden)


def test_plural_and_qualifier_forms_match():
    forbidden = fs.forbidden_for(_patient())
    for text in ("apple", "Apples", "raw apple", "baked apples"):
        assert fs.violations(text, forbidden), text


# ── the template fallback is static text nobody had checked ────────────


def test_renal_template_blueberries_are_blocked():
    forbidden = fs.forbidden_for(_patient())
    assert fs.violations("Cream of wheat with blueberries", forbidden)


def test_renal_template_strawberries_are_blocked():
    forbidden = fs.forbidden_for(_patient())
    assert fs.violations("Waffles with strawberries", forbidden)


# ── condition-derived, not listed as an allergy ────────────────────────


def test_g6pd_forbids_fava_beans_even_though_no_one_listed_them():
    forbidden = fs.forbidden_for(_patient(), [_cond("G6PD Deficitency")])
    assert fs.violations("Ful medames with fava beans", forbidden)
    hits = fs.violations("stewed broad beans", forbidden)
    assert hits and any(h.source == "condition" for h in hits)


def test_g6pd_does_not_forbid_legumes_generally():
    # Lentils and chickpeas are not contraindicated in G6PD. Blocking them
    # would cost a renal patient protein options for no clinical reason.
    forbidden = fs.forbidden_for(SimpleNamespace(
        allergies=None, food_intolerances="G6PD Deficiency",
        dietary_restrictions=None))
    assert not fs.violations("lentil soup", forbidden)
    assert not fs.violations("chickpea salad", forbidden)


# ── it must not block the whole menu ───────────────────────────────────


def test_ordinary_renal_foods_stay_available():
    forbidden = fs.forbidden_for(_patient())
    for meal in (
        "4 oz baked cod with white rice",
        "grilled chicken breast and steamed carrots",
        "scrambled eggs with zucchini",
        "cream of wheat",
    ):
        assert fs.is_safe(meal, forbidden), meal


def test_non_food_allergens_do_not_match_food_text():
    # Penicillin/Latex/Heparin are drug and material allergies; they must not
    # start rejecting meals.
    forbidden = fs.forbidden_for(_patient())
    assert fs.is_safe("chicken and rice", forbidden)


def test_word_boundary_not_substring():
    # "egg" must not reject "eggplant" by substring.
    forbidden = fs.forbidden_for(SimpleNamespace(
        allergies="Eggs", food_intolerances=None, dietary_restrictions=None))
    assert fs.violations("scrambled eggs", forbidden)
    assert fs.is_safe("roasted eggplant", forbidden)


def test_a_patient_with_no_allergies_blocks_nothing():
    forbidden = fs.forbidden_for(SimpleNamespace(
        allergies=None, food_intolerances=None, dietary_restrictions=None))
    assert forbidden == []
    assert fs.is_safe("anything at all", forbidden)


# ── the guard has to be able to explain itself (canon §3aj) ────────────


def test_every_block_carries_a_reason():
    forbidden = fs.forbidden_for(_patient(), [_cond("G6PD Deficitency")])
    assert all(f.reason and f.source for f in forbidden)


def test_prompt_block_names_each_item_and_is_empty_when_nothing_applies():
    assert fs.prompt_block([]) == ""
    block = fs.prompt_block(fs.forbidden_for(_patient()))
    assert "FORBIDDEN" in block and "apple" in block
