# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""What WHO and the FDA actually legislate about sugar — and it is not TOTAL.

Operator, 2026-10-21: *"overestimating sugar values, conflating natural, added
and carbs values as sugar"*, then *"follow the WHO and FDA guidelines on sugar
and every other nutrient. Thats wha a clinician or dietician will do."*

Both authorities set a figure, and **neither of them sets one for total sugars.**

    WHO 2015, Guideline: sugars intake for adults and children
        FREE sugars < 10% of total energy (strong), < 5% conditional.
    FDA 21 CFR 101.9(c)(6)(iii), Nutrition Facts
        ADDED sugars Daily Value 50 g. Total Sugars is declared with NO %DV,
        deliberately — the FDA declined to set one.

`nutrient_goals_service` quoted WHO's percentage and charged it against
`sugar_g`, which is USDA 2000, TOTAL sugars. For the reference record that is
1688 × 0.05 / 4 = 21.1 g, so **two bananas exhausted a diabetic's whole daily
sugar budget** on fruit WHO's definition expressly excludes.

The obvious repair — charge `added_sugars_g` instead — was measured first and
it does not work. **Added Sugars is a LABEL field, not a food-composition
field.** Asked of FoodData Central on 2026-10-21 for the same query:

    Survey (FNDDS)   0 of 5 foods carry nutrient 1235
    SR Legacy        0 of 5
    Branded          3 of 5

USDA's own wire for FNDDS 2710657 returns 65 nutrients and no 1235 at all. In
this database the field is present on 163 of 1,071 meals and every one is a
labelled product — Boost Glucose Control, peanuts, cider vinegar — while
July, September and October 2026 carry it on ZERO meals. A limit charged
against it would have read `0 of 21 g` every day of a record whose meals are
eba, dodo, okro and jollof rice: §3ar's dead control, reporting perfect
compliance to a diabetic. That is worse than over-charging fruit, not better.

So the quantity is DERIVED, the way a dietitian derives it — from what the food
IS. Both guidelines define free/added sugar by food class, and this codebase
already resolves a food to a class for the plausibility bands
(`food_category_service.resolve_band_category`). The rule below is those two
published definitions applied to that existing vocabulary.

**Every food word in this module is quoted from the definitions themselves**
(`honey`, `syrup`, `juice`, `concentrate` — all four appear in WHO's sentence,
and the first three in the FDA's). `test_free_sugars.py` asserts that, so this
cannot quietly become the per-food alias table §3c and §3an forbid.

⚠️ **An unclassifiable food yields UNKNOWN, never zero.** A pizza, a stew or a
baked good contains intrinsic and added sugar together and no authority
publishes the split per dish. `unassessed_g` carries that food's total sugars
as the upper bound on what might also be free, so a day can say "7 g free,
up to 9 g more in 2 items nobody can apportion" instead of claiming 7 g is the
answer. §3aa: unmeasured and zero are opposite facts.
"""

from __future__ import annotations

from dataclasses import dataclass

#: WHO 2015, verbatim. The vocabulary below is quoted FROM this sentence, which
#: is what keeps it a citation rather than a food list of our own.
WHO_FREE_SUGARS_DEFINITION = (
    "Free sugars are monosaccharides and disaccharides added to foods and "
    "beverages by the manufacturer, cook or consumer, and sugars naturally "
    "present in honey, syrups, fruit juices and fruit juice concentrates."
)

#: WHO 2015, the exclusion — the half the old code contradicted.
WHO_INTRINSIC_EXCLUSION = (
    "Free sugars do not include the sugars in fresh fruits and vegetables, "
    "or the sugars naturally present in milk, which are intrinsic sugars."
)

#: FDA 21 CFR 101.9(c)(6)(iii). Quoted because it is why a free-sugars figure
#: may be shown under an "added sugars" label without lying: the FDA's own
#: definition already reaches syrups, honey and juice concentrates, so the two
#: authorities differ materially only on 100% juice.
FDA_ADDED_SUGARS_DEFINITION = (
    "Added sugars are either added during the processing of foods, or are "
    "packaged as such, and include sugars (free, mono- and disaccharides), "
    "sugars from syrups and honey, and sugars from concentrated fruit or "
    "vegetable juices that are in excess of what would be expected from the "
    "same volume of 100 percent fruit or vegetable juice of the same type."
)

#: The FDA Daily Value for ADDED sugars. It is 10% of a 2,000 kcal diet, which
#: is WHO's own strong recommendation expressed as grams — the two figures
#: agree, and that agreement is why one rule can cite both.
FDA_ADDED_SUGARS_DV_G = 50.0

#: The only food words in this module, each one quoted from a definition above.
#: Stems, so "syrups", "juices" and "concentrates" all match. A food that names
#: one of these carries free sugars BY DEFINITION, whatever class it resolves
#: to — which is the case that matters most, because a fruit juice resolves to
#: `fruit_fresh` and the intrinsic rule would otherwise answer zero for a glass
#: of orange juice holding 20.65 g of sugar (a real row on this record).
_WHO_NAMED_FREE_SOURCES: tuple[str, ...] = ("honey", "syrup", "juice", "concentrate")

#: The three classes WHO's exclusion sentence NAMES: fresh fruit, vegetables,
#: milk. Kept apart from the wider set below because for these three a declared
#: ADDED-sugar figure is a contradiction in terms — WHO says their sugars are
#: intrinsic, so a Nutrition Facts panel declaring added sugars means the record
#: is not that food. `scripts/purge_superseded_branded_cache.py` uses exactly
#: this set as proof, and must not use the wider one: a sweetened nut butter or
#: a glazed ham legitimately declares added sugars, and `brioche bread` resolved
#: to `nut_seed` on this database, so the wider set condemned two correct rows
#: on a misclassification rather than on a contradiction.
WHO_NAMED_INTRINSIC: frozenset[str] = frozenset({
    "fruit_fresh", "vegetable", "dairy",
})

#: Classes whose sugars are INTRINSIC, so none of them is free — WHO's three
#: above, plus the classes that carry no sugar worth apportioning (meat, egg,
#: fish, oil, water, plain grains and legumes, plain tea and coffee).
#:
#: `grain_cooked` and `legume_cooked` are here because the band means the plain
#: cooked staple; a sweetened grain dish resolves to `prepared_dish` or
#: `snack_processed`, which are unassessed below.
_INTRINSIC_ONLY: frozenset[str] = frozenset({
    "fruit_fresh", "vegetable", "dairy", "cheese",
    "legume_cooked", "nut_seed", "grain_cooked",
    "egg", "lean_meat", "fatty_meat", "oil_fat",
    "water", "tea_coffee", "condiment",
})

#: Classes that ARE free sugar. `sugar_sweet` is USDA's "Sweets" — sugars,
#: syrups, honey, confectionery — which is WHO's named list as a category.
_ALL_FREE: frozenset[str] = frozenset({"sugar_sweet"})

#: Composites. Both intrinsic and added sugar are present and no authority
#: publishes the split for a dish, so these are reported as unassessed rather
#: than guessed in either direction. Named explicitly instead of falling out of
#: an `else`, so the list of things we cannot answer is reviewable.
_UNASSESSABLE: frozenset[str] = frozenset({
    "bread_baked", "cereal_dry", "snack_processed", "prepared_dish",
    "soup_stew", "beverage", "alcohol", "nutrition_drink", "unknown",
})


@dataclass(frozen=True)
class FreeSugars:
    """One component's free-sugar share, and the evidence it rests on.

    `grams` is None exactly when the rule could not apportion the food. In that
    case `unassessed_g` holds its total sugars — an upper bound, never a value
    to add to a total.
    """

    grams: float | None
    unassessed_g: float
    basis: str
    reason: str

    @property
    def assessed(self) -> bool:
        return self.grams is not None


def _names_a_free_source(food_name: str) -> str | None:
    """The WHO-named free-sugar source this food declares, if any."""
    text = (food_name or "").lower()
    for stem in _WHO_NAMED_FREE_SOURCES:
        if stem in text:
            return stem
    return None


def free_sugars_for(
    *,
    band: str | None,
    total_sugars_g: float | None,
    added_sugars_g: float | None = None,
    food_name: str = "",
) -> FreeSugars:
    """Apportion one food's sugars into free and intrinsic, per WHO and the FDA.

    Evidence is taken in this order, and the order is the design:

    1. **A WHO-named source in the food's own name** — honey, syrup, juice,
       concentrate. This runs FIRST, ahead of both the label and the class,
       because WHO counts the sugars in fruit juice as free while a juice
       resolves to `fruit_fresh` and a 100%-juice label truthfully declares
       ZERO added sugars. Checking either of those first answers "no free
       sugar" for a glass of orange juice, which is the single most wrong
       answer this function could give.
    2. **A label figure.** `added_sugars_g` comes off a Nutrition Facts panel
       and is a declared fact about that product, so it outranks any class
       inference (§ the label outranks the estimate).
    3. **The food's class**, by WHO's intrinsic exclusion.
    4. Otherwise UNKNOWN.
    """
    total = float(total_sugars_g or 0.0)

    # ── 1. the guideline names this food's sugar as free ──────────────────
    named = _names_a_free_source(food_name)
    if named:
        return FreeSugars(
            grams=total, unassessed_g=0.0, basis="who_named_source",
            reason=(f"WHO counts the sugars in {named} as free sugars, so all "
                    f"{total:.1f} g count toward the limit."),
        )

    # ── 2. the label states it ────────────────────────────────────────────
    if added_sugars_g is not None:
        stated = float(added_sugars_g)
        # Added sugars cannot exceed total sugars — a panel figure that does is
        # a basis error, not a measurement. Observed on this record: Boost
        # Glucose Control stores added 4.1616 against total 4.1371. Capped and
        # SAID, because silently keeping the larger number would let a derived
        # free-sugar figure exceed the sugar the food contains.
        if total and stated > total:
            return FreeSugars(
                grams=total, unassessed_g=0.0, basis="label_capped",
                reason=(f"The label declares {stated:.1f} g added sugars, more "
                        f"than the {total:.1f} g of total sugars reported for "
                        f"this food; capped at the total."),
            )
        return FreeSugars(
            grams=stated, unassessed_g=0.0, basis="label",
            reason=(f"The product label declares {stated:.1f} g of added "
                    f"sugars (FDA Nutrition Facts)."),
        )

    # ── 3. the class answers it ───────────────────────────────────────────
    if band in _INTRINSIC_ONLY:
        return FreeSugars(
            grams=0.0, unassessed_g=0.0, basis="who_intrinsic",
            reason=(f"WHO excludes the intrinsic sugars of this food class "
                    f"({band}), so none of its {total:.1f} g is free sugar."),
        )
    if band in _ALL_FREE:
        return FreeSugars(
            grams=total, unassessed_g=0.0, basis="who_class",
            reason=(f"This food class ({band}) is sugars, syrups and "
                    f"confectionery, which WHO counts as free sugar in full."),
        )

    # ── 4. nobody publishes the split for a composite dish ────────────────
    return FreeSugars(
        grams=None, unassessed_g=total, basis="unassessed",
        reason=(f"A composite food ({band or 'unclassified'}) carries intrinsic "
                f"and added sugar together and no guideline apportions it per "
                f"dish; its {total:.1f} g of total sugars is an upper bound on "
                f"what may also be free."),
    )


def who_free_sugar_limit_g(energy_kcal: float, *, diabetes: bool) -> float:
    """WHO's free-sugars ceiling in grams, from the patient's own energy target.

    10% of total energy is the strong recommendation; 5% is the conditional one
    and is what diabetes takes. Sugar carries 4 kcal/g.
    """
    pct = 0.05 if diabetes else 0.10
    return float(energy_kcal) * pct / 4.0
