# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A food lookup must return the food that was named, or nothing.

Measured 2026-10-22: a breakfast of sardines, brioche, two eggs and onion was
stored at **3,090 kcal, 315 g fat, 17 g protein, 2,520 mg cholesterol**,
because "sardines" had been cached since June as USDA fdc 173578 — "Fish oil,
sardine": 902 kcal, 100 g fat, 0 g protein per 100 g. The lexical rule scored
it a perfect 1.0, since every typed word appears in the description. An audit
of all 1,666 cached profiles then found 432 of 934 linked rows matched a
different food (milk -> "Crackers, milk", water melon -> honeydew, cow liver ->
goose liver).

So the model chooses which retrieved record IS the food; the numbers still come
from the record. These tests pin the choice, the fail-closed path, and that an
impossible profile is never cached from any tier.
"""

import pytest
from sqlalchemy import select

from app.models.food_nutrient_cache import FoodNutrientCache
from app.services import food_match_verifier
from app.services import nutrient_estimator as ne
from app.services.food_match_verifier import choose as real_choose

pytestmark = pytest.mark.asyncio

SARDINE_OIL = {"fdc_id": 173578, "description": "Fish oil, sardine", "data_type": "SR Legacy",
               "nutrients": {"calories": 902, "protein_g": 0.0, "fat_g": 100.0, "carbs_g": 0.0}}
SARDINES = {"fdc_id": 175139,
            "description": "Fish, sardine, Atlantic, canned in oil, drained solids with bone",
            "data_type": "SR Legacy",
            "nutrients": {"calories": 208, "protein_g": 24.6, "fat_g": 11.5, "carbs_g": 0.0}}


@pytest.fixture
def real_verifier(monkeypatch):
    """Undo conftest's offline stub and fake only the model's reply."""
    monkeypatch.setattr(food_match_verifier, "choose", real_choose)
    food_match_verifier._memo.clear()
    sent = []

    def reply_with(*answers):
        queue = list(answers)

        async def fake_chat(messages, **kw):
            sent.append(messages[-1]["content"])
            a = queue.pop(0)
            if isinstance(a, Exception):
                raise a
            return a

        monkeypatch.setattr("app.services.alafia_model_service.alafia_chat", fake_chat)

    yield reply_with, sent
    food_match_verifier._memo.clear()


def _search(monkeypatch, rows):
    async def fake_search(q, page_size=5):
        return rows
    monkeypatch.setattr(ne, "search_usda_foods", fake_search, raising=False)
    monkeypatch.setattr("app.core.nutrition_data.search_usda_foods", fake_search)

    async def no_detail(fdc_id):  # sparse rows trigger a detail fetch; stay offline
        return None
    monkeypatch.setattr(ne, "get_usda_food_detail", no_detail, raising=False)


async def test_sardines_resolve_to_the_fish_not_the_oil(monkeypatch, real_verifier):
    """THE REPORTED ROW. Lexically the oil ranks first; the model picks the fish."""
    reply_with, sent = real_verifier
    reply_with('{"choice": 2, "reason": "fish oil is extracted from sardines"}')
    _search(monkeypatch, [SARDINE_OIL, SARDINES])

    best = await ne._try_usda_single("sardines")

    assert best["fdc_id"] == 175139
    assert best["nutrients"]["protein_g"] == 24.6
    # RAG: the model saw the retrieved records AND their numbers.
    assert "Fish oil, sardine" in sent[0] and "kcal 902" in sent[0]


async def test_no_candidate_is_the_food_means_no_usda_answer(monkeypatch, real_verifier):
    reply_with, _ = real_verifier
    reply_with('{"choice": null, "reason": "milk crackers are not milk"}')
    _search(monkeypatch, [{"fdc_id": 1, "description": "Crackers, milk", "data_type": "SR Legacy",
                           "nutrients": {"calories": 446, "protein_g": 7.6, "fat_g": 13.8, "carbs_g": 71.7}}])

    assert await ne._try_usda_single("milk") is None


async def test_an_unavailable_model_fails_closed_and_is_not_remembered(monkeypatch, real_verifier):
    """An unverified match is exactly how sardine oil was cached. It is not
    used — and the outage is not memoised as 'no match' for the process."""
    from app.services.alafia_model_service import ALAFIAModelError
    reply_with, _ = real_verifier
    reply_with(ALAFIAModelError("all providers failed"), '{"choice": 1, "reason": "same food"}')
    _search(monkeypatch, [SARDINES])

    with pytest.raises(ne.SourceUnavailable):
        await ne._try_usda_single("sardines")
    assert (await ne._try_usda_single("sardines"))["fdc_id"] == 175139


@pytest.mark.parametrize("reply", ['{"choice": 7}', "not json", '{"choice": "two"}'])
async def test_an_unreadable_answer_is_no_answer(monkeypatch, real_verifier, reply):
    reply_with, _ = real_verifier
    reply_with(reply)
    _search(monkeypatch, [SARDINES])

    with pytest.raises(ne.SourceUnavailable):
        await ne._try_usda_single("sardines")


async def test_an_outage_is_not_cached_as_an_answer(monkeypatch, db):
    """USDA answered 429 4,157 times in one repair run. `_try_usda_single`
    reported each as "no such food", the AI tier answered, and that answer was
    CACHED — so the food never reached USDA again. An authority that could not
    be asked is not one that said no: the fallback may answer, but is not kept."""
    async def rate_limited(q, page_size=5):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(ne, "search_usda_foods", rate_limited, raising=False)

    async def no_branded(name):
        return None

    async def ai(name, serving=None):
        return {"source": "ai", "fdc_id": None, "ai_model": "m", "food_name": name,
                "serving_size": None, "serving_weight_g": None, "confidence": 0.7,
                "nutrients": {"calories": 208.0, "protein_g": 24.6, "fat_g": 11.5, "carbs_g": 0.0},
                "cached": False}

    monkeypatch.setattr(ne, "_try_mcp_branded", no_branded)
    monkeypatch.setattr(ne, "_try_ai", ai)

    out = await ne._estimate_nutrients_impl(db, "zqvx outage probe")

    assert out["source"] == "ai", "the patient still gets an answer"
    rows = (await db.execute(select(FoodNutrientCache.id).where(
        FoodNutrientCache.food_name_normalized == "zqvx outage probe"))).scalars().all()
    assert rows == [], "an answer given during an outage must not become permanent"


async def test_an_impossible_profile_is_never_cached_from_any_tier(monkeypatch, db):
    """Cached in production by summing densities: "bitter leaf and ogbono with
    fried chicken" at 575 kcal with 22 + 97 + 21 = 141 g of macros per 100 g.
    Whatever tier answers that, it is refused and the next tier runs.

    Chosen because the CATEGORY BAND cannot catch it: an unclassified food's
    band tops out at 900 kcal, and 575 sits inside it. The first version of
    this test used 1,180 kcal, which the band already refused — so it passed
    against the broken code and guarded nothing."""
    impossible = {"source": "usda", "fdc_id": None, "ai_model": None, "food_name": "soup",
                  "serving_size": None, "serving_weight_g": None, "confidence": 1.0,
                  "nutrients": {"calories": 575.0, "protein_g": 22.07, "fat_g": 21.04, "carbs_g": 97.46},
                  "cached": False}
    credible = {"source": "ai", "fdc_id": None, "ai_model": "m", "food_name": "egusi soup",
                "serving_size": None, "serving_weight_g": None, "confidence": 0.7,
                "nutrients": {"calories": 180.0, "protein_g": 9.0, "fat_g": 14.0, "carbs_g": 5.0},
                "cached": False}

    async def usda(name, db=None):
        return dict(impossible)

    async def branded(name):
        return dict(impossible, source="mcp_branded_usda")

    async def ai(name, serving=None):
        return dict(credible)

    monkeypatch.setattr(ne, "_try_usda", usda)
    monkeypatch.setattr(ne, "_try_mcp_branded", branded)
    monkeypatch.setattr(ne, "_try_ai", ai)

    out = await ne._estimate_nutrients_impl(db, "zqvx probe")

    assert out["source"] == "ai" and out["nutrients"]["calories"] == 180.0
    rows = (await db.execute(select(FoodNutrientCache.source).where(
        FoodNutrientCache.food_name_normalized == "zqvx probe"))).scalars().all()
    assert rows == ["ai"], "only the credible answer may reach the shared cache"


async def test_phytate_is_added_from_a_loaded_phyfoodcomp_row(monkeypatch, db):
    """Production, 2026-10-23: KeyError 'biblio' in the phytate step failed
    EVERY estimate with a phytate candidate for four hours. The rows here have
    the shape the loader writes, which the earlier tests never exercised."""
    from app.models.reference_food import ReferenceFood
    db.add(ReferenceFood(source="phyfoodcomp_1_0", code="06000001",
                         name_en="Melon seed, kernel, raw", nutrients={
                             "phytate_mg": 1200.0, "phytate_phosphorus_mg": 337.9},
                         biblio="Nigeria; r; method: HPLC IP6"))
    await db.commit()
    monkeypatch.setattr(ne, "_reference_loaded_at", float("-inf"))

    result = {"food_name": "Melon seed, kernel only, dried, raw", "nutrients": {"calories": 574.0}}
    await ne._add_phytate(db, "egusi", result)   # conftest's verifier picks the top row

    assert result["nutrients"]["phytate_mg"] == 1200.0
    assert result["phytate_source"] == "phyfoodcomp_1_0:06000001"
    monkeypatch.setattr(ne, "_reference_loaded_at", float("-inf"))


async def test_a_failing_phytate_step_never_fails_the_food(monkeypatch, db):
    async def boom(*a, **k):
        raise KeyError("biblio")
    monkeypatch.setattr(ne, "_add_phytate_body", boom)
    result = {"food_name": "x", "nutrients": {"calories": 100.0}}
    await ne._add_phytate(db, "x", result)          # must not raise
    assert result["nutrients"] == {"calories": 100.0}


async def test_a_verified_match_is_not_vetoed_by_the_keyword_band(monkeypatch, db):
    """Production repair, 2026-10-23: "water melon" sits in a 0-5 kcal band
    because it contains the word "water", so the VERIFIED "Watermelon, raw"
    (30 kcal) was refused and never cached — 11 foods stalled this way. A
    record the model matched to the food outranks a band guessed from words."""
    async def usda(name, db=None):
        return {"source": "usda", "fdc_id": 167765, "ai_model": None, "food_name": "Watermelon, raw",
                "serving_size": "100 g", "serving_weight_g": 100.0, "confidence": 1.0,
                "nutrients": {"calories": 30.0, "protein_g": 0.61, "fat_g": 0.15, "carbs_g": 7.55},
                "cached": False}

    async def nothing(*a, **k):
        return None

    monkeypatch.setattr(ne, "_try_usda", usda)
    monkeypatch.setattr(ne, "_try_mcp_branded", nothing)
    monkeypatch.setattr(ne, "_try_ai", nothing)

    out = await ne._estimate_nutrients_impl(db, "water melon")

    assert out["food_name"] == "Watermelon, raw" and not out.get("out_of_band")
    rows = (await db.execute(select(FoodNutrientCache.source).where(
        FoodNutrientCache.food_name_normalized == "water melon"))).scalars().all()
    assert rows == ["usda"]
