"""Reference ranges come from the data, never from a constant in the source.

A reference range is not a fact about medicine — it is a fact about a lab, an
assay, a sex and an age. Writing one into the engine picks a population and
applies it to everybody: an earlier BUN band used 21, which is the adult FEMALE
ceiling, on a male patient whose own lab reported 9-23. Across millions of
patients that is not an approximation, it is wrong for most of them.

Every `lab_results` row can carry the range its lab printed, and 63.5% of them
do, covering 120 of 219 analytes on this database. So the range is looked up,
in order of how specific it is to the patient:

    1. the patient's OWN most recent reported range for that analyte
    2. the range most commonly reported for that analyte across the population
    3. a guideline target held in `clinical_thresholds` — for values a lab never
       prints a range for, such as Kt/V or a calcium-phosphorus product
    4. a range LEARNED from the central 95% of observed values, stored back so
       the next request is a lookup rather than a recomputation
    5. nothing — and only then does the biomarker go unscored

No step invents a range. Step 4 is why "unscored" is rarely the answer: if an
analyte has been measured enough times, the central 95% of observed values IS a
reference range — that is how reference ranges are established — and it improves
as patients arrive rather than going stale like a constant. Step 5 remains for
analytes nobody has measured, where there is nothing to score anyway.
"""

from __future__ import annotations

import logging
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.labs import LabResult

logger = logging.getLogger(__name__)

Range = tuple[float, float]


async def for_user(db: AsyncSession, user_id: int) -> dict[str, Range]:
    """{test_name: (low, high)} as reported on THIS patient's own results.

    The most recent report wins: a lab can revise its range, and the newest one
    is the one their clinician is reading.
    """
    rows = (await db.execute(
        select(LabResult.test_name,
               LabResult.reference_range_low,
               LabResult.reference_range_high)
        .where(LabResult.user_id == user_id,
               LabResult.reference_range_low.isnot(None),
               LabResult.reference_range_high.isnot(None))
        .order_by(LabResult.test_name, LabResult.test_date.desc())
    )).all()

    ranges: dict[str, Range] = {}
    for name, low, high in rows:
        if name in ranges:
            continue
        if low is not None and high is not None and high > low:
            ranges[name] = (float(low), float(high))
    return ranges


async def population_modes(db: AsyncSession) -> dict[str, Range]:
    """The range most often reported for each analyte, across all patients.

    Used only where the patient has none of their own. The MODE rather than a
    mean: ranges are categorical (a lab prints one specific pair), so averaging
    two labs' ranges would produce a pair neither of them uses.
    """
    rows = (await db.execute(
        select(LabResult.test_name,
               LabResult.reference_range_low,
               LabResult.reference_range_high,
               func.count().label("n"))
        .where(LabResult.reference_range_low.isnot(None),
               LabResult.reference_range_high.isnot(None))
        .group_by(LabResult.test_name,
                  LabResult.reference_range_low,
                  LabResult.reference_range_high)
    )).all()

    counts: dict[str, Counter] = {}
    for name, low, high, n in rows:
        if low is None or high is None or high <= low:
            continue
        counts.setdefault(name, Counter())[(float(low), float(high))] += int(n)

    return {name: c.most_common(1)[0][0] for name, c in counts.items() if c}


async def clinical_thresholds(db: AsyncSession) -> dict[str, Range]:
    """Guideline targets held as data, for the values a lab never prints.

    A lab reports a reference range for albumin; it does not report one for
    Kt/V or a calcium-phosphorus product, because those are guideline TARGETS
    rather than assay ranges. They still must not be constants in the engine —
    a guideline revision should be a row change, not a deploy — so they live in
    `clinical_thresholds` with the source of each number recorded beside it.
    """
    from app.models.clinical_threshold import ClinicalThreshold

    rows = (await db.execute(
        select(ClinicalThreshold.analyte,
               ClinicalThreshold.opt_low,
               ClinicalThreshold.opt_high)
        .where(ClinicalThreshold.is_active.is_(True))
    )).all()
    return {
        analyte: (float(low), float(high))
        for analyte, low, high in rows
        if low is not None and high is not None and high > low
    }


#: Below this many observations a percentile range is noise, not a reference.
_MIN_OBSERVATIONS = 20

#: …and they must come from this many different PATIENTS. Observation count
#: alone is not enough: 20 draws from one person describes that person's
#: disease, not a population, and adopting it as a reference range would encode
#: their illness as everyone's normal. This is the guard that matters at scale —
#: on a database with one patient's labs it correctly learns nothing.
_MIN_PATIENTS = 10


async def learn_from_distribution(db: AsyncSession,
                                  min_observations: int = _MIN_OBSERVATIONS,
                                  min_patients: int = _MIN_PATIENTS,
                                  ) -> dict[str, Range]:
    """Derive a range for analytes no lab reported one for, and REMEMBER it.

    "Unscored" was the wrong answer. If the analyte has been measured enough
    times, the central 95% of observed values IS a reference range — that is
    how reference ranges are established in the first place — and it improves
    as more patients arrive rather than going stale like a constant.

    The range must come from enough observations AND enough distinct patients:
    20 draws from one person describes that person's disease, not a population.
    On this database — one patient's labs — nothing qualifies, which is the
    correct answer rather than a missing feature. The learned range is written to
    `clinical_thresholds` with its provenance and the sample size, so the next
    request looks it up instead of recomputing, and a reviewer can see exactly
    what it was derived from.

    A percentile range is NOT a clinical target: it describes what this
    population's values look like, which for a cohort that is largely on
    dialysis may be a long way from healthy. `source` says so explicitly.
    """
    from app.models.clinical_threshold import ClinicalThreshold

    known = set((await db.execute(
        select(LabResult.test_name)
        .where(LabResult.reference_range_low.isnot(None),
               LabResult.reference_range_high.isnot(None))
        .distinct()
    )).scalars().all())
    known |= set((await db.execute(
        select(ClinicalThreshold.analyte)
    )).scalars().all())

    rows = (await db.execute(
        select(
            LabResult.test_name,
            func.percentile_cont(0.025).within_group(LabResult.value),
            func.percentile_cont(0.975).within_group(LabResult.value),
            func.count(LabResult.value),
            func.count(func.distinct(LabResult.user_id)),
        )
        .where(LabResult.value.isnot(None))
        .group_by(LabResult.test_name)
        .having(func.count(LabResult.value) >= min_observations)
        .having(func.count(func.distinct(LabResult.user_id)) >= min_patients)
    )).all()

    learned: dict[str, Range] = {}
    for name, low, high, n, patients in rows:
        if name in known or low is None or high is None or high <= low:
            continue
        learned[name] = (float(low), float(high))
        # store, so it is a lookup next time rather than a recomputation
        db.add(ClinicalThreshold(
            analyte=name, opt_low=float(low), opt_high=float(high),
            source=(f"derived: central 95% of {int(n)} values from "
                    f"{int(patients)} patients (population distribution, "
                    f"not a clinical target)"),
        ))
    if learned:
        try:
            await db.flush()
        except Exception:  # noqa: BLE001 - learning must never fail a score
            logger.warning("Could not persist learned ranges", exc_info=True)
    return learned


async def resolve(db: AsyncSession, user_id: int) -> dict[str, Range]:
    """Every range available for this patient, most specific first.

    Never raises and never invents: an analyte absent from the result simply has
    no reference, and the caller must treat it as unscoreable rather than
    substituting a default.
    """
    try:
        # Least specific first, so each layer overrides the one before it.
        ranges = await learn_from_distribution(db)
        ranges.update(await clinical_thresholds(db))
        ranges.update(await population_modes(db))
        ranges.update(await for_user(db, user_id))   # the patient's own wins
        return ranges
    except Exception:  # noqa: BLE001 - a missing range must not break a score
        logger.warning("Could not resolve reference ranges", exc_info=True)
        return {}
