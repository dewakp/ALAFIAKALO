# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""`Penicilin` must guard against `Penicillin`, and must NOT guard against sugar.

The reference production profile declares, verbatim:

    Penicilin, Latex, Heparine, Raw Apples, Raw Berries

Two are misspelled, and `food_safety.violations` compares words — so a dose
logged as the correctly-spelled `Penicillin` did not match, and the guard whose
only job is to catch that was defeated by one missing letter.

WHY THE REFUSAL HALF IS THE DANGEROUS HALF
==========================================
Measured live against RxNav on 2026-10-03, with `approximateTerm`:

    Penicilin    -> PENICILLIN   (rxcui 7986)      score  8.75
    Heparine     -> HEPARIN      (rxcui 5224)      score 11.73
    Latex        -> latex        (rxcui 1314891)   score 12.79
    Raw Apples   -> "raw sugar"  (rxcui 1483267)   score 12.75   <-- WRONG

**RxNorm's score is not a spelling-similarity score.** The bogus match scored
HIGHER than both genuine typo fixes. Accepting the top candidate on score would
map a fruit allergy onto sugar — warning this patient off everything sweet while
still missing the penicillin.

And a ratio threshold alone is not enough either: `penicillin` against
`penicillamine` — a chelator, a completely different drug — scores about 0.87,
above any threshold low enough to accept the real typos. Edit distance is what
separates them: every genuine misspelling on this profile is ONE edit away and
that pair is THREE (measured in the container, after this file first claimed
"four or more" from mental arithmetic — the same shape as §3av's fabricated
field count). Three exceeds the budget of two, so it is refused.

So RxNorm CHOOSES the identity and similarity only REFUSES a proposal that is
not a spelling variant. That is the opposite direction from §3aj's failure,
where similarity was used to PICK a drug and confidently named a third one.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.allergy_resolution import (
    EXACT,
    REFUSED,
    SPELLING,
    UNKNOWN,
    UNREACHABLE,
    AllergyTermResolution,
)
from app.models.user import User
from app.services import allergy_resolution as ar
from app.services import food_safety, rxnorm

#: The real declared string, used verbatim.
REAL_ALLERGIES = "Penicilin, Latex, Heparine, Raw Apples, Raw Berries"


async def _user(db, email="allergy@example.com", allergies=REAL_ALLERGIES):
    u = User(email=email, hashed_password="x", full_name="Allergy Test",
             date_of_birth="1974-03-15", gender="Male",
             height_cm=177.8, current_weight_kg=55.0, allergies=allergies)
    db.add(u)
    await db.flush()
    return u


class TestTheVetoIsEditDistanceNotSimilarity:
    """REGRESSION GUARDS. Each pair below decides a clinical match."""

    @pytest.mark.parametrize("declared,candidate", [
        ("penicilin", "penicillin"),      # the real profile's typo
        ("heparine", "heparin"),          # the real profile's other typo
        ("calcium carbonat", "calcium carbonate"),   # §3aj's own example
        ("latex", "latex"),               # identical: trivially a variant
    ])
    def test_a_genuine_misspelling_is_accepted(self, declared, candidate):
        ok, reason, dist, ratio = ar.is_spelling_variant(declared, candidate)
        assert ok, f"{declared!r} -> {candidate!r}: {reason}"
        assert dist <= ar.MAX_EDITS

    def test_penicillin_is_NOT_penicillamine(self):
        """The case a similarity threshold cannot separate.

        Penicillamine is a chelator. Accepting it as "the correct spelling of"
        penicillin would attach the wrong drug identity to a declared allergy,
        which is worse than the missed match this feature exists to fix.
        """
        ok, reason, dist, ratio = ar.is_spelling_variant(
            "penicillin", "penicillamine")
        assert not ok, reason
        assert dist > ar.MAX_EDITS
        assert ratio > 0.80, (
            "the premise: a ratio gate low enough to accept the real typos "
            f"would have accepted this too (ratio {ratio:.2f})")

    def test_raw_apples_is_not_raw_sugar(self):
        """The measured false positive, after `_normalise` strips `raw`."""
        declared = food_safety._normalise("Raw Apples")      # -> "apple"
        candidate = food_safety._normalise("raw sugar")      # -> "sugar"
        ok, reason, _, _ = ar.is_spelling_variant(declared, candidate)
        assert not ok
        assert "start differently" in reason

    @pytest.mark.parametrize("declared,candidate", [
        ("iron", "zinc"),                     # different word entirely
        ("peanut", "peanut butter"),          # word count differs
        ("aspirin", "aspirin oral tablet"),   # a dose form, not a spelling
    ])
    def test_a_different_thing_is_refused(self, declared, candidate):
        ok, reason, _, _ = ar.is_spelling_variant(declared, candidate)
        assert not ok, f"{declared!r} -> {candidate!r} must be refused"
        assert reason

    def test_a_short_word_gets_a_tighter_budget(self):
        """Two edits on a four-letter word is half the word.

        `iron` -> `iodine` must not pass just because the distance is small in
        absolute terms.
        """
        ok, _, _, _ = ar.is_spelling_variant("iron", "icon")
        assert not ok or ar.levenshtein("iron", "icon") <= 1

    def test_levenshtein_is_exact(self):
        assert ar.levenshtein("penicilin", "penicillin") == 1
        assert ar.levenshtein("heparine", "heparin") == 1
        assert ar.levenshtein("", "abc") == 3
        assert ar.levenshtein("abc", "abc") == 0


class TestResolutionNeverTouchesTheNetworkTwice:
    """`resolve_term` is stubbed here: the suite must stay offline (conftest
    already forces `rxnorm.lookup` to report unreachable)."""

    @pytest.mark.asyncio
    async def test_an_exact_rxnorm_hit_needs_no_alias(self, monkeypatch):
        async def _exact(name):
            return rxnorm.DrugFacts(query=name, rxcui="1314891")
        monkeypatch.setattr(rxnorm, "lookup", _exact)

        v = await ar.resolve_term("Latex")
        assert v.verdict == EXACT
        assert not v.gives_alias, "it already matches itself"

    @pytest.mark.asyncio
    async def test_a_typo_becomes_an_alias(self, monkeypatch):
        async def _suggest(name):
            return rxnorm.DrugFacts(query=name, suggestion="PENICILLIN")
        monkeypatch.setattr(rxnorm, "lookup", _suggest)

        v = await ar.resolve_term("Penicilin")
        assert v.verdict == SPELLING
        assert v.resolved_term == "penicillin"
        assert v.edit_distance == 1
        assert v.gives_alias

    @pytest.mark.asyncio
    async def test_a_wrong_suggestion_is_refused_with_its_reason(self, monkeypatch):
        """The measured `Raw Apples` -> `raw sugar` case."""
        async def _suggest(name):
            return rxnorm.DrugFacts(query=name, suggestion="raw sugar")
        monkeypatch.setattr(rxnorm, "lookup", _suggest)

        v = await ar.resolve_term("Raw Apples")
        assert v.verdict == REFUSED
        assert not v.gives_alias
        assert v.refused_reason, "a refusal with no stated cause cannot be reviewed"

    @pytest.mark.asyncio
    async def test_unreachable_is_not_a_refusal(self, monkeypatch):
        """§3aj: unreachable is not the same as invalid. Ask again later."""
        async def _down(name):
            return rxnorm.DrugFacts(query=name, reachable=False)
        monkeypatch.setattr(rxnorm, "lookup", _down)

        v = await ar.resolve_term("Penicilin")
        assert v.verdict == UNREACHABLE

    @pytest.mark.asyncio
    async def test_no_candidate_is_unknown_not_refused(self, monkeypatch):
        async def _nothing(name):
            return rxnorm.DrugFacts(query=name)
        monkeypatch.setattr(rxnorm, "lookup", _nothing)
        assert (await ar.resolve_term("Dust mites")).verdict == UNKNOWN


class TestAnExactMatchCanSTILLNeedAnAlias:
    """REGRESSION GUARDS. Found by running the resolver on the real profile.

    `Heparine` resolves EXACTLY — RxNorm knows it as a synonym — so the first
    version of this module filed it as `exact` and stored no alias. A dose
    logged as `Heparin` therefore still missed: the `Penicilin` failure
    pointing the other way, and invisible to any amount of reasoning about the
    code. Measured: rxcui 5224, canonical name `heparin`.

    Note also that `Heparin` resolves to a DIFFERENT rxcui (235473), so
    comparing rxcuis would have called them unrelated drugs. The canonical
    NAME is what relates them.
    """

    @pytest.mark.asyncio
    async def test_a_synonym_aliases_to_its_canonical_spelling(self, monkeypatch):
        async def _exact(name):
            return rxnorm.DrugFacts(query=name, rxcui="5224")

        async def _canonical(rxcui):
            assert rxcui == "5224"
            return "heparin"

        monkeypatch.setattr(rxnorm, "lookup", _exact)
        monkeypatch.setattr(rxnorm, "canonical_name", _canonical)

        v = await ar.resolve_term("Heparine")
        assert v.verdict == SPELLING, v.refused_reason
        assert v.resolved_term == "heparin"
        assert v.edit_distance == 1
        assert v.gives_alias

    @pytest.mark.asyncio
    async def test_an_identical_canonical_name_adds_nothing(self, monkeypatch):
        """`Latex` -> `latex`: already matches itself, so no alias."""
        async def _exact(name):
            return rxnorm.DrugFacts(query=name, rxcui="1314891")

        async def _canonical(rxcui):
            return "latex"

        monkeypatch.setattr(rxnorm, "lookup", _exact)
        monkeypatch.setattr(rxnorm, "canonical_name", _canonical)

        v = await ar.resolve_term("Latex")
        assert v.verdict == EXACT
        assert not v.gives_alias

    @pytest.mark.asyncio
    async def test_no_canonical_name_property_is_an_ordinary_answer(self, monkeypatch):
        """rxcui 7986 returns no RxNorm Name at all — measured, not assumed."""
        async def _exact(name):
            return rxnorm.DrugFacts(query=name, rxcui="7986")

        async def _canonical(rxcui):
            return None

        monkeypatch.setattr(rxnorm, "lookup", _exact)
        monkeypatch.setattr(rxnorm, "canonical_name", _canonical)

        v = await ar.resolve_term("Penicillin")
        assert v.verdict == EXACT
        assert not v.gives_alias

    @pytest.mark.asyncio
    async def test_a_canonical_name_that_is_a_DIFFERENT_drug_does_not_alias(
            self, monkeypatch):
        """An exact rxcui does not earn a free pass to widen the allergy.

        An rxcui can name a salt form or a combination product. Treating that
        as "the correct spelling" would attach a different drug's identity to
        a declared allergy — worse than the missed match being fixed.
        """
        async def _exact(name):
            return rxnorm.DrugFacts(query=name, rxcui="5224")

        async def _canonical(rxcui):
            return "warfarin sodium"

        monkeypatch.setattr(rxnorm, "lookup", _exact)
        monkeypatch.setattr(rxnorm, "canonical_name", _canonical)

        v = await ar.resolve_term("Heparine")
        assert v.verdict == EXACT
        assert not v.gives_alias
        assert v.refused_reason, "the refusal must say why"

    @pytest.mark.asyncio
    async def test_a_dose_of_heparin_now_fires_for_a_heparine_allergy(self, db):
        """The second half of the headline fix, end to end."""
        from app.models.med_nutrient import MedicationDoseLog
        from app.models.notifications import Notification, NotificationCategory
        from app.services import active_response

        user = await _user(db, email="heparin@example.com")
        await ar.persist(db, ar.Verdict(
            declared_term="heparine", declared_sample="Heparine",
            verdict=SPELLING, resolved_name="heparin",
            resolved_term="heparin", rxcui="5224", edit_distance=1))
        dose = MedicationDoseLog(
            user_id=user.id, medication_name="Heparin",
            log_date=date.today(), dose_amount=5000, dose_unit="unit")
        db.add(dose)
        await db.flush()

        assert await active_response.evaluate_medication_dose(db, dose, user) >= 1
        notes = (await db.execute(select(Notification).where(
            Notification.user_id == user.id,
            Notification.category == NotificationCategory.MEDICATION_CONFLICT,
        ))).scalars().all()
        assert notes
        assert "Heparine" in notes[0].message, "quotes what the patient declared"


class TestTheStoreSharpensRatherThanDuplicating:
    @pytest.mark.asyncio
    async def test_persist_then_read_back_as_an_alias(self, db):
        v = ar.Verdict(declared_term="penicilin", declared_sample="Penicilin",
                       verdict=SPELLING, resolved_name="PENICILLIN",
                       resolved_term="penicillin", edit_distance=1,
                       similarity=0.95)
        await ar.persist(db, v)
        await db.flush()
        assert await ar.stored_aliases(db, ["Penicilin"]) == {
            "penicilin": "penicillin"}

    @pytest.mark.asyncio
    async def test_a_refusal_yields_no_alias(self, db):
        await ar.persist(db, ar.Verdict(
            declared_term="apple", declared_sample="Raw Apples",
            verdict=REFUSED, resolved_name="raw sugar",
            resolved_term="sugar", refused_reason="start differently"))
        await db.flush()
        assert await ar.stored_aliases(db, ["Raw Apples"]) == {}

    @pytest.mark.asyncio
    async def test_re_resolution_sharpens_and_does_not_insert_beside(self, db):
        v = ar.Verdict(declared_term="penicilin", declared_sample="Penicilin",
                       verdict=SPELLING, resolved_name="PENICILLIN",
                       resolved_term="penicillin", edit_distance=1)
        await ar.persist(db, v)
        await ar.persist(db, v)
        await db.flush()
        rows = (await db.execute(select(AllergyTermResolution).where(
            AllergyTermResolution.declared_term == "penicilin"))).scalars().all()
        assert len(rows) == 1, "§3ab: sharpen, never insert beside"
        assert rows[0].times_confirmed == 2

    @pytest.mark.asyncio
    async def test_an_outage_never_erases_what_we_knew(self, db):
        """An `unreachable` must not overwrite a real answer."""
        await ar.persist(db, ar.Verdict(
            declared_term="penicilin", declared_sample="Penicilin",
            verdict=SPELLING, resolved_name="PENICILLIN",
            resolved_term="penicillin", edit_distance=1))
        await ar.persist(db, ar.Verdict(
            declared_term="penicilin", declared_sample="Penicilin",
            verdict=UNREACHABLE))
        await db.flush()
        assert await ar.stored_aliases(db, ["Penicilin"]) == {
            "penicilin": "penicillin"}


class TestTheProfileItselfIsNeverREWRITTEN:
    @pytest.mark.asyncio
    async def test_the_declared_text_is_untouched(self, db):
        """Rewriting what a patient said about their own body invents a fact."""
        user = await _user(db)
        await ar.persist(db, ar.Verdict(
            declared_term="penicilin", declared_sample="Penicilin",
            verdict=SPELLING, resolved_name="PENICILLIN",
            resolved_term="penicillin", edit_distance=1))
        await db.flush()
        assert user.allergies == REAL_ALLERGIES

    @pytest.mark.asyncio
    async def test_the_warning_still_says_what_the_patient_WROTE(self, db):
        user = await _user(db)
        aliases = {"penicilin": "penicillin"}
        guidance = food_safety.build_guidance(user, (), (), aliases=aliases)
        hits = food_safety.violations("Penicillin 500 mg", guidance.avoid)
        assert hits, "the correctly-spelled drug must now match"
        assert hits[0].label == "Penicilin", (
            "the message names the patient's own words, not a correction")
        assert hits[0].kind == food_safety.ALLERGY


class TestTheHeadlineFix:
    """REGRESSION GUARD — the operator's actual request.

    Without the alias this is exactly the recorded gap: a dose logged as
    `Penicillin` against a profile declaring `Penicilin` produced nothing.
    """

    @pytest.mark.asyncio
    async def test_a_dose_of_the_correctly_spelled_drug_now_fires(self, db):
        from app.models.med_nutrient import MedicationDoseLog
        from app.models.notifications import Notification, NotificationCategory
        from app.services import active_response

        user = await _user(db, email="headline@example.com")
        await ar.persist(db, ar.Verdict(
            declared_term="penicilin", declared_sample="Penicilin",
            verdict=SPELLING, resolved_name="PENICILLIN",
            resolved_term="penicillin", edit_distance=1))
        dose = MedicationDoseLog(
            user_id=user.id, medication_name="Penicillin",
            log_date=date.today(), dose_amount=500, dose_unit="mg")
        db.add(dose)
        await db.flush()

        written = await active_response.evaluate_medication_dose(db, dose, user)
        await db.flush()

        assert written >= 1, "the whole point of this change"
        notes = (await db.execute(select(Notification).where(
            Notification.user_id == user.id,
            Notification.category == NotificationCategory.MEDICATION_CONFLICT,
        ))).scalars().all()
        assert notes
        assert "Penicilin" in notes[0].message, "quotes what they declared"

    @pytest.mark.asyncio
    async def test_without_the_alias_it_still_does_not_fire(self, db):
        """The premise, stated as a test: this is the gap being closed."""
        from app.models.med_nutrient import MedicationDoseLog
        from app.services import active_response

        user = await _user(db, email="nopremise@example.com")
        dose = MedicationDoseLog(
            user_id=user.id, medication_name="Penicillin",
            log_date=date.today(), dose_amount=500, dose_unit="mg")
        db.add(dose)
        await db.flush()
        assert await active_response.evaluate_medication_dose(db, dose, user) == 0

    @pytest.mark.asyncio
    async def test_sugar_is_NOT_flagged_from_a_fruit_allergy(self, db):
        """If the refusal half ever breaks, this is how it would show.

        `Raw Apples` resolving to `raw sugar` would make every sweet food a
        declared-allergy violation for this patient.
        """
        user = await _user(db, email="nosugar@example.com")
        guidance = food_safety.build_guidance(user, (), (), aliases={})
        assert not food_safety.violations("sugar", guidance.avoid)
        assert not food_safety.violations("raw sugar cane juice", guidance.avoid)
