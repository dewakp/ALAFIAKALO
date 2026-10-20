# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The expectation a value is judged against must be a FACT, not a figure we typed.

Operator, 2026-10-20, on learning that `tea_coffee` was banded 22-110:

    "Who created this band? is that from FDA or something we made up from our
     model? tea is not coffee and not all tea or coffee are even same thing."
    "FDA lookup checking the first 'tea' is irrational, if there are 100 tea
     lower in rank but number 70 is a better fit. Lookup must be intelligent,
     not first seen."
    "hand written is even worse because it is made up not based on history or
     fact."

All three are correct, and BOTH inputs to the old check were invented:

  * `_CATEGORIES["tea_coffee"]["kcal"] == (0, 15)` — typed by hand. Measured,
    the family spans coffee 1, espresso 9, tea-with-milk 51, bubble tea 55.
  * `reference_kcal * 0.4 .. * 2.0`, then a further `* 1.3 / * 0.5` — four
    multipliers with no source, applied to ONE arbitrarily chosen USDA row.

And the row was chosen by list order. Measured on the live catalog, seven
candidates for "tea" tie at jaccard 0.50 (bubble 55, ginger 1, kombucha 16,
herbal 1, chamomile 1, hibiscus 0, green 1) — "Tea, bubble" won because it
sorted first, so plain tea at 1 kcal/100 g was refused as a wrong match and the
egg and kiwi beside it were discarded with it. "Coffee" ties the same way and
survived only because "Coffee, brewed" happened to sort first.
"""

import pytest

pytestmark = pytest.mark.asyncio


def _hits(*pairs):
    return [{"description": d, "nutrients": {"calories": k}} for d, k in pairs]


async def _range(monkeypatch, db, query, hits):
    from app.services import food_category_service as fcs

    async def fake_search(name, *a, **k):
        return hits

    monkeypatch.setattr("app.core.nutrition_data.search_usda_foods", fake_search)
    return await fcs.reference_energy_range(db, query)


# ── the lookup ────────────────────────────────────────────────────────────

async def test_a_tie_is_not_broken_by_list_order(monkeypatch, db):
    """THE REPORTED BUG. Every one of these ties; the old code took the first."""
    rng = await _range(monkeypatch, db, "tea", _hits(
        ("Tea, bubble", 55), ("Tea, ginger", 1), ("Tea, kombucha", 16),
        ("Tea, hot, herbal", 1), ("Tea, hot, hibiscus", 0),
    ))
    assert rng is not None
    lo, hi = rng
    # The family's own spread, not whichever row sorted first.
    assert lo == 0 and hi == 55


async def test_plain_tea_is_no_longer_refused(monkeypatch, db):
    from app.services import plausibility

    rng = await _range(monkeypatch, db, "tea", _hits(
        ("Tea, bubble", 55), ("Tea, ginger", 1), ("Tea, hot, herbal", 1),
    ))
    _n, warnings, believable = plausibility.review(
        "tea", {"calories": 1.0}, reference_range=rng)
    assert believable is True, warnings


async def test_an_exact_name_outranks_the_family(monkeypatch, db):
    """"Coffee, brewed" for "brewed coffee" is the authority naming this very
    food, not a family — so it is not widened to the family's spread."""
    rng = await _range(monkeypatch, db, "brewed coffee", _hits(
        ("Coffee, brewed", 1), ("Coffee, brewed, decaffeinated", 0),
        ("Coffee, Turkish", 27), ("Coffee, Cuban", 34),
    ))
    # Only the exact entry contributes, and a single point is not a spread —
    # so there is nothing to judge against rather than an invented tolerance.
    assert rng is None


async def test_a_single_candidate_yields_NO_band(monkeypatch, db):
    """A point is not a range. Inventing a tolerance around it is the made-up
    band again in a smaller disguise."""
    rng = await _range(monkeypatch, db, "kombucha", _hits(("Tea, kombucha", 16),))
    assert rng is None


async def test_nothing_matching_yields_no_band(monkeypatch, db):
    rng = await _range(monkeypatch, db, "carton", _hits(("Milk, whole", 61),))
    assert rng is None


# ── what the guard does with it ───────────────────────────────────────────

async def test_no_band_means_NO_energy_rejection(monkeypatch, db):
    """An unchecked value is honest; a value rejected against a number we made
    up is not. This is the whole change."""
    from app.services import plausibility

    _n, _w, believable = plausibility.review(
        "numb earl grey tea", {"calories": 1.0}, reference_range=None)
    assert believable is True


async def test_a_physical_impossibility_is_STILL_refused(monkeypatch, db):
    """The facts survive: nothing edible exceeds pure fat, whatever the
    authority does or does not say about the name."""
    from app.services import plausibility

    _n, warnings, believable = plausibility.review(
        "sardines", {"calories": 997.0}, reference_range=None)
    assert believable is False
    assert any("impossible" in w for w in warnings), warnings


async def test_a_value_outside_the_authority_s_own_spread_is_refused(monkeypatch, db):
    """The guard still bites — it just bites on evidence now."""
    from app.services import plausibility

    rng = await _range(monkeypatch, db, "tea", _hits(
        ("Tea, bubble", 55), ("Tea, ginger", 1), ("Tea, hot, herbal", 1),
    ))
    _n, warnings, believable = plausibility.review(
        "tea", {"calories": 589.0}, reference_range=rng)
    assert believable is False
    assert any("outside 1–55" in w for w in warnings), warnings
