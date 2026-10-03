# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""`Penicilin` must guard against `Penicillin`, without rewriting the profile.

The reference production profile declares, verbatim:

    Penicilin, Latex, Heparine, Raw Apples, Raw Berries

Three of those five are drugs or materials rather than food, and two are
misspelled. `food_safety.violations` compares words, so a dose logged as the
correctly-spelled `Penicillin` did not match `Penicilin` — the guard that exists
to catch exactly that was defeated by one missing letter.

WHY RXNORM PROPOSES AND SIMILARITY ONLY VETOES
==============================================
§3aj is explicit that **string similarity is the wrong instrument for drug
names**: "calcium calcitriol" scores 0.63 against "calcium carbonate" and its
nearest match by ratio is a THIRD drug, "calcium citrate". That rule is about
using similarity to CHOOSE a drug. Here the direction is reversed and that is
the whole design:

    RxNorm chooses the identity.      Similarity only refuses a proposal
                                       that is not a spelling variant.

The refusal half is not optional. Measured live against RxNav on 2026-10-03:

    term           top named candidate       score    verdict
    Penicilin      PENICILLIN (rxcui 7986)   8.75     accept  — distance 1
    Heparine       HEPARIN    (rxcui 5224)   11.73    accept  — distance 1
    Latex          latex   (rxcui 1314891)   12.79    exact   — already matches
    Raw Apples     "raw sugar" (1483267)     12.75    REFUSE  — a different word

**`approximateTerm`'s score is not a spelling-similarity score.** "Raw Apples"
→ "raw sugar" scored HIGHER than the genuine typo fix. Accepting the top
candidate on score alone would map a fruit allergy onto sugar and start warning
this patient off every sweet thing they eat, while still missing the penicillin.

EDIT DISTANCE IS THE GUARD; RATIO IS SECONDARY
==============================================
A ratio threshold alone is not safe. `penicillin` against `penicillamine` — a
chelator, an entirely different drug — scores about 0.87, which clears any
threshold low enough to accept the real typos. Levenshtein separates them
cleanly: every genuine misspelling on this profile is **1** edit away, and that
pair is **3** (measured, not estimated — it was first written here as "four or
more" from arithmetic in someone's head, which is §3av's "run the scan, never
the arithmetic" in a docstring). 3 > MAX_EDITS, so it is refused. So acceptance
requires all of:

    * the same number of words (a typo does not add or drop a word)
    * the same first letter per word (cheap, and blocks whole-word swaps)
    * Levenshtein <= MAX_EDITS per word, scaled down for very short words
    * ratio >= MIN_RATIO as a backstop

NOTHING HERE RUNS ON A WRITE PATH. `resolve_term` makes a network call, so it
belongs to a script or a background task. The write path calls
`stored_aliases()`, which is a single indexed SELECT and never reaches the
network — the §3an "look it up once, remember it after" shape, and the same
reason `get_goal_progress` reads STORED effects only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.allergy_resolution import (
    EXACT,
    REFUSED,
    SPELLING,
    UNKNOWN,
    UNREACHABLE,
    AllergyTermResolution,
)
from app.services.food_safety import _normalise, profile_list

logger = logging.getLogger(__name__)

#: Per-word edit budget. 1 covers every misspelling measured on the real
#: profile; 2 is allowed only for words long enough that two edits cannot turn
#: one drug into another (`penicillin`/`penicillamine` is 4+ and stays refused).
MAX_EDITS = 2
#: Words shorter than this get a budget of 1 — at 4 characters, 2 edits is half
#: the word and "iron" would reach "zinc".
SHORT_WORD = 7
#: Secondary backstop. Deliberately not the primary test: see the docstring.
MIN_RATIO = 0.80


@dataclass(frozen=True)
class Verdict:
    """What RxNorm said about one declared term, and what we did with it."""

    declared_term: str
    declared_sample: str
    verdict: str
    resolved_name: str | None = None
    resolved_term: str | None = None
    rxcui: str | None = None
    refused_reason: str | None = None
    edit_distance: int | None = None
    similarity: float | None = None

    @property
    def gives_alias(self) -> bool:
        return self.verdict == SPELLING and bool(self.resolved_term)


def levenshtein(a: str, b: str) -> int:
    """Edit distance. Written out rather than taking a dependency for 15 lines.

    This is the load-bearing check, so it is exact: a ratio is a similarity
    heuristic, while "how many keystrokes apart are these" is the actual
    question when deciding whether one spelling is a typo of another.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                previous[j] + 1,          # deletion
                current[j - 1] + 1,       # insertion
                previous[j - 1] + (ca != cb),  # substitution
            ))
        previous = current
    return previous[-1]


def _ratio(a: str, b: str) -> float:
    """Longest-match similarity, used only as a backstop."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def is_spelling_variant(declared: str, candidate: str) -> tuple[bool, str, int, float]:
    """Is `candidate` the same word(s) as `declared`, spelled correctly?

    Returns (accepted, reason, total_edit_distance, ratio). The reason is
    recorded on the row whether or not it was accepted — a refusal with no
    stated cause cannot be reviewed, and the refusals are the half of this
    that stops a confident wrong answer.
    """
    d_words = declared.split()
    c_words = candidate.split()
    ratio = _ratio(declared, candidate)

    if not d_words or not c_words:
        return False, "empty after normalisation", 0, ratio
    if len(d_words) != len(c_words):
        return (False,
                f"word count differs ({len(d_words)} vs {len(c_words)}) — a "
                "misspelling does not add or drop a word",
                levenshtein(declared, candidate), ratio)

    total = 0
    for dw, cw in zip(d_words, c_words):
        if dw[0] != cw[0]:
            return (False,
                    f"{dw!r} and {cw!r} start differently — a different word, "
                    "not a misspelling",
                    levenshtein(declared, candidate), ratio)
        budget = 1 if min(len(dw), len(cw)) < SHORT_WORD else MAX_EDITS
        dist = levenshtein(dw, cw)
        if dist > budget:
            return (False,
                    f"{dw!r} is {dist} edits from {cw!r} (budget {budget}) — "
                    "too far to be a typo",
                    levenshtein(declared, candidate), ratio)
        total += dist

    if total == 0:
        return True, "identical after normalisation", 0, ratio
    if ratio < MIN_RATIO:
        return (False, f"ratio {ratio:.2f} below {MIN_RATIO}", total, ratio)
    return True, f"{total} edit(s) apart", total, ratio


async def resolve_term(declared_sample: str) -> Verdict:
    """Ask RxNorm what one declared term is. MAKES A NETWORK CALL.

    Never raises, and never guesses: an unreachable RxNav produces
    `unreachable`, which is re-asked later rather than cached as a refusal.
    """
    term = _normalise(declared_sample)
    if not term:
        return Verdict(declared_term="", declared_sample=declared_sample,
                       verdict=UNKNOWN, refused_reason="nothing left after normalising")

    from app.services import rxnorm

    facts = await rxnorm.lookup(declared_sample)

    if not facts.reachable:
        return Verdict(declared_term=term, declared_sample=declared_sample,
                       verdict=UNREACHABLE,
                       refused_reason="RxNav could not be consulted")

    # RxNorm knew it as typed — but KNOWN does not mean "the only spelling".
    #
    # `Heparine` is a real RxNorm synonym (rxcui 5224) whose canonical name is
    # `heparin`, so without this branch a profile declaring `Heparine` matched
    # only itself and missed a dose logged as `Heparin`: the `Penicilin`
    # failure pointing the other way, and found only by running the resolver
    # against the real profile rather than reasoning about it.
    #
    # The canonical name goes through the SAME veto. An exact match does not
    # earn a free pass to widen what counts as this patient's allergy.
    if facts.known:
        canonical = await rxnorm.canonical_name(facts.rxcui)
        canonical_term = _normalise(canonical or "")
        if canonical_term and canonical_term != term:
            accepted, reason, dist, ratio = is_spelling_variant(term, canonical_term)
            if accepted:
                return Verdict(declared_term=term, declared_sample=declared_sample,
                               verdict=SPELLING, resolved_name=canonical,
                               resolved_term=canonical_term, rxcui=facts.rxcui,
                               refused_reason=reason, edit_distance=dist,
                               similarity=ratio)
            # A canonical name that is a DIFFERENT word is not an alias. Stay
            # EXACT and record why, rather than widening the match: an rxcui
            # can name a combination product or a salt form, and treating that
            # as "the correct spelling" would attach the wrong identity.
            return Verdict(declared_term=term, declared_sample=declared_sample,
                           verdict=EXACT, resolved_name=canonical,
                           rxcui=facts.rxcui, refused_reason=reason,
                           edit_distance=dist, similarity=ratio)
        # Identical, or no name property at all (rxcui 7986 has none). The
        # declared term already matches itself — this is how `Latex` behaves.
        return Verdict(declared_term=term, declared_sample=declared_sample,
                       verdict=EXACT,
                       resolved_name=canonical or declared_sample.strip(),
                       rxcui=facts.rxcui, refused_reason=None)

    if not facts.suggestion:
        return Verdict(declared_term=term, declared_sample=declared_sample,
                       verdict=UNKNOWN,
                       refused_reason="RxNorm offered no named candidate")

    resolved_term = _normalise(facts.suggestion)
    accepted, reason, dist, ratio = is_spelling_variant(term, resolved_term)
    if not accepted:
        return Verdict(declared_term=term, declared_sample=declared_sample,
                       verdict=REFUSED, resolved_name=facts.suggestion,
                       resolved_term=resolved_term, refused_reason=reason,
                       edit_distance=dist, similarity=ratio)

    return Verdict(declared_term=term, declared_sample=declared_sample,
                   verdict=SPELLING, resolved_name=facts.suggestion,
                   resolved_term=resolved_term, refused_reason=reason,
                   edit_distance=dist, similarity=ratio)


async def persist(db: AsyncSession, verdict: Verdict) -> AllergyTermResolution | None:
    """Store a verdict, sharpening an existing row rather than inserting beside it.

    §3ab: re-resolution must SHARPEN. An `unreachable` never overwrites a real
    answer — a third-party outage must not erase what we already knew.
    """
    if not verdict.declared_term:
        return None
    row = (await db.execute(
        select(AllergyTermResolution).where(
            AllergyTermResolution.declared_term == verdict.declared_term)
    )).scalar_one_or_none()

    if row is None:
        row = AllergyTermResolution(
            declared_term=verdict.declared_term,
            declared_sample=verdict.declared_sample[:200],
            resolved_name=verdict.resolved_name,
            resolved_term=verdict.resolved_term,
            rxcui=verdict.rxcui,
            verdict=verdict.verdict,
            refused_reason=verdict.refused_reason,
            edit_distance=verdict.edit_distance,
            similarity=verdict.similarity,
        )
        db.add(row)
        await db.flush()
        return row

    if verdict.verdict == UNREACHABLE:
        # Keep what we had. Unreachable is not a new fact.
        return row
    if row.verdict == verdict.verdict:
        row.times_confirmed = (row.times_confirmed or 1) + 1
    row.verdict = verdict.verdict
    row.resolved_name = verdict.resolved_name
    row.resolved_term = verdict.resolved_term
    row.rxcui = verdict.rxcui
    row.refused_reason = verdict.refused_reason
    row.edit_distance = verdict.edit_distance
    row.similarity = verdict.similarity
    await db.flush()
    return row


async def stored_aliases(db: AsyncSession, declared: list[str]) -> dict[str, str]:
    """{normalised declared term -> extra term to ALSO match on}.

    One indexed SELECT, no network. This is what a write path calls.
    """
    terms = {_normalise(d) for d in declared if d}
    terms.discard("")
    if not terms:
        return {}
    rows = (await db.execute(
        select(AllergyTermResolution).where(
            AllergyTermResolution.declared_term.in_(terms),
            AllergyTermResolution.is_active.is_(True),
            AllergyTermResolution.verdict == SPELLING,
        )
    )).scalars().all()
    return {r.declared_term: r.resolved_term for r in rows if r.resolved_term}


async def aliases_for_user(db: AsyncSession, user) -> dict[str, str]:
    """Every alias that applies to this patient's declared profile."""
    declared = (profile_list(getattr(user, "allergies", None))
                + profile_list(getattr(user, "food_intolerances", None)))
    if not declared:
        return {}
    return await stored_aliases(db, declared)


async def resolve_for_user_id(user_id: int) -> None:
    """Background entry point — resolve one patient's declared terms.

    Opens its OWN session, because the request's is closed by the time a
    FastAPI BackgroundTask runs (§3c, the same rule nutrient enrichment
    follows), and never raises: a profile save must not fail, or even look
    slow, because RxNav was unreachable.
    """
    try:
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            user = (await db.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()
            if user is None:
                return
            if await resolve_for_user(db, user):
                await db.commit()
    except Exception:
        logger.exception("background allergy resolution failed for user %s", user_id)


async def resolve_for_user(db: AsyncSession, user) -> list[Verdict]:
    """Resolve anything about this patient's profile we have not resolved yet.

    MAKES NETWORK CALLS — for a background task or a script, never a request.
    Terms already carrying a non-`unreachable` verdict are skipped, so this is
    cheap to run repeatedly and costs nothing once a profile has settled.
    """
    declared = (profile_list(getattr(user, "allergies", None))
                + profile_list(getattr(user, "food_intolerances", None)))
    if not declared:
        return []

    known = {
        r.declared_term
        for r in (await db.execute(
            select(AllergyTermResolution).where(
                AllergyTermResolution.declared_term.in_(
                    [t for t in {_normalise(d) for d in declared} if t]),
                AllergyTermResolution.verdict != UNREACHABLE,
            )
        )).scalars().all()
    }

    out: list[Verdict] = []
    for item in declared:
        term = _normalise(item)
        if not term or term in known:
            continue
        known.add(term)
        try:
            verdict = await resolve_term(item)
            await persist(db, verdict)
            out.append(verdict)
            logger.info("allergy term %r -> %s (%s)", item, verdict.verdict,
                        verdict.resolved_name or verdict.refused_reason)
        except Exception:
            logger.exception("could not resolve allergy term %r", item)
    return out
