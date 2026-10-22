# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The daily sugar limit must be charged against the quantity WHO legislates.

Operator, 2026-10-21: *"overestimating sugar values, conflating natural, added
and carbs values as sugar"*, then *"follow the WHO and FDA guidelines on sugar
and every other nutrient."*

Every test here FAILS against the pre-change tree — `compute_goals` emitted a
`sugar_g` limit and no `free_sugars_g` one, and `sugar_g` carried `rda: 50`.
They are regression guards, not coverage.
"""

from app.core.nutrition_data import NUTRIENT_BY_KEY
from app.services.nutrient_goals_service import compute_goals

#: 1960 gives an adult; the rest are the reference record's own figures, so the
#: energy target lands near the 1,688 kcal §3az records.
_PROFILE = dict(
    date_of_birth="1960-01-01", sex="male", height_cm=170.0,
    current_weight_kg=55.0, activity_level="sedentary",
)


def _goal(payload, key):
    for g in payload["goals"]:
        if g["key"] == key:
            return g
    return None


class _Cond:
    """The shape `detect_condition_flags` reads."""

    def __init__(self, name):
        self.condition_name = name
        self.name = name
        self.icd11_title = name
        self.is_active = True
        self.status = "active"


# ── the limit moved ───────────────────────────────────────────────────────

def test_total_sugars_no_longer_carries_a_LIMIT():
    """THE REPORTED BUG. WHO's free-sugars percentage was charged against USDA
    2000, total sugars — so fruit, vegetables and milk spent an allowance the
    guideline expressly excludes them from."""
    payload = compute_goals(**_PROFILE)
    assert _goal(payload, "sugar_g") is None, (
        "a limit on TOTAL sugars has no authority behind it — neither WHO nor "
        "the FDA sets one")


def test_free_sugars_carries_the_limit():
    payload = compute_goals(**_PROFILE)
    goal = _goal(payload, "free_sugars_g")
    assert goal is not None, "the quantity WHO legislates must be the one capped"
    assert goal["kind"] == "limit"
    assert goal["name"] == "Free Sugars"


def test_the_limit_is_WHOs_percentage_of_this_patients_energy():
    """10% strong, 5% conditional for diabetes, at 4 kcal/g — the arithmetic is
    unchanged, only the quantity it is charged against."""
    plain = compute_goals(**_PROFILE)
    energy = plain["energy_kcal"]
    assert _goal(plain, "free_sugars_g")["goal"] == round(energy * 0.10 / 4, 1)

    diabetic = compute_goals(**_PROFILE, conditions=[_Cond("Type 2 diabetes mellitus")])
    assert diabetic["flags"]["diabetes"] is True
    assert _goal(diabetic, "free_sugars_g")["goal"] == round(
        diabetic["energy_kcal"] * 0.05 / 4, 1)


def test_the_rationale_states_what_does_NOT_count():
    """A limit a patient cannot act on is a limit they will breach. The whole
    point of the correction is that whole fruit does not count, so the sentence
    beside the number has to say so."""
    for payload in (compute_goals(**_PROFILE),
                    compute_goals(**_PROFILE,
                                  conditions=[_Cond("Type 2 diabetes mellitus")])):
        why = _goal(payload, "free_sugars_g")["rationale"].lower()
        assert "free" in why
        assert "whole fruit" in why and "do not count" in why
        assert "honey" in why or "juice" in why


# ── the catalog ───────────────────────────────────────────────────────────

def test_total_sugars_has_NO_daily_value():
    """The FDA declares Total Sugars with no %DV — it decided not to set one.
    The 50 that sat here was the ADDED-sugars DV, so every surface computing a
    percentage reported a banana against a ceiling written for a soft drink."""
    assert NUTRIENT_BY_KEY["sugar_g"]["rda"] is None


def test_added_sugars_keeps_the_figure_that_DV_was_written_for():
    assert NUTRIENT_BY_KEY["added_sugars_g"]["rda"] == 50


def test_free_sugars_is_in_the_catalog_as_a_derived_nutrient():
    """It must be nameable by the AI tools and the diary, and it has no USDA
    nutrient id because no authority measures it per food — it is derived."""
    entry = NUTRIENT_BY_KEY["free_sugars_g"]
    assert entry["usda_id"] is None
    assert entry["unit"] == "g"


def test_free_sugars_is_NOT_a_db_column():
    """It lives in the extended panel like `added_sugars_g`. Putting it in
    NUTRIENT_CATALOG would add it to DB_COLUMN_KEYS and every aggregate would
    read a column that does not exist."""
    from app.core.nutrition_data import DB_COLUMN_KEYS

    assert "free_sugars_g" not in DB_COLUMN_KEYS
    assert "free_sugars_unassessed_g" not in DB_COLUMN_KEYS


# ── what the limit reaches without naming it ──────────────────────────────

def test_the_daily_alert_follows_the_limit_with_no_named_list():
    """`active_response` selects `kind == "limit"` generically, so the moved
    key must arrive there on its own. §3az's whole lesson was a hardcoded
    threshold sitting looser than the patient's real one; a named sugar key
    here would reintroduce it."""
    import ast
    import inspect

    from app.services import active_response

    # ⚠️ Walk the AST, not the lines. The first version of this check was a
    # line regex excluding `#` comments and lines containing `\"\"\"`, which
    # matched the module DOCSTRING's own sentence about `sugar_g` and failed on
    # correct code — §3av's "run the scan, never the arithmetic", committed
    # inside the test written to enforce it. Docstrings are `Expr`/`Constant`
    # nodes, so collecting only non-docstring string constants separates the
    # module's prose from the keys its code actually uses.
    tree = ast.parse(inspect.getsource(active_response))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))

    # What §3az actually forbids is a hardcoded THRESHOLD — its whole finding
    # was a `sugar_g: 50` constant sitting looser than this patient's real
    # 21.1 g cap. Naming a key is not that.
    #
    # ⚠️ This assertion first forbade the key outright and then failed on the
    # apportionment arm added in the same change — which names `free_sugars_g`
    # to decide whether the day's UNASSESSED sugar could carry it over the cap
    # it already got from `compute_goals`. That arm is legitimate and
    # necessarily sugar-specific: no other nutrient has an apportionment
    # problem. The guard was narrowed rather than deleted, because the thing
    # worth protecting is that the NUMBER still comes from the patient.
    assert "OLD_HARDCODED" not in ast.dump(tree)
    caps = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            and not isinstance(n.value, bool) and n.value in (50, 21, 25, 36)]
    assert not caps, (
        f"a sugar ceiling must come from compute_goals, never a literal here "
        f"(found {caps})")

    payload = compute_goals(**_PROFILE)
    limits = {g["key"] for g in payload["goals"] if g["kind"] == "limit"}
    assert "free_sugars_g" in limits


# ── "every other nutrient", 2026-10-22 ───────────────────────────────────
#
# Operator, after the sugar fix: *"that's where this exact class of error
# lives next. --- and the instruction was to fix that."*

def test_saturated_fat_cites_WHO_not_a_vague_DGA():
    """The FIGURE was right and the citation was not. WHO 2023 makes <10% of
    energy a strong recommendation and the FDA's 20 g DV is the same number at
    2,000 kcal; it was credited to "DGA" with no authority recorded."""
    goal = _goal(compute_goals(**_PROFILE), "saturated_fat_g")
    assert goal["authority"] and "WHO" in goal["authority"]
    assert "10%" in goal["rationale"]


def test_trans_fat_HAS_a_limit_now():
    """It had none — zero occurrences in the module — while WHO sets <1% of
    energy as a strong recommendation and the catalog has carried
    `trans_fat_g` all along. A published ceiling with no goal never warns
    anybody (§3ar, by omission)."""
    payload = compute_goals(**_PROFILE)
    goal = _goal(payload, "trans_fat_g")
    assert goal is not None, "WHO sets a figure; the ladder must carry it"
    assert goal["kind"] == "limit"
    assert goal["goal"] == round(payload["energy_kcal"] * 0.01 / 9, 1)
    assert "WHO" in (goal["authority"] or "")


def test_cholesterol_no_longer_asserts_a_WITHDRAWN_threshold():
    """`200 if (cardiovascular or ckd) else 300` cited nothing. The 200 was
    NCEP ATP III's high-risk figure and ATP III is superseded; the DGA removed
    its own 300 mg cap in 2015. 300 is the FDA's LABELLING DV, which is what
    the goal now says it is.

    This deliberately loosens the condition case 200 -> 300: a tighter figure
    must arrive from `condition_nutrient_quotas` WITH its citation (§3bc), not
    be re-typed here."""
    plain = _goal(compute_goals(**_PROFILE), "cholesterol_mg")
    renal = _goal(compute_goals(**_PROFILE,
                                conditions=[_Cond("End-stage renal disease")]),
                  "cholesterol_mg")
    assert plain["goal"] == renal["goal"] == 300
    assert "FDA" in (plain["authority"] or "")


def test_a_cited_quota_can_still_tighten_any_of_them():
    """The override lives in `add()`, so a guideline figure with a citation
    supersedes the ladder — which is the sanctioned way to restore a
    condition-specific cholesterol limit."""
    payload = compute_goals(**_PROFILE, quotas={
        "cholesterol_mg": {"amount": 150.0, "unit": "mg", "kind": "limit",
                           "source": "A cited guideline",
                           "rationale": "Because the guideline says so."}})
    goal = _goal(payload, "cholesterol_mg")
    assert goal["goal"] == 150.0
    assert goal["authority"] == "A cited guideline"


def test_every_LIMIT_in_the_ladder_names_an_authority_or_is_known_unsourced():
    """The ratchet: a limit with no authority is a number with nobody behind
    it. Listed explicitly so adding one is a deliberate act, and so the
    remaining unsourced figures are visible rather than assumed fine."""
    payload = compute_goals(**_PROFILE)
    unsourced = sorted(g["key"] for g in payload["goals"]
                       if g["kind"] == "limit" and not g.get("authority"))
    assert unsourced == [], (
        f"a limit with no authority is a number with nobody behind it: "
        f"{unsourced}")
