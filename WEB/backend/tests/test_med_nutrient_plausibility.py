"""Medication-derived nutrients must be attributable and physiologically possible.

Both guards here exist because of one production row. On 2026-08-17 a dose
logged as "Calcium Calcitriol, 1000 mg" resolved to the *Calcitriol* profile —
vitamin D, canonical unit mcg — and contributed 40,000,000 IU of vitamin D to
that day's total, which the app displayed as 40,000,041 IU.

Two independent failures had to line up:
  1. the name matched two profiles equally and the scan order decided it;
  2. nothing checked whether the resulting amount was possible.
"""

import pytest

from app.services.med_nutrient_service import (
    MAX_NUTRIENT_PER_DOSE,
    implausible_nutrients,
    lookup_med_nutrients,
    seed_med_profiles,
    unit_convert_factor,
)


class TestPlausibilityBounds:
    def test_flags_an_impossible_vitamin_d_amount(self):
        # The exact amount produced by the production row.
        assert implausible_nutrients({"vitamin_d_iu": 40_000_000.0}) == {
            "vitamin_d_iu": 40_000_000.0
        }

    def test_allows_a_real_therapeutic_megadose(self):
        # Ergocalciferol is genuinely prescribed at 50,000 IU weekly; a bound
        # that rejected it would be a bound clinicians route around.
        assert implausible_nutrients({"vitamin_d_iu": 50_000.0}) == {}

    def test_allows_an_ordinary_dose(self):
        # 1 mcg calcitriol → 40 IU.
        assert implausible_nutrients({"vitamin_d_iu": 40.0}) == {}

    def test_ignores_nutrients_without_a_bound(self):
        assert implausible_nutrients({"some_future_nutrient": 1e9}) == {}

    def test_every_bound_is_positive(self):
        assert all(v > 0 for v in MAX_NUTRIENT_PER_DOSE.values())


class TestUnitConversion:
    def test_mg_to_mcg_is_a_thousandfold(self):
        # The multiplier that turned 1000 mg into 1,000,000 mcg. Correct in
        # itself — the bug was applying it to the wrong medication unchecked.
        assert unit_convert_factor("mg", "mcg") == 1000.0

    def test_mcg_to_iu_for_vitamin_d(self):
        assert unit_convert_factor("mcg", "IU") == 40.0


@pytest.mark.asyncio
class TestLookupGuards:
    async def test_ambiguous_name_is_not_silently_resolved(self, db):
        """'Calcium Calcitriol' names two ingredients — refuse to pick one."""
        await seed_med_profiles(db)

        result = await lookup_med_nutrients(db, "Calcium Calcitriol", 1000, "mg")

        assert result["nutrients"] == {}
        assert result["source"] == "ambiguous"
        assert result["profile_id"] is None
        assert "more than one medication" in result["warning"]

    async def test_ambiguous_name_does_not_produce_vitamin_d(self, db):
        """The regression itself: this row must never yield 40,000,000 IU."""
        await seed_med_profiles(db)

        result = await lookup_med_nutrients(db, "Calcium Calcitriol", 1000, "mg")

        assert "vitamin_d_iu" not in result["nutrients"]

    async def test_unambiguous_name_still_resolves(self, db):
        await seed_med_profiles(db)

        result = await lookup_med_nutrients(db, "Calcitriol", 1, "mcg")

        assert result["nutrients"]["vitamin_d_iu"] == 40.0
        assert result["source"] != "ambiguous"

    async def test_wrong_unit_magnitude_is_rejected_not_recorded(self, db):
        """Calcitriol is dosed in mcg; 1 mg of it is a thousandfold error."""
        await seed_med_profiles(db)

        result = await lookup_med_nutrients(db, "Calcitriol", 1, "mg")

        assert result["nutrients"] == {}
        assert result["source"] == "implausible"
        assert "dosed in mcg" in result["warning"]
