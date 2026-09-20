"""Resolve what every agent in the record does to nutrient totals.

The sweep that makes `nutrient_effects` cover the patient's actual record rather
than the one agent somebody seeded by hand. It asks the knowledge tier about
each distinct treatment and medication the database holds, and stores the answer
so the nutrition page can serve it without an LLM call on the request path.

WHY THIS IS A SCRIPT AND NOT PART OF THE REQUEST
------------------------------------------------
`resolve_agent_effects` is a model call — measured at ~57 s in dev (§3am) and
several seconds even on the production provider order. Putting one inside
`/nutrition/goal-progress` would be §3ae's timeout failure by construction, and
would re-ask the same question for every patient on a drug. The store is shared,
so the answer is worth computing once for everyone.

WHAT IT REFUSES TO DO
---------------------
It never invents an agent. The sweep reads what the record actually contains:
`therapy_sessions.therapy_type`, `medication_dose_logs.medication_name`, and the
drugs the unit administered in `therapy_sessions.drugs_administered` — the third
medication source (§3aa), which is where Venofer, Epogene and Doxercalciferol
live and where none of them had ever reached nutrient tracking.

An agent that already has a stored effect is SKIPPED, not re-asked. Re-resolution
sharpens a row rather than duplicating it (§3ab), but spending a model call to
re-derive a literature prior we already hold is waste, and the seeded protein row
carries a citation that a model answer would overwrite with something weaker.

Usage (dev) — dry run first, it is the default:
    docker compose --profile test run --rm \
      -e DATABASE_URL=postgresql+asyncpg://alafia:alafia@db:5432/alafia \
      backend-test python scripts/resolve_nutrient_effects.py

    ... then, to actually ask and store:
    ... backend-test python scripts/resolve_nutrient_effects.py --apply
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from app.core.database import async_session
from app.models.chronic_conditions import TherapySession
from app.models.med_nutrient import MedicationDoseLog
from app.services.flowsheet_drugs import canonical_drug_name, parse_drugs_administered
from app.services.nutrient_effects_service import (
    normalize_agent, resolve_agent_effects, stored_effects,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("resolve_nutrient_effects")


async def _distinct_agents(db) -> list[tuple[str, str]]:
    """Every (kind, label) the record actually holds, deduped on the agent KEY.

    Deduped on the key rather than the label because "Venofer", "venofer" and
    "Iron sucrose" are one drug (§3aa) and resolving each spelling separately
    would spend three model calls to build three rows that then converge only on
    themselves.
    """
    seen: dict[tuple[str, str], tuple[str, str]] = {}

    def remember(kind: str, label: str) -> None:
        label = (label or "").strip()
        if not label:
            return
        key = normalize_agent(label, kind)
        if key:
            seen.setdefault((kind, key), (kind, label))

    for therapy_type in (await db.execute(
        select(TherapySession.therapy_type).distinct()
    )).scalars().all():
        value = str(getattr(therapy_type, "value", therapy_type) or "").strip()
        if value:
            remember("treatment", value.replace("_", " "))

    for name in (await db.execute(
        select(MedicationDoseLog.medication_name).distinct()
    )).scalars().all():
        remember("medication", str(name or ""))

    # The third source. Parsed rather than read whole: one cell holds several
    # drugs, and `;` also occurs INSIDE a dose, so a naive split invents drugs.
    for written in (await db.execute(
        select(TherapySession.drugs_administered).distinct()
    )).scalars().all():
        for drug in parse_drugs_administered(written):
            # Unrecognised names come back unchanged. Resolve them anyway — an
            # unmapped drug is exactly the one nobody has modelled — but the
            # canonical fold is what stops three spellings becoming three rows.
            remember("medication", canonical_drug_name(drug.name)[0])

    return sorted(seen.values(), key=lambda p: (p[0], p[1].lower()))


async def sweep(*, apply: bool, limit: int | None, only: str | None) -> int:
    """Resolve unknown agents. Returns the number of agents newly described."""
    resolved_count = 0
    async with async_session() as db:
        agents = await _distinct_agents(db)
        if only:
            needle = only.strip().lower()
            agents = [a for a in agents if needle in a[1].lower()]

        known = await stored_effects(db, agents)
        have = {(e.agent_kind, e.agent_key) for e in known}

        pending = [
            (kind, label) for kind, label in agents
            if (kind, normalize_agent(label, kind)) not in have
        ]
        logger.info(
            "%d distinct agents in the record; %d already described, %d to resolve",
            len(agents), len(agents) - len(pending), len(pending),
        )

        if limit is not None:
            pending = pending[:limit]

        if not apply:
            for kind, label in pending:
                logger.info("  would resolve %-11s %s", kind, label)
            logger.info("dry run — nothing asked and nothing written. Use --apply.")
            return 0

        for kind, label in pending:
            effects = await resolve_agent_effects(db, kind, label)
            if effects:
                resolved_count += 1
                for effect in effects:
                    logger.info(
                        "  %-11s %-28s %-9s %-22s %s %s",
                        kind, label, effect.direction, effect.nutrient_key,
                        "?" if effect.magnitude is None else f"{effect.magnitude:g}",
                        effect.magnitude_unit or "",
                    )
            else:
                # Not the same as "this agent affects nothing" (§3aa). Say which.
                logger.info("  %-11s %-28s no effects returned", kind, label)
            await db.commit()

    return resolved_count


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually ask the model and write the results")
    parser.add_argument("--limit", type=int, default=None,
                        help="resolve at most N agents this run")
    parser.add_argument("--only", type=str, default=None,
                        help="only agents whose label contains this text")
    args = parser.parse_args()

    count = await sweep(apply=args.apply, limit=args.limit, only=args.only)
    logger.info("done: %d agent(s) newly described", count)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001
        logger.error("sweep failed: %s", exc, exc_info=True)
        sys.exit(1)
