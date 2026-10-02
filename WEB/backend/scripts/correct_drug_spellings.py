#!/usr/bin/env python3
"""Correct misspelled drug names — only where RxNorm names the correction.

`resolve_nutrient_effects.py` reported seven names RxNorm does not recognise.
A misspelled drug is not cosmetic: `canonical_drug_name` cannot map it, so the
drug never joins its own history, never reaches nutrient tracking, and shows up
as a separate drug on the medication list (§3aj).

WHAT THIS WILL AND WILL NOT DO
------------------------------
RxNorm's `approximateTerm` returns CANDIDATES, not corrections. Probed
2026-10-02, each candidate rxcui resolved to its actual RxNorm name:

    Cyclobenzeprine        -> 21949   cyclobenzaprine          CORRECT
    Vancomicine            -> 11124   vancomycin               CORRECT
    Flublok 2024 - 2026    -> 2746444 Flublok 2026-2027        operator-chosen
    Flucel Vax             -> 2109616 Vaxelis                  REFUSED
    Marine Bone Discovery  -> 2738225 (no name)                REFUSED
    Rugby Stimulant ...    -> 2282120 (no name)                REFUSED
    Oedesetron             -> (no candidate at all)            REFUSED

`Flucel Vax` is the case that proves the rule. Its best match is **Vaxelis, a
different vaccine**, and RxNorm holds nothing under the correct spelling either
(`Flucelvax`, `Flucelvax Quadrivalent` and `influenza virus vaccine` all return
no rxcui). A rename there would put a wrong vaccine on a clinical record.
`Oedesetron` looks like ondansetron (rxcui 26225 exists) — but RxNorm offered no
candidate, and §3aj is explicit that string similarity is the wrong instrument
for drug names: "calcium calcitriol" scores 0.63 against "calcium carbonate" and
its nearest match is a third drug entirely.

Two rxcuis tied at an identical score for `Marine Bone Discovery` (2738225 and
352755, both 12.731). A tie is the authority declining to choose.

The three vaccine seasons also tied at 14.87 — 2024-2025, 2025-2026, 2026-2027 —
so the season came from the operator against the administration date, not from
the match score.

WHERE THE NAMES LIVE (production, 2026-10-02)
---------------------------------------------
    medication_dose_logs   Cyclobenzeprine 6, Oedesetron 4, Marine Bone 3,
                           Flublok 1, Rugby Stimulant 1, Vancomicine 1
    medications            Cyclobenzeprine 1, Oedesetron 1
    therapy_sessions       one 2018 flowsheet line carrying `Flucel Vax (5 ml)`

Dry run is the default: this UPDATES clinical rows.

    python scripts/correct_drug_spellings.py            # dry run
    python scripts/correct_drug_spellings.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

sys.path.insert(0, "/app")

from app.core.database import async_session            # noqa: E402
from app.models.med_nutrient import MedicationDoseLog  # noqa: E402
from app.models.medications import Medication          # noqa: E402


#: wrong -> (right, rxcui, why). ONLY names RxNorm itself resolved.
CORRECTIONS: dict[str, tuple[str, str, str]] = {
    "Cyclobenzeprine": (
        "Cyclobenzaprine", "21949",
        "RxNorm names rxcui 21949 'cyclobenzaprine'"),
    "Vancomicine": (
        "Vancomycin", "11124",
        "RxNorm names rxcui 11124 'vancomycin'"),
    "Flublok 2024 - 2026": (
        "Flublok 2026-2027", "2746444",
        "three seasons tied at 14.87; season chosen by the operator against the "
        "2026-09-15 administration date, not by match score"),
    "Oedesetron": (
        "Ondansetron", "26225",
        "TWO independent sources: the operator identified the drug, and RxNorm "
        "names rxcui 26225 'ondansetron' (TTY=IN, an ingredient concept — the "
        "right granularity for a dose log). RxNorm's own approximate matcher "
        "offered NO candidate, so similarity never entered into it (§3aj)"),
}

#: Real products that RxNorm does not cover. These are NOT misspellings and must
#: never be renamed — the operator identified each one. A list headed "names
#: RxNorm does not recognise" reads as an error report when it is a COVERAGE
#: BOUNDARY, and §3aj's fail-open rule covers absence as well as unreachability:
#: not in the authority is not the same as invalid.
#:
#: `NutrientEffect` already defines AGENT_SUPPLEMENT and AGENT_HERB beside
#: AGENT_MEDICATION, but `resolve_nutrient_effects.py` labels everything out of
#: `medication_dose_logs` as a medication because that is the table it came
#: from. A supplement is not a prescription, and §3an's rule applies — enforced
#: alike, EXPLAINED differently.
OUTSIDE_RXNORM: dict[str, str] = {
    "Marine Bone Discovery":
        "supplement (operator-identified). Two candidate rxcuis tied at an "
        "identical 12.731 and neither resolves to a name.",
    "Flucel Vax":
        "flu vaccine, season = the logged date (2018-10-17 -> 2018-2019). "
        "RxNorm holds NO Flucelvax concept: `Flublok 2024-2025` resolved to "
        "2687737 through the identical exact-name call that returned nothing "
        "for every Flucelvax form, and all 8 approximate candidates tied at "
        "15.382 resolve to no name. Its only 'match' was Vaxelis, a different "
        "vaccine. Lives in TWO places — therapy_sessions id=776 free text and "
        "session_drugs id=1781, which carries a route and timestamp the text "
        "does not.",
    "Rugby Stimulant Laxative Plus Stool Softener":
        "OTC product (operator-identified). The branded combination is not in "
        "RxNorm, though the sweep still resolved its effects correctly from "
        "mechanism: removes potassium_mg / sodium_mg via increased fecal "
        "losses.",
}

#: Nothing is listed here any more. The four names this script originally
#: refused went back to the operator, and only ONE was a misspelling
#: (`Oedesetron`, now in CORRECTIONS). The other three are real products RxNorm
#: does not carry — see OUTSIDE_RXNORM above.
#:
#: Kept as an empty dict rather than deleted: a name that cannot be resolved AND
#: cannot be identified by the operator still belongs here, left exactly as
#: written. A wrong drug name on a clinical record is worse than an unmatched
#: one.
REFUSED: dict[str, str] = {}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the corrections (default: dry run)")
    args = ap.parse_args()

    changed = 0
    async with async_session() as db:
        for wrong, (right, rxcui, why) in CORRECTIONS.items():
            logs = (await db.execute(
                select(MedicationDoseLog).where(
                    MedicationDoseLog.medication_name == wrong)
            )).scalars().all()
            meds = (await db.execute(
                select(Medication).where(Medication.name == wrong)
            )).scalars().all()

            if not logs and not meds:
                print(f"  {wrong!r}: no rows — nothing to correct")
                continue

            print(f"  {wrong!r} -> {right!r}  (rxcui {rxcui})")
            print(f"      {why}")
            print(f"      dose logs: {len(logs)}   prescriptions: {len(meds)}")
            for row in logs:
                if args.apply:
                    row.medication_name = right
                changed += 1
            for row in meds:
                if args.apply:
                    row.name = right
                changed += 1

        if args.apply:
            await db.commit()

    print()
    print("OUTSIDE RxNORM — real products, identified by the operator, NOT renamed:")
    for name, why in OUTSIDE_RXNORM.items():
        print(f"  {name}")
        print(f"      {why}")

    if REFUSED:
        print()
        print("REFUSED — left exactly as written, for a human to check the source:")
        for name, why in REFUSED.items():
            print(f"  {name}")
            print(f"      {why}")

    print()
    if args.apply:
        print(f"applied: {changed} row(s) corrected.")
    else:
        print(f"dry run: {changed} row(s) would change. Use --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
