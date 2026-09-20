"""Seed the literature priors that already exist in code into `nutrient_effects`.

This is a MIGRATION of behaviour, not a new set of facts, and the distinction is
the whole point: every figure written here is READ from the constant that
already governs it in `dialysis_balance`, never retyped. One source for the
number means the store cannot silently disagree with the model it replaces, and
a test can assert the two produce identical results on real sessions.

Protein is the first and most important case. Its coefficient row is

    Coefficients(saturation=0.0, sieving=0.0, diffusible_fraction=0.0,
                 grams_per_session=9.0)

— every physics parameter zeroed to switch the physics OFF, with a flat
per-session constant bolted on because the gradient model was the only place to
put it. That is a rate-driven effect wearing a gradient model's dataclass, and
it is why adding it once cost a `GOAL_KEY` entry, a bespoke `elif analyte ==
PROTEIN`, and an inline `scale = 0.001 if key == "protein_g"` unit hack.

Dialysate GAINS are deliberately NOT seeded here. Bath calcium and magnesium
are genuine gradient transfers — they depend on the serum concentration and the
bath concentration, and `dialysis_balance` computes them properly. Copying them
into a rate-driven store would be wrong twice over: the magnitude is not a
constant, and it would then be applied twice.

Usage (dev):
    docker compose --profile test run --rm \
      -e DATABASE_URL=postgresql+asyncpg://alafia:alafia@db:5432/alafia \
      backend-test python scripts/seed_nutrient_effects.py
"""

import asyncio
import logging
import sys

from sqlalchemy import select

from app.core.database import async_session
from app.models.nutrient_effect import (
    AGENT_TREATMENT, PER_SESSION, REMOVES, NutrientEffect,
)
from app.services.dialysis_balance import (
    DEFAULT_COEFFICIENTS, PROTEIN,
    _BLOOD_VOLUME_RATIO_BOUNDS, _REFERENCE_BLOOD_VOLUME_L,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed_nutrient_effects")

#: The clamp `estimate_session_removal` applies to the throughput ratio, read
#: from the model rather than retyped — one source, so the store cannot quietly
#: disagree with the thing it mirrors. That disagreement is not hypothetical:
#: when the model moved from dialysate volume to blood volume, the equivalence
#: test failed all five parametrisations because this constant had not.
_SCALE_MIN, _SCALE_MAX = _BLOOD_VOLUME_RATIO_BOUNDS

#: Which therapy types this prior describes. `TherapyType` carries eleven
#: members and the balance model knows one — that gap is what the resolver is
#: for, and seeding must not paper over it by claiming coverage it lacks.
_HEMODIALYSIS_KEYS = ("hemodialysis",)


async def seed() -> int:
    """Write the priors, converging on any row already present. Returns writes."""
    coeff = DEFAULT_COEFFICIENTS[PROTEIN]
    if not coeff.grams_per_session:
        logger.error("protein prior has no grams_per_session — nothing to seed")
        return 0

    written = 0
    async with async_session() as db:
        for agent_key in _HEMODIALYSIS_KEYS:
            existing = (await db.execute(
                select(NutrientEffect).where(
                    NutrientEffect.agent_kind == AGENT_TREATMENT,
                    NutrientEffect.agent_key == agent_key,
                    NutrientEffect.nutrient_key == "protein_g",
                    NutrientEffect.direction == REMOVES,
                )
            )).scalar_one_or_none()

            if existing is not None:
                # Converge, never duplicate (§3ab). A re-run must be a no-op.
                existing.magnitude = coeff.grams_per_session
                existing.scales_with = "blood_volume_processed_l"
                existing.scale_reference = _REFERENCE_BLOOD_VOLUME_L
                existing.scale_min, existing.scale_max = _SCALE_MIN, _SCALE_MAX
                existing.is_active = True
                logger.info("protein_g for %s already present — refreshed", agent_key)
            else:
                db.add(NutrientEffect(
                    agent_kind=AGENT_TREATMENT,
                    agent_key=agent_key,
                    agent_label="Hemodialysis",
                    agent_code="hemodialysis",
                    nutrient_key="protein_g",
                    direction=REMOVES,
                    magnitude=coeff.grams_per_session,
                    magnitude_unit="g",
                    basis=PER_SESSION,
                    # Amino acids leave with what passed through the filter.
                    # This was dialysate volume until the flowsheet import loss
                    # was recovered — and dialysate is 30 L on nearly every home
                    # session, so scaling on it made the figure a constant.
                    scales_with="blood_volume_processed_l",
                    scale_reference=_REFERENCE_BLOOD_VOLUME_L,
                    scale_min=_SCALE_MIN,
                    scale_max=_SCALE_MAX,
                    mechanism=(
                        "Free amino acids cross the membrane and leave in the "
                        "effluent, so less of the day's protein is retained."
                    ),
                    rationale=(
                        "The basis for the raised protein target on dialysis "
                        "(KDOQI ~1.0-1.2 g/kg/day)."
                    ),
                    evidence_level="high",
                    source="KDOQI 2020 nutrition guidance; dialysis kinetics literature",
                    # NOT "llm": this figure has a citation and predates the
                    # resolver. Provenance that cannot be audited is worthless.
                    provenance="literature_prior",
                    confidence=0.8,
                    # Lowering a TARGET tells the patient to eat more — the safe
                    # direction, which is exactly why protein loss is ungated in
                    # the model this migrates.
                    requires_measurement=False,
                ))
                written += 1
                logger.info(
                    "seeded protein_g for %s: %.1f g/session, scaled by "
                    "blood volume processed against %.0f L, clamped %.2f-%.1fx",
                    agent_key, coeff.grams_per_session, _REFERENCE_BLOOD_VOLUME_L,
                    _SCALE_MIN, _SCALE_MAX,
                )

        await db.commit()
    return written


async def main() -> None:
    written = await seed()
    logger.info("done: %d new effect(s)", written)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001
        logger.error("seeding failed: %s", exc, exc_info=True)
        sys.exit(1)
