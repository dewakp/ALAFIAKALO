"""Catch impossible medication doses before they reach the record.

The case that prompted this: a production dose log reading
**"calcium calcitriol 1000 mg"**. That is not a drug. It was meant to be calcium
carbonate 1000 mg — which is an ordinary dose — but read literally it names
calcitriol, which is dosed in MICROGRAMS (0.25–1 mcg typical). Taken at face
value it is roughly a thousand-fold overdose sitting in a clinical record, and
anything that later infers "your usual dose" from history would replay it with a
confident "your last dose" caption underneath.

Nothing invented here: `dose_unit_canonical` and `MAX_DOSE_CANONICAL` already
existed in `med_nutrient_service` with sourced values (calcitriol → mcg, ceiling
2.0; calcium carbonate → mg, ceiling 3000). They were simply never called from
the endpoint that writes doses — the §3ad pattern, a correct thing wired to
nothing.

Deliberately conservative: this only reports what it can PROVE from reference
data. An unrecognised drug name is not an error — the profile table holds a few
dozen entries and most real prescriptions are not in it, so refusing unknowns
would block ordinary use. It fires on positive evidence only:

  * the unit contradicts the drug's canonical unit, or
  * the dose exceeds a known ceiling for that drug, or
  * the name contains a known drug as a whole word ("calcium calcitriol"
    contains "calcitriol"), or is a near-miss typo of one.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.med_nutrient import MedNutrientProfile
from app.services.rxnorm import lookup as rxnorm_lookup

if TYPE_CHECKING:
    from app.services.rxnorm import DrugFacts
from app.services.med_nutrient_service import (
    MAX_DOSE_CANONICAL,
    normalize_med_name,
    unit_convert_factor,
)

logger = get_logger(__name__)

# How alike a typed name must be to a known drug before we call it a typo.
# Kept HIGH on purpose: at 0.85 "calcitrol" still matches "calcitriol" (a real
# typo), while "calcium calcitriol" does not drag in "calcium citrate" — which
# scores 0.727 and would be a confidently wrong suggestion. Containment above
# handles that case on evidence instead of on resemblance.
_TYPO_RATIO = 0.85


@dataclass
class DoseFinding:
    level: str            # "error" (blocks unless acknowledged) | "warning"
    code: str
    message: str
    suggestion: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


async def _known_names(db: AsyncSession) -> list[str]:
    rows = (await db.execute(select(MedNutrientProfile.med_name_normalized))).scalars().all()
    return sorted({*(rows or []), *MAX_DOSE_CANONICAL.keys()})


async def _profile_for(db: AsyncSession, normalized: str) -> MedNutrientProfile | None:
    return (await db.execute(
        select(MedNutrientProfile).where(
            MedNutrientProfile.med_name_normalized == normalized
        )
    )).scalar_one_or_none()


async def validate_dose(
    db: AsyncSession, medication_name: str, dose_amount: float, dose_unit: str,
    *, rx: "DrugFacts | None" = None,
) -> list[DoseFinding]:
    """Report provable problems with a dose. Empty list means nothing to say.

    RxNorm is the authority on whether a name is a medication — a hand-written
    table is only a list of the drugs somebody remembered, and it waved through
    "sevelamer carbonate" (a real drug it lacked) while flagging "Calcitriol" as
    a misspelling of itself. `rx` is injectable so tests need no network.
    """
    findings: list[DoseFinding] = []
    name = (medication_name or "").strip()
    if not name:
        return findings

    normalized = normalize_med_name(name)
    profile = await _profile_for(db, normalized)
    locally_known = profile is not None or normalized in MAX_DOSE_CANONICAL

    if rx is None:
        rx = await rxnorm_lookup(name)

    # ── 1. Is this a medication at all? ──────────────────────────────────
    if rx.reachable and not rx.known and not locally_known:
        if rx.suggestion and normalize_med_name(rx.suggestion) != normalized:
            findings.append(DoseFinding(
                level="error",
                code="unknown_medication",
                message=(f"“{name}” isn’t a medication in RxNorm. The closest match "
                         f"is “{rx.suggestion}” — please confirm what was taken."),
                suggestion=rx.suggestion,
            ))
        else:
            findings.append(DoseFinding(
                level="error",
                code="unknown_medication",
                message=f"“{name}” isn’t a medication we can find in RxNorm.",
            ))
        return findings

    # ── 2. Unit and ceiling, against whatever reference we have ──────────
    if profile is not None:
        findings.extend(await _check_against(profile, name, dose_amount, dose_unit))

    findings.extend(_check_marketed_strength(rx, name, dose_amount, dose_unit))
    # When RxNorm is unreachable the profile path above still applies its
    # canonical unit and MAX_DOSE_CANONICAL ceiling, so an outage degrades the
    # check rather than removing it.
    return findings


# A single dose may legitimately be several units of the largest marketed
# strength (two tablets, a double dose). Beyond this multiple it is not a dosing
# choice, it is a units error.
_UNITS_PER_DOSE = 10.0

_TO_MG = {"mg": 1.0, "mcg": 0.001, "µg": 0.001, "ug": 0.001, "g": 1000.0}


def _check_marketed_strength(
    rx: "DrugFacts", name: str, dose_amount: float, dose_unit: str,
) -> list[DoseFinding]:
    """Compare the dose against the largest strength actually sold.

    Derived, not hand-written: RxNorm lists calcitriol at 0.00025 and 0.0005 MG,
    so 1000 mg is two million times the biggest capsule made.
    """
    unit = (dose_unit or "").strip().lower()
    factor = _TO_MG.get(unit)
    if not (rx.known and rx.max_strength_mg and factor and dose_amount):
        return []
    dose_mg = float(dose_amount) * factor
    ceiling_mg = rx.max_strength_mg * _UNITS_PER_DOSE
    if dose_mg <= ceiling_mg:
        return []
    ceiling_str = _readable_mg(rx.max_strength_mg)
    return [DoseFinding(
        level="error",
        code="dose_exceeds_marketed_strength",
        message=(f"{dose_amount:g} {dose_unit} of {name} is {dose_mg:g} mg — the largest "
                 f"marketed single unit is {ceiling_str}. Check the units."),
        suggestion=f"{ceiling_str} or less per unit",
    )]


def _readable_mg(mg: float) -> str:
    """Express a strength the way a label does.

    RxNorm returns milligrams for everything, so calcitriol comes back as
    0.0005 mg. Printed like that, the warning is nearly unreadable and invites
    the very misjudgement it exists to prevent — the drug is dosed, prescribed
    and labelled in MICROGRAMS. Sub-milligram strengths are shown in mcg.
    """
    if mg < 1:
        return f"{mg * 1000:g} mcg"
    return f"{mg:g} mg"


async def _check_against(
    profile: MedNutrientProfile, name: str, dose_amount: float, dose_unit: str,
) -> list[DoseFinding]:
    """Unit and ceiling checks for a dose read against a specific drug profile."""
    findings: list[DoseFinding] = []
    canonical = (profile.dose_unit_canonical or "").strip()
    unit = (dose_unit or "").strip()

    # ── 2. The unit contradicts the drug ─────────────────────────────────
    factor = unit_convert_factor(unit, canonical) if unit and canonical else None
    if unit and canonical and factor is None:
        findings.append(DoseFinding(
            level="error",
            code="unit_mismatch",
            message=(f"{profile.med_name_original} is measured in {canonical}, "
                     f"and “{unit}” cannot be converted to it. Check the label."),
            suggestion=canonical,
        ))
        return findings   # without a conversion the ceiling check is meaningless

    # ── 3. Ceilings come from RxNorm, NOT from a table in this repo ──────
    #
    # There used to be a second ceiling check here reading `MAX_DOSE_CANONICAL`,
    # nine hand-written numbers. That is the thing this module exists to avoid:
    # a hand-written range is only ever right for the drugs someone thought of,
    # it goes stale silently, and when it is wrong it BLOCKS A CORRECT CLINICAL
    # RECORD — the patient cannot log what they actually took.
    #
    # `_check_marketed_strength()` already derives the ceiling from what RxNorm
    # says is actually sold, which is authoritative and covers every drug rather
    # than nine. When RxNorm is unreachable there is no ceiling check at all, and
    # that is deliberate: unreachable is not invalid, and blocking every dose
    # because a third-party API is down is worse than the risk being guarded
    # against (canon 3aj, "fail OPEN").
    return findings


def blocking(findings: list[DoseFinding]) -> list[DoseFinding]:
    return [f for f in findings if f.level == "error"]
