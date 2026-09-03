"""Food guidance, pinned against the production record that motivated it.

User 63 lists `Penicilin, Latex, Heparine, Raw Apples, Raw Berries` with
`G6PD Deficiency` under food intolerances, and was served "1 small apple".

Two design corrections are pinned here as well as the behaviour:

  * a condition TRIGGER is not an allergy — favism is enzymatic, coeliac is
    autoimmune, an allergy is immune-mediated and patient-declared;
  * guidance runs in BOTH directions — conditions have mitigators, and a module
    that only removes food is a restriction list, not nutrition advice.

Condition facts arrive from `condition_nutrition_service` (resolved once and
stored). Nothing about G6PD, coeliac or any other condition is written here.
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


def _fact(relation, subject, *, kind="food", mechanism=None, condition="G6PD deficiency"):
    """Stand-in for condition_nutrition_service.NutritionFact."""
    return SimpleNamespace(
        relation=relation, subject=subject, subject_kind=kind,
        mechanism=mechanism, condition=condition,
        reason=f"{condition} — {mechanism}" if mechanism else subject,
    )


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
    g = fs.build_guidance(_patient())
    hits = fs.violations("1 small apple (95 kcal, 150mg potassium)", g.avoid)
    assert hits, "the exact breakfast item served to an apple-allergic patient"
    assert any("apple" in h.term for h in hits)


def test_the_general_tip_that_shipped_is_blocked():
    g = fs.build_guidance(_patient())
    assert fs.violations("Choose low-potassium fruits (apples, grapes)", g.avoid)


def test_compound_words_match_either_half():
    """Found live: "Pork tenderloin with applesauce" reached an allergic patient.

    The suffix case ("blueberries") was handled and the prefix case was not.
    """
    g = fs.build_guidance(_patient())
    assert fs.violations("Pork tenderloin with applesauce", g.avoid)
    assert fs.violations("apple juice", g.avoid)
    assert fs.violations("blueberry muffin", g.avoid)


def test_plural_and_qualifier_forms_match():
    g = fs.build_guidance(_patient())
    for text in ("apple", "Apples", "raw apple", "baked apples"):
        assert fs.violations(text, g.avoid), text


# ── the template fallback is static text nobody had checked ────────────


def test_renal_template_items_are_blocked():
    g = fs.build_guidance(_patient())
    assert fs.violations("Cream of wheat with blueberries", g.avoid)
    assert fs.violations("Waffles with strawberries", g.avoid)


# ── a trigger is NOT an allergy ────────────────────────────────────────


def test_condition_triggers_are_enforced_but_classified_separately():
    g = fs.build_guidance(_patient(), [
        _fact("avoid", "fava beans",
              mechanism="triggers acute haemolysis (favism)"),
    ])
    hits = fs.violations("Ful medames with fava beans", g.avoid)
    assert hits
    hit = hits[0]
    assert hit.kind == fs.CONDITION_TRIGGER
    assert hit.kind != fs.ALLERGY, "favism is enzymatic, not an allergy"
    assert "favism" in (hit.mechanism or "")


def test_patient_declared_allergies_keep_the_allergy_kind():
    g = fs.build_guidance(_patient())
    apple = next(r for r in g.avoid if r.term == "apple")
    assert apple.kind == fs.ALLERGY


def test_nothing_about_any_condition_is_hardcoded():
    """With no facts supplied, only what the PATIENT declared is enforced.

    The first version carried a dict mapping "g6pd" to four bean names. If that
    ever comes back, this fails.
    """
    g = fs.build_guidance(_patient(), facts=[])
    assert not fs.violations("Ful medames with fava beans", g.avoid)
    assert not fs.violations("stewed broad beans", g.avoid)
    # …while the patient's own declarations still hold.
    assert fs.violations("apple", g.avoid)


# ── the half that was missing entirely ─────────────────────────────────


def test_mitigators_are_carried_as_positive_guidance():
    g = fs.build_guidance(_patient(), [
        _fact("favour", "folate", kind="nutrient",
              mechanism="supports red cell production",
              condition="Chronic anaemia"),
        _fact("favour", "vitamin C", kind="nutrient",
              mechanism="improves non-haem iron absorption",
              condition="Chronic anaemia"),
    ])
    subjects = {e.subject for e in g.favour}
    assert subjects == {"folate", "vitamin C"}
    assert all(e.subject_kind == "nutrient" for e in g.favour)


def test_a_mitigator_is_never_treated_as_something_to_avoid():
    g = fs.build_guidance(SimpleNamespace(
        allergies=None, food_intolerances=None, dietary_restrictions=None), [
        _fact("favour", "leafy greens", mechanism="folate source"),
    ])
    assert g.avoid == []
    assert fs.is_safe("spinach and leafy greens salad", g.avoid)


def test_prompt_block_states_both_directions():
    g = fs.build_guidance(_patient(), [
        _fact("avoid", "fava beans", mechanism="triggers acute haemolysis (favism)"),
        _fact("favour", "folate", kind="nutrient",
              mechanism="supports red cell production"),
    ])
    block = fs.prompt_block(g)
    assert "MUST NOT BE OFFERED" in block
    assert "PRIORITISE" in block
    assert "fava bean" in block and "folate" in block


def test_prompt_block_is_empty_when_nothing_applies():
    g = fs.build_guidance(SimpleNamespace(
        allergies=None, food_intolerances=None, dietary_restrictions=None))
    assert fs.prompt_block(g) == ""
    assert not g


# ── it must not block the whole menu ───────────────────────────────────


def test_ordinary_renal_foods_stay_available():
    g = fs.build_guidance(_patient())
    for meal in (
        "4 oz baked cod with white rice",
        "grilled chicken breast and steamed carrots",
        "scrambled eggs with zucchini",
        "cream of wheat",
    ):
        assert fs.is_safe(meal, g.avoid), meal


def test_non_food_allergens_do_not_match_food_text():
    # Penicillin/Latex/Heparin are drug and material allergies; they must not
    # start rejecting meals.
    g = fs.build_guidance(_patient())
    assert fs.is_safe("chicken and rice", g.avoid)


def test_word_boundary_not_substring():
    # "egg" must not reject "eggplant" by substring.
    g = fs.build_guidance(SimpleNamespace(
        allergies="Eggs", food_intolerances=None, dietary_restrictions=None))
    assert fs.violations("scrambled eggs", g.avoid)
    assert fs.is_safe("roasted eggplant", g.avoid)


def test_a_patient_with_no_allergies_blocks_nothing():
    g = fs.build_guidance(SimpleNamespace(
        allergies=None, food_intolerances=None, dietary_restrictions=None))
    assert g.avoid == []
    assert fs.is_safe("anything at all", g.avoid)


# ── the guard has to be able to explain itself (canon §3aj) ────────────


def test_every_restriction_carries_a_reason_and_a_kind():
    g = fs.build_guidance(_patient(), [
        _fact("avoid", "fava beans", mechanism="triggers acute haemolysis (favism)"),
    ])
    assert all(r.reason and r.kind for r in g.avoid)


# ── conditions disagree, and the disagreement is dangerous ─────────────


def test_a_capped_nutrient_is_never_prioritised():
    """Found in real resolved guidance for a patient with BOTH hypertension
    and ESRD: hypertension asks to prioritise potassium (DASH), ESRD caps it.
    Telling a planner to load a dialysis patient with potassium is how
    hyperkalemia happens."""
    g = fs.build_guidance(
        SimpleNamespace(allergies=None, food_intolerances=None, dietary_restrictions=None),
        [_fact("favour", "potassium", kind="nutrient",
               mechanism="promotes vasodilation", condition="Hypertension")],
        nutrient_limits=["Potassium", "Phosphorus", "Sodium"],
    )
    assert g.favour == [], "a capped nutrient must not be encouraged"


def test_an_uncapped_mitigator_survives_the_arbiter():
    g = fs.build_guidance(
        SimpleNamespace(allergies=None, food_intolerances=None, dietary_restrictions=None),
        [_fact("favour", "Vitamin B12", kind="nutrient",
               mechanism="red cell maturation", condition="Renal anaemia")],
        nutrient_limits=["Potassium", "Phosphorus"],
    )
    assert [e.subject for e in g.favour] == ["Vitamin B12"]


def test_a_restriction_outranks_an_encouragement():
    """One condition's mitigator is another's trigger."""
    g = fs.build_guidance(
        SimpleNamespace(allergies="Nuts", food_intolerances=None,
                        dietary_restrictions=None),
        [_fact("favour", "nuts", mechanism="magnesium source",
               condition="Hypertension")],
    )
    assert g.favour == []
    assert fs.violations("mixed nuts", g.avoid)


def test_medications_are_not_meal_guidance():
    """"Phosphate binders" came back as something to favour. It is a drug."""
    g = fs.build_guidance(
        SimpleNamespace(allergies=None, food_intolerances=None, dietary_restrictions=None),
        [_fact("favour", "phosphate binders", mechanism="reduce absorption"),
         _fact("favour", "egg whites", mechanism="low-phosphorus protein")],
    )
    assert [e.subject for e in g.favour] == ["egg whites"]


def test_conditional_advice_the_system_cannot_evaluate_is_dropped():
    g = fs.build_guidance(
        SimpleNamespace(allergies=None, food_intolerances=None, dietary_restrictions=None),
        [_fact("favour", "Potassium (in non-CKD stage 5 patients)", kind="nutrient",
               mechanism="acid-base balance")],
    )
    assert g.favour == []


# ── normalisation must not mangle clinical words ───────────────────────


def test_us_and_is_words_are_not_treated_as_plurals():
    """Real resolved guidance produced "citru" and "phosphoru"."""
    assert fs._normalise("citrus") == "citrus"
    assert fs._normalise("phosphorus") == "phosphorus"
    assert fs._normalise("asparagus") == "asparagus"
    # …while real plurals still fold.
    assert fs._normalise("apples") == "apple"
    assert fs._normalise("berries") == "berry"
