"""Resolve what an AGENT does to a NUTRIENT, store it, and reuse it.

The companion to `condition_nutrition_service`, and deliberately the same shape:
normalise the key → serve from the store → otherwise ask the model for a SHAPE
→ upsert so re-resolution SHARPENS one row instead of inserting beside it.

What it replaces is a closure three layers deep — `ANALYTES`, `GOAL_KEY`, and
`DialysisSoluteCoefficient.analyte` — where every new clinical fact cost a code
change. Protein's arrival as a fifth dialysis analyte required a `GOAL_KEY`
entry, a bespoke `elif`, and an inline unit hack. That is the enumeration tax,
and it is why the set of modelled effects froze at whatever someone happened to
think of while glucose, phosphate binding and vitamin stripping stayed invisible.

WHAT DOES NOT BELONG HERE
-------------------------
Gradient transfer. `dialysis_balance` needs a serum concentration and a bath
concentration, and `SerumLevels` carries exactly four analytes — so potassium,
phosphorus, magnesium and calcium can be computed that way and nothing else
ever can. This module holds rate- and dose-driven effects, which need neither.

The split is not invented here; it is already in the code, badly. Protein's
coefficients are `saturation=0.0, sieving=0.0, diffusible_fraction=0.0,
grams_per_session=9.0` — every physics term zeroed to disable the physics.

SAFETY IS COMPUTED HERE, NOT ASKED OF THE MODEL
-----------------------------------------------
Whether an effect needs a measurement behind it depends on the PATIENT, not on
the effect: potassium is a `limit` for someone on dialysis and a `target` for
everyone else, and the same clearance therefore means opposite things. So the
model is never asked; `gate_needed()` decides from the goal's own `kind`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.nutrition_data import NUTRIENT_CATALOG
from app.models.nutrient_effect import (
    ADDS, BINDS_DIETARY, BLOCKS_ABSORPTION, INCREASES_REQUIREMENT, REMOVES,
    FRACTION_OF_INTAKE, PER_DOSE_UNIT, PER_G_DIETARY, PER_LITRE_DIALYSATE, PER_SESSION,
    NutrientEffect,
)

logger = logging.getLogger(__name__)

VALID_AGENT_KINDS = {"treatment", "medication", "condition", "supplement", "herb", "procedure"}
VALID_DIRECTIONS = {ADDS, REMOVES, BINDS_DIETARY, BLOCKS_ABSORPTION, INCREASES_REQUIREMENT}
VALID_BASES = {PER_SESSION, PER_DOSE_UNIT, PER_G_DIETARY, PER_LITRE_DIALYSATE, FRACTION_OF_INTAKE}
VALID_EVIDENCE = {"high", "moderate", "low", "expert_opinion"}

#: At most this many effects per agent. An agent with forty claimed effects is a
#: model padding, not a clinical finding.
_MAX_EFFECTS_PER_AGENT = 8

#: catalog key -> key, and display name -> key. The model answers in clinical
#: language ("thiamine"), not in our column names, and a fact we cannot map to a
#: catalog key can never reach a total — so it is refused rather than stored.
_KEY_BY_KEY = {n["key"]: n["key"] for n in NUTRIENT_CATALOG}
_KEY_BY_NAME: dict[str, str] = {}
for _n in NUTRIENT_CATALOG:
    _KEY_BY_NAME[str(_n["name"]).strip().lower()] = _n["key"]
    # "Thiamine (B1)" is also asked for as "thiamine".
    _bare = re.sub(r"\s*\([^)]*\)", "", str(_n["name"])).strip().lower()
    _KEY_BY_NAME.setdefault(_bare, _n["key"])


#: Agent kinds whose names are DRUG names, and therefore have a canonical form.
_DRUG_LIKE_KINDS = {"medication", "supplement", "herb"}


def normalize_agent(name: str, agent_kind: str | None = None) -> str:
    """Normalise an agent to its lookup key.

    Agents arrive spelled many ways — a therapy_type enum, an RxNorm label, a
    patient's own typing — so matching is on this and never on the display text.

    For a DRUG the name is first folded through
    `flowsheet_drugs.canonical_drug_name`, and that is not optional. Its own
    docstring says why: the same medication arrives as "Venofer" on a
    flowsheet, "venofer" in a dose log and "Iron sucrose" from a FHIR import,
    and "anything grouping on the raw string reports three drugs where the
    patient is on one". Without the fold this store would hold three separate
    sets of facts for one drug, each keyed by spelling and each converging only
    on itself — the duplication §3ab exists to prevent, built into the very
    mechanism meant to prevent it.

    An unrecognised name comes back unchanged with `recognised=False` and is
    then normalised textually. Never guess: an unmatched drug name is a gap, a
    wrongly-matched one is a clinical error.
    """
    raw = (name or "").strip()
    if not raw:
        return ""
    if agent_kind in _DRUG_LIKE_KINDS:
        # Imported here rather than at module scope: this module is imported by
        # the nutrition API, and flowsheet parsing is not needed to read a
        # stored effect.
        from app.services.flowsheet_drugs import canonical_drug_name

        raw = canonical_drug_name(raw)[0]
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", raw.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def resolve_nutrient_key(raw: str) -> str | None:
    """Map whatever the model called a nutrient onto a catalog key, or None.

    Returning None is the correct outcome for something we cannot represent: a
    stored effect whose nutrient no total understands is a fact that can never
    be applied, which is worse than an absent one because it looks like coverage.
    """
    if not raw:
        return None
    probe = str(raw).strip().lower()
    if probe in _KEY_BY_KEY:
        return probe
    return _KEY_BY_NAME.get(probe) or _KEY_BY_NAME.get(re.sub(r"\s*\([^)]*\)", "", probe).strip())


def gate_needed(direction: str, goal_kind: str) -> bool:
    """Does crediting this effect need a recent measurement behind it?

    Not a question about sign. `_gate_removal` gates removals because "crediting
    a removal lowers a total and therefore looks like room to eat more" — yet
    protein, a removal, is deliberately ungated, because lowering a TARGET's
    achieved value tells the patient to eat MORE, which is the safe direction.

    The rule is about false reassurance:

        ↓ a LIMIT   (potassium cleared)   creates dietary headroom   → gate
        ↑ a LIMIT   (dextrose → sugar)    tightens the budget        → apply
        ↓ a TARGET  (protein lost)        eat more                   → apply
        ↑ a TARGET  (IV iron → iron)      "you are fine"             → gate

    That last row has no implementation anywhere today and is the dangerous one:
    crediting Venofer against an iron target would tell an anaemic patient they
    had met their needs.
    """
    lowers = direction in (REMOVES, BINDS_DIETARY, BLOCKS_ABSORPTION)
    if goal_kind == "limit":
        return lowers
    return not lowers      # a target: raising the achieved figure reassures


@dataclass(frozen=True)
class Effect:
    """One resolved effect, in the form a consumer applies."""

    agent_kind: str
    agent_key: str
    agent_label: str
    nutrient_key: str
    direction: str
    magnitude: float | None
    magnitude_unit: str | None
    basis: str
    scales_with: str | None = None
    scale_reference: float | None = None
    scale_min: float | None = None
    scale_max: float | None = None
    mechanism: str | None = None
    evidence_level: str = "moderate"
    confidence: float = 0.5
    calibrated: bool = False

    def scaled_magnitude(self, context: dict[str, float] | None = None) -> float | None:
        """Apply the stored scaling rule to this effect's magnitude.

        Reproduces the protein prior exactly: 9 g per session multiplied by
        (dialysate volume / 30 L), clamped to 0.5–2.0×. The clamp is not
        decoration — an unclamped ratio would credit a 120 L session with four
        times the amino-acid loss, which is not what happens.
        """
        if self.magnitude is None:
            return None
        if not self.scales_with or not self.scale_reference:
            return self.magnitude
        measured = (context or {}).get(self.scales_with)
        if not measured or self.scale_reference <= 0:
            return self.magnitude
        ratio = measured / self.scale_reference
        if self.scale_min is not None:
            ratio = max(self.scale_min, ratio)
        if self.scale_max is not None:
            ratio = min(self.scale_max, ratio)
        return self.magnitude * ratio


def _row_to_effect(row: NutrientEffect) -> Effect:
    return Effect(
        agent_kind=row.agent_kind, agent_key=row.agent_key, agent_label=row.agent_label,
        nutrient_key=row.nutrient_key, direction=row.direction,
        magnitude=row.magnitude, magnitude_unit=row.magnitude_unit, basis=row.basis,
        scales_with=row.scales_with, scale_reference=row.scale_reference,
        scale_min=row.scale_min, scale_max=row.scale_max,
        mechanism=row.mechanism, evidence_level=row.evidence_level,
        confidence=row.confidence,
        calibrated=(row.provenance in ("clinician", "measured")),
    )


async def stored_effects(
    db: AsyncSession, agents: Iterable[tuple[str, str]]
) -> list[Effect]:
    """Everything already known about these (agent_kind, agent_label) pairs."""
    pairs = [(k, normalize_agent(label, k)) for k, label in agents if label]
    pairs = [(k, key) for k, key in pairs if key]
    if not pairs:
        return []

    kinds = {k for k, _ in pairs}
    keys = {key for _, key in pairs}
    rows = (await db.execute(
        select(NutrientEffect).where(
            NutrientEffect.agent_kind.in_(kinds),
            NutrientEffect.agent_key.in_(keys),
            NutrientEffect.is_active.is_(True),
        )
    )).scalars().all()
    wanted = set(pairs)
    return [_row_to_effect(r) for r in rows if (r.agent_kind, r.agent_key) in wanted]


_RESOLVE_PROMPT = """You are a clinical pharmacologist and renal dietitian. \
State how the agent below changes a patient's DAILY NUTRIENT TOTALS.

AGENT KIND: {agent_kind}
AGENT: {agent_label}

Return ONLY a JSON object matching this SHAPE, no prose and no code fences. \
The angle brackets are placeholders — never echo them back:
{{"effects":[{{"nutrient":"<nutrient name or key>",
              "direction":"adds|removes|binds_dietary|blocks_absorption|increases_requirement",
              "magnitude":<number or null>,
              "unit":"<mg|mcg|g|IU|fraction>",
              "basis":"per_session|per_dose_unit|per_g_dietary|per_litre_dialysate|fraction_of_intake",
              "mechanism":"<short clinical reason>",
              "evidence":"high|moderate|low"}}]}}

RULES:
1. "adds" means the patient receives the nutrient WITHOUT eating it. "removes" \
means it leaves the body. "binds_dietary" means it subtracts nutrient the \
patient DID eat, before absorption. "blocks_absorption" reduces the fraction \
absorbed. "increases_requirement" moves the target, not the total.
2. "basis" must say what the magnitude is per. A number without its basis is \
meaningless, so if you cannot state the basis, set magnitude to null.
3. Set "magnitude" to null when no established figure exists. A null magnitude \
is useful — it records THAT the effect exists. An invented number is not.
4. Only effects specific to this agent. General healthy-eating advice is not an \
effect, and neither is a nutrient the agent merely contains as an excipient.
5. If the agent has no established effect on nutrient totals, return an empty \
array. Do NOT invent one.
6. At most {limit} effects, most clinically significant first."""


async def resolve_agent_effects(
    db: AsyncSession,
    agent_kind: str,
    agent_label: str,
    *,
    agent_code: str | None = None,
) -> list[Effect]:
    """Ask the model what this agent does to nutrient totals, store it, return it.

    Never raises. A nutrient page must still render when the knowledge tier is
    unavailable, and an empty result is logged with its reason rather than being
    indistinguishable from "this agent affects nothing" (§3aa).
    """
    agent_kind = agent_kind if agent_kind in VALID_AGENT_KINDS else "medication"
    key = normalize_agent(agent_label, agent_kind)
    if not key:
        return []

    prompt = _RESOLVE_PROMPT.format(
        agent_kind=agent_kind, agent_label=agent_label, limit=_MAX_EFFECTS_PER_AGENT)

    try:
        from app.services.alafia_model_service import alafia_chat
        raw = (await alafia_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=1200, json_mode=True,
        )).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("nutrient effects: could not resolve %r (%s): %s",
                       agent_label, agent_kind, exc)
        return []

    parsed = _parse_effects(raw)
    if parsed is None:
        logger.warning("nutrient effects: unparseable reply for %r", agent_label)
        return []

    out: list[Effect] = []
    for item in parsed[:_MAX_EFFECTS_PER_AGENT]:
        effect = await _upsert(
            db, agent_kind=agent_kind, agent_key=key, agent_label=agent_label,
            agent_code=agent_code, item=item,
        )
        if effect is not None:
            out.append(effect)
    return out


def _parse_effects(raw: str) -> list[dict] | None:
    """Pull the effects array out of a model reply, tolerating fences."""
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    effects = obj.get("effects")
    return effects if isinstance(effects, list) else None


async def _upsert(
    db: AsyncSession,
    *,
    agent_kind: str,
    agent_key: str,
    agent_label: str,
    agent_code: str | None,
    item: dict[str, Any],
) -> Effect | None:
    """Store one effect, or sharpen the one already there.

    Re-resolution must CONVERGE. §3ab records what a re-import that inserts
    beside the row it meant to correct does to a record: the patient ends up
    holding two contradictory facts about one subject.
    """
    if not isinstance(item, dict):
        return None

    nutrient_key = resolve_nutrient_key(item.get("nutrient", ""))
    if nutrient_key is None:
        # Not representable in any total — refusing beats storing a fact that
        # can never be applied but looks like coverage.
        logger.info("nutrient effects: %r is not a catalog nutrient, skipped",
                    item.get("nutrient"))
        return None

    direction = str(item.get("direction") or "").strip()
    basis = str(item.get("basis") or "").strip()
    if direction not in VALID_DIRECTIONS or basis not in VALID_BASES:
        return None

    magnitude = item.get("magnitude")
    magnitude = float(magnitude) if isinstance(magnitude, (int, float)) else None
    evidence = str(item.get("evidence") or "moderate")
    if evidence not in VALID_EVIDENCE:
        evidence = "moderate"

    existing = (await db.execute(
        select(NutrientEffect).where(
            NutrientEffect.agent_kind == agent_kind,
            NutrientEffect.agent_key == agent_key,
            NutrientEffect.nutrient_key == nutrient_key,
            NutrientEffect.direction == direction,
        )
    )).scalar_one_or_none()

    if existing is not None:
        existing.times_confirmed += 1
        existing.confidence = min(0.99, existing.confidence + 0.1)
        # A literature prior or a clinician's figure outranks a re-derivation:
        # only fill a magnitude that is genuinely absent.
        if existing.magnitude is None and magnitude is not None:
            existing.magnitude = magnitude
            existing.magnitude_unit = item.get("unit") or existing.magnitude_unit
        if not existing.mechanism and item.get("mechanism"):
            existing.mechanism = str(item["mechanism"])[:2000]
        if agent_code and not existing.agent_code:
            existing.agent_code = agent_code
        existing.is_active = True
        row = existing
    else:
        row = NutrientEffect(
            agent_kind=agent_kind, agent_key=agent_key, agent_label=agent_label,
            agent_code=agent_code, nutrient_key=nutrient_key, direction=direction,
            magnitude=magnitude,
            magnitude_unit=(str(item["unit"])[:16] if item.get("unit") else None),
            basis=basis,
            mechanism=(str(item["mechanism"])[:2000] if item.get("mechanism") else None),
            evidence_level=evidence, provenance="llm",
            confidence=0.6 if evidence == "high" else 0.5,
            times_confirmed=1,
        )
        db.add(row)

    # A knowledge write must never break the caller's own work — §3a's SAVEPOINT
    # lesson: a failed flush poisons the session and the later commit 500s even
    # when the exception was caught.
    try:
        await db.flush()
    except Exception:  # noqa: BLE001
        logger.warning("nutrient effects: could not store %r/%r",
                       agent_key, nutrient_key, exc_info=True)
        return None
    return _row_to_effect(row)
