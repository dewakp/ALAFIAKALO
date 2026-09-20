"""The effects store resolves and remembers; it never carries typed-in facts.

`nutrient_effects` exists because the previous design charged a code change per
clinical fact — adding protein as a fifth dialysis analyte cost a `GOAL_KEY`
entry, a bespoke `elif`, and an inline unit hack. A store that quietly grew its
own hardcoded table would have bought nothing, so the rule is enforced here
rather than described in a docstring (§3an, whose equivalent test exists for the
same reason).
"""

from __future__ import annotations

import ast
import inspect

import pytest
from sqlalchemy import select

from app.models.nutrient_effect import (
    ADDS, BINDS_DIETARY, BLOCKS_ABSORPTION, INCREASES_REQUIREMENT, REMOVES,
    PER_SESSION, NutrientEffect,
)
from app.services import nutrient_effects_service as nes


# ── The anti-hardcoding guard ─────────────────────────────────────────

def _executable_strings(module) -> str:
    """Every string literal in the module EXCEPT docstrings.

    Comments are not AST nodes, so prose explaining the design is exempt
    automatically; docstrings are subtracted explicitly. What remains is what
    the code actually executes — which is where a smuggled lookup table lives.
    """
    tree = ast.parse(inspect.getsource(module))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                out.append(node.value)
    return " ".join(out).lower()


#: Named agents and nutrients whose appearance in executable code means someone
#: typed clinical knowledge in again. Vocabulary ("binds_dietary",
#: "per_litre_dialysate") is not knowledge and is deliberately absent here.
_TELLTALES = (
    "sevelamer", "furosemide", "metformin", "omeprazole", "venofer",
    "calcitriol", "dextrose", "lanthanum",
)


def test_the_service_hardcodes_no_agent_to_nutrient_mapping():
    """Fails the build if a literal agent→nutrient fact reappears."""
    src = _executable_strings(nes)
    for token in _TELLTALES:
        assert token not in src, (
            f"{token!r} appears in nutrient_effects_service code. Effects are "
            "resolved and stored, never typed in (§3ad, §3c, §3an)."
        )


def test_the_prompt_does_not_seed_an_effect_example():
    """The prompt must carry a SHAPE, never an example pair.

    `condition_nutrition_service` learned this the hard way: its resolution
    prompt used "fava beans" as the example, which both hardcoded a mapping and
    biased every answer toward it. An effects prompt showing "phosphate binder →
    phosphorus" would be the identical mistake one domain over.
    """
    prompt = nes._RESOLVE_PROMPT.lower()
    for token in _TELLTALES:
        assert token not in prompt, f"the resolution prompt names {token!r}"
    # The placeholders must still be placeholders.
    assert "<nutrient name or key>" in prompt
    assert "{agent_label}" in nes._RESOLVE_PROMPT


# ── The nutrient vocabulary is the catalog, not a new list ────────────

def test_a_nutrient_outside_the_catalog_is_refused():
    """A fact nothing can apply is worse than an absent one — it looks like coverage."""
    assert nes.resolve_nutrient_key("phlogiston") is None
    assert nes.resolve_nutrient_key("") is None


def test_clinical_names_resolve_onto_catalog_keys():
    """The model answers in clinical language, not in our column names."""
    assert nes.resolve_nutrient_key("magnesium_mg") == "magnesium_mg"
    assert nes.resolve_nutrient_key("Magnesium") == "magnesium_mg"
    # "Thiamine (B1)" in the catalog; a model will say "thiamine".
    assert nes.resolve_nutrient_key("thiamine") == "vitamin_b1_thiamine_mg"


# ── One drug is one agent, however it was written ─────────────────────

def test_one_drug_spelled_three_ways_is_one_agent_key():
    """`flowsheet_drugs` states the rule: fold every source through it "or the
    unified record duplicates".

    The same medication arrives as "Venofer" on a flowsheet, "venofer" in a
    dose log and "Iron sucrose" from a FHIR import. Keying the store on the raw
    spelling would hold three independent sets of facts for one drug, each
    converging only on itself — §3ab's contradictory duplicate, built into the
    mechanism meant to prevent it.
    """
    keys = {
        nes.normalize_agent("Venofer", "medication"),
        nes.normalize_agent("venofer", "medication"),
        nes.normalize_agent("Iron sucrose", "medication"),
    }
    assert len(keys) == 1, f"one drug produced {len(keys)} agent keys: {keys}"


def test_a_brand_canonicalises_to_its_ingredient():
    """The dev record writes "Epogene" 1,900+ times; the drug is Epoetin alfa."""
    assert nes.normalize_agent("Epogene", "medication") == "epoetin alfa"


def test_a_treatment_name_is_not_folded_through_the_drug_map():
    """Only drug-like agents have a canonical drug form."""
    assert nes.normalize_agent("Hemodialysis", "treatment") == "hemodialysis"
    assert nes.normalize_agent("End-Stage Renal Disease", "condition") == "end-stage renal disease"


def test_an_unrecognised_drug_is_normalised_but_never_renamed():
    """Never guess. An unmatched drug name is a gap; a wrongly-matched one is
    a clinical error (the rule `canonical_drug_name` states for itself)."""
    assert nes.normalize_agent("Marine Bone Discovery", "medication") == "marine bone discovery"


# ── Gating is about false reassurance, not about sign ─────────────────

@pytest.mark.parametrize("direction,goal_kind,expected", [
    # Lowering a LIMIT creates dietary headroom — justify it.
    (REMOVES, "limit", True),
    (BINDS_DIETARY, "limit", True),
    (BLOCKS_ABSORPTION, "limit", True),
    # Raising a LIMIT tightens the budget — no permission needed.
    (ADDS, "limit", False),
    # Lowering a TARGET tells the patient to eat more — the safe direction,
    # and exactly why protein loss is ungated today.
    (REMOVES, "target", False),
    # Raising a TARGET says "you are fine". Nothing gates this today, and it is
    # the dangerous one: crediting IV iron would tell an anaemic patient they
    # had met their needs.
    (ADDS, "target", True),
    (INCREASES_REQUIREMENT, "target", True),
])
def test_gate_needed_follows_reassurance_not_sign(direction, goal_kind, expected):
    assert nes.gate_needed(direction, goal_kind) is expected


# ── Scaling must reproduce the shipping protein prior exactly ─────────

def _protein_effect() -> nes.Effect:
    """Protein as the store would hold it — the migration's first real case."""
    return nes.Effect(
        agent_kind="treatment", agent_key="hemodialysis", agent_label="Hemodialysis",
        nutrient_key="protein_g", direction=REMOVES,
        magnitude=9.0, magnitude_unit="g", basis=PER_SESSION,
        scales_with="dialysate_volume_l", scale_reference=30.0,
        scale_min=0.5, scale_max=2.0,
    )


@pytest.mark.parametrize("volume_l,expected_g", [
    (30.0, 9.0),      # the reference prescription
    (15.0, 4.5),      # half the volume, half the loss
    (60.0, 18.0),     # double, at the clamp ceiling
    (120.0, 18.0),    # beyond it — clamped, NOT four times the loss
    (3.0, 4.5),       # below the floor — clamped at 0.5x
])
def test_scaled_magnitude_reproduces_the_protein_prior(volume_l, expected_g):
    """`grams_per_session * max(0.5, min(volume/30.0, 2.0))`, exactly.

    If the store cannot reproduce today's shipping numbers, migrating protein
    into it is a rewrite wearing a migration's name.
    """
    effect = _protein_effect()
    got = effect.scaled_magnitude({"dialysate_volume_l": volume_l})
    assert got == pytest.approx(expected_g)


def test_an_unscaled_effect_returns_its_magnitude_unchanged():
    effect = nes.Effect(
        agent_kind="medication", agent_key="a drug", agent_label="A Drug",
        nutrient_key="iron_mg", direction=ADDS, magnitude=100.0,
        magnitude_unit="mg", basis=nes.PER_DOSE_UNIT,
    )
    assert effect.scaled_magnitude({"dialysate_volume_l": 60.0}) == 100.0


def test_a_null_magnitude_stays_null():
    """Recording THAT an effect exists is useful; inventing its size is not."""
    effect = nes.Effect(
        agent_kind="treatment", agent_key="hemodialysis", agent_label="Hemodialysis",
        nutrient_key="vitamin_b1_thiamine_mg", direction=REMOVES,
        magnitude=None, magnitude_unit=None, basis=PER_SESSION,
    )
    assert effect.scaled_magnitude({"dialysate_volume_l": 30.0}) is None


# ── Re-resolution converges on one row ────────────────────────────────

@pytest.mark.parametrize("volume_l", [15.0, 30.0, 45.0, 60.0, 90.0])
def test_the_store_reproduces_the_shipping_model_exactly(volume_l):
    """The word "migration" has to be earned against the model, not my arithmetic.

    `test_scaled_magnitude_reproduces_the_protein_prior` asserts against numbers
    I typed into this file, so it would happily pass while both sides drifted
    together. This one compares the store's output to what
    `estimate_session_removal` actually produces today, reading the magnitude
    and the reference volume from the same constants the model uses. If either
    side changes, the build fails — which is the only reason to call this a
    migration rather than a rewrite.
    """
    from app.services.dialysis_balance import (
        DEFAULT_COEFFICIENTS, PROTEIN, SerumLevels, SessionParams,
        _REFERENCE_DIALYSATE_L, estimate_session_removal,
    )

    session = SessionParams(
        dialysate_volume_l=volume_l, duration_minutes=240.0,
        blood_flow_ml_min=350.0, bath_potassium_meq=1.0, completed=True,
    )
    shipped = estimate_session_removal(session, SerumLevels(), DEFAULT_COEFFICIENTS)
    assert PROTEIN in shipped, "the shipping model stopped producing protein"

    coeff = DEFAULT_COEFFICIENTS[PROTEIN]
    stored = nes.Effect(
        agent_kind="treatment", agent_key="hemodialysis", agent_label="Hemodialysis",
        nutrient_key="protein_g", direction=REMOVES,
        magnitude=coeff.grams_per_session, magnitude_unit="g", basis=PER_SESSION,
        scales_with="dialysate_volume_l", scale_reference=_REFERENCE_DIALYSATE_L,
        scale_min=0.5, scale_max=2.0,
    )
    from_store_g = stored.scaled_magnitude({"dialysate_volume_l": volume_l})
    assert from_store_g == pytest.approx(shipped[PROTEIN].mass_mg / 1000.0)


@pytest.mark.asyncio
async def test_re_resolution_sharpens_rather_than_duplicates(db):
    """§3ab: a re-derivation that inserts beside the row it meant to correct
    leaves the record holding two contradictory facts about one subject."""
    item = {
        "nutrient": "Magnesium", "direction": REMOVES, "magnitude": 40.0,
        "unit": "mg", "basis": PER_SESSION, "mechanism": "crosses the membrane",
        "evidence": "moderate",
    }
    first = await nes._upsert(
        db, agent_kind="treatment", agent_key="hemodialysis",
        agent_label="Hemodialysis", agent_code=None, item=item)
    assert first is not None and first.nutrient_key == "magnesium_mg"

    await nes._upsert(
        db, agent_kind="treatment", agent_key="hemodialysis",
        agent_label="Hemodialysis", agent_code=None, item=item)
    await db.flush()

    rows = (await db.execute(
        select(NutrientEffect).where(
            NutrientEffect.agent_key == "hemodialysis",
            NutrientEffect.nutrient_key == "magnesium_mg",
            NutrientEffect.direction == REMOVES,
        )
    )).scalars().all()
    assert len(rows) == 1, "re-resolution duplicated instead of converging"
    assert rows[0].times_confirmed == 2
    assert rows[0].confidence > 0.5


@pytest.mark.asyncio
async def test_an_unrepresentable_nutrient_is_not_stored(db):
    """Refused at write time, so the store never implies coverage it lacks."""
    got = await nes._upsert(
        db, agent_kind="medication", agent_key="a drug", agent_label="A Drug",
        agent_code=None,
        item={"nutrient": "phlogiston", "direction": ADDS, "magnitude": 1.0,
              "unit": "mg", "basis": nes.PER_DOSE_UNIT},
    )
    assert got is None
