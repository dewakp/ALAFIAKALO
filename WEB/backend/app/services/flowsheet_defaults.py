"""Defaults for a new treatment, so a patient re-types as little as possible.

Three things a flowsheet should already know when it opens:

* today's **target weight**, from the mean of recent post-treatment weights;
* the **settings that rarely change** — physician, nurse, equipment lot and
  serial numbers, dialysate prescription — carried from the last completed
  session;
* **last treatment's post weight**, which is this treatment's *previous*
  weight and is how the unit computes today's fluid target;
* which **access-specific fields apply**, because a catheter has no needles.

Everything here is a *default*. Nothing is silently submitted: the caller shows
each value, the basis for it, and lets the patient change it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chronic_conditions import TherapySession

logger = logging.getLogger(__name__)

#: How many past treatments the target weight averages over.
TARGET_WEIGHT_WINDOW = 7

#: Statuses that mean the treatment actually happened.
COMPLETED_STATUSES = {"completed", "finished", "complete"}

#: A post weight outside this band is a recording error, not a patient.
POST_WEIGHT_PLAUSIBLE_KG = (25.0, 300.0)

#: Fields that only make sense for a needled access. A catheter has no needles
#: and no thrill or bruit, so leaving these enabled invites meaningless data.
FISTULA_ONLY_FIELDS = (
    "needle_gauge",
    "needle_length",
    "buttonhole_technique",
    "access_thrill_bruit",
    "post_access_thrill_bruit",
)

#: Settings that rarely change between treatments.
CARRY_FORWARD_FIELDS = (
    "attending_physician",
    "attending_nurse",
    "dialysis_access_type",
    "dialysate_volume_liters",
    "dialysate_lactate_meq",
    "dialysate_potassium_meq",
    "blood_flow_rate",
    "dialysate_flow_rate",
    "flow_fraction",
    "cartridge_lot",
    "sak_lot",
    "sak_number",
    "cycler_number",
    "warmer_serial",
    "control_panel_serial",
)

#: Defaults whose value comes from a DIFFERENT field on the last session.
#:
#: `previous_post_weight_kg` is not "the same as last time" — it IS last time's
#: post-treatment weight, which is how a unit computes today's fluid target.
#: The patient was re-typing a number the record already held: of 1,940
#: sessions carrying it, only 1,432 match the prior session's post weight, so
#: 508 were entered by hand and drifted.
CARRY_FORWARD_MAPPED = {
    "previous_post_weight_kg": "post_dialysis_weight_kg",
}

#: A weight has to be a person's before it can be a default. This record holds a
#: post-dialysis weight of 0.3 kg and pre-dialysis weights of 3.5 and 4.7 kg —
#: weighing-machine faults. Carrying one forward would seed the next treatment's
#: fluid target from garbage.
WEIGHT_PLAUSIBLE_KG = (20.0, 300.0)

#: Bath potassium outside this band is another field's value. 11 sessions record
#: 45 mEq/L, which is the lactate. Carrying that forward would seed a new
#: treatment with an impossible prescription AND skew the dialysis balance
#: model, so it is dropped from the defaults and flagged.
BATH_K_PLAUSIBLE_MEQ = (0.0, 4.0)

_CATHETER = re.compile(r"cath?eter|\bcather\b|\bcvc\b|perm[ -]?cath|tunn?el", re.I)
_NEEDLED = re.compile(r"fistula|graft|\bavf\b|\bavg\b|buttonhole", re.I)

ACCESS_CATHETER = "catheter"
ACCESS_NEEDLED = "needled"
ACCESS_UNKNOWN = "unknown"


def classify_access(access_type: str | None) -> str:
    """Bucket a free-text access description.

    The column is free text and messy — "Catheter. URJ", "AV Graft Left lower
    arm", and a misspelt "Cather. URJ" all appear — so this matches on substance
    rather than expecting a controlled vocabulary.

    A **graft counts as needled**: it is cannulated like a fistula, so needle
    fields apply. Only a catheter excludes them.

    Anything unrecognised returns `unknown` and nothing is disabled. Wrongly
    grey out a field and the patient cannot record what actually happened; that
    is worse than an extra enabled field.
    """
    text = (access_type or "").strip()
    if not text:
        return ACCESS_UNKNOWN
    # Check needled first: "AV Graft" must not be swallowed by a loose match.
    if _NEEDLED.search(text):
        return ACCESS_NEEDLED
    if _CATHETER.search(text):
        return ACCESS_CATHETER
    return ACCESS_UNKNOWN


@dataclass
class FlowsheetDefaults:
    target_weight_kg: float | None = None
    target_weight_basis: str | None = None
    target_weight_sample_size: int = 0

    access_type: str | None = None
    access_kind: str = ACCESS_UNKNOWN
    #: Fields the client should disable (not hide) for this access.
    disabled_fields: list[str] = field(default_factory=list)

    carried_forward: dict = field(default_factory=dict)
    carried_from_date: str | None = None
    #: {field: date it was last recorded}. Fields are carried from the most
    #: recent session that HAS them, which is not always the same session, so a
    #: single date would be wrong for most of them.
    carried_sources: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _is_completed(session: TherapySession) -> bool:
    status = str(getattr(session.status, "value", session.status) or "")
    return status.lower() in COMPLETED_STATUSES


async def recent_completed(
    db: AsyncSession, user_id: int, before: date, limit: int = 40
) -> list[TherapySession]:
    """Most recent completed sessions strictly before `before`."""
    from datetime import datetime, time

    rows = (await db.execute(
        select(TherapySession)
        .where(
            TherapySession.user_id == user_id,
            # scheduled_date is DateTime WITHOUT timezone — compare naive.
            TherapySession.scheduled_date < datetime.combine(before, time.min),
        )
        .order_by(TherapySession.scheduled_date.desc())
        .limit(limit)
    )).scalars().all()
    return [r for r in rows if _is_completed(r)]


def target_weight_from(sessions: list[TherapySession]) -> tuple[float | None, str, int]:
    """Mean post weight over the most recent treatments.

    A session with no recorded post weight is **skipped, not counted as zero**.
    Averaging in a zero would drag the target down and set an unsafe fluid
    removal goal — 230 of this patient's 2005 sessions have a null post weight,
    so this is the common case, not an edge case.
    """
    weights: list[float] = []
    low, high = POST_WEIGHT_PLAUSIBLE_KG
    for session in sessions:
        value = session.post_dialysis_weight_kg
        if value is None:
            continue
        if not (low <= float(value) <= high):
            continue
        weights.append(float(value))
        if len(weights) == TARGET_WEIGHT_WINDOW:
            break

    if not weights:
        return None, "No recorded post-treatment weights yet — please enter today's target.", 0

    mean = round(sum(weights) / len(weights), 1)
    if len(weights) < TARGET_WEIGHT_WINDOW:
        basis = (
            f"Average of your last {len(weights)} post-treatment "
            f"weight{'s' if len(weights) > 1 else ''} — fewer than "
            f"{TARGET_WEIGHT_WINDOW} are on file, so this is less settled than usual."
        )
    else:
        basis = f"Average of your last {TARGET_WEIGHT_WINDOW} post-treatment weights."
    return mean, basis, len(weights)


async def defaults_for(db: AsyncSession, user_id: int, today: date) -> FlowsheetDefaults:
    """Everything a new flowsheet can pre-fill for this patient."""
    sessions = await recent_completed(db, user_id, today)
    defaults = FlowsheetDefaults()

    if not sessions:
        defaults.notes.append(
            "This looks like your first recorded treatment, so nothing could be "
            "carried forward."
        )
        weight, basis, n = target_weight_from([])
        defaults.target_weight_kg, defaults.target_weight_basis = weight, basis
        return defaults

    defaults.target_weight_kg, defaults.target_weight_basis, defaults.target_weight_sample_size = (
        target_weight_from(sessions)
    )

    last = sessions[0]
    defaults.carried_from_date = str(last.scheduled_date)[:10]

    carried: dict = {}
    sources: dict = {}

    def _last_recorded(field_name: str):
        """The most recent session that actually HAS this field, and its date.

        Scanning only the latest session loses anything that session left
        blank — and on this record the last treatment recorded no cycler,
        warmer, cartridge lot or control panel, though all four are recorded
        1,833-1,964 times and were present a fortnight earlier. "Default to the
        last recorded value" means the last time it was recorded, not the last
        time anything was.
        """
        for candidate in sessions:
            found = getattr(candidate, field_name, None)
            if found is not None and str(found).strip() != "":
                return found, str(candidate.scheduled_date)[:10]
        return None, None

    for name in CARRY_FORWARD_FIELDS:
        value, seen_on = _last_recorded(name)
        if value is None:
            continue
        if name == "dialysate_potassium_meq":
            low, high = BATH_K_PLAUSIBLE_MEQ
            if not (low <= float(value) <= high):
                defaults.notes.append(
                    f"Last session recorded a dialysate potassium of {value:g} mEq/L, "
                    "which is outside the usual range, so it was not carried forward."
                )
                continue
        carried[name] = value
        sources[name] = seen_on

    for target, source in CARRY_FORWARD_MAPPED.items():
        value, seen_on = _last_recorded(source)
        if value is None:
            continue
        low, high = WEIGHT_PLAUSIBLE_KG
        if target.endswith("_kg") and not (low <= float(value) <= high):
            defaults.notes.append(
                f"Last treatment recorded a weight of {value:g} kg, which is not "
                "a plausible body weight, so it was not carried forward."
            )
            continue
        carried[target] = value
        sources[target] = seen_on

    defaults.carried_forward = carried
    defaults.carried_sources = sources

    # Say so where a value is not from the last treatment, or the patient has no
    # way to know they are looking at a fortnight-old cycler number.
    stale = sorted(f for f, d in sources.items()
                   if d and d != defaults.carried_from_date)
    if stale:
        defaults.notes.append(
            "Some settings came from an earlier treatment because the last one "
            "did not record them: " + ", ".join(stale.replace("_", " ") for stale in stale) + "."
        )

    defaults.access_type = last.dialysis_access_type
    defaults.access_kind = classify_access(last.dialysis_access_type)
    if defaults.access_kind == ACCESS_CATHETER:
        defaults.disabled_fields = list(FISTULA_ONLY_FIELDS)
        defaults.notes.append(
            "Your last treatment used a catheter, so the needle and bruit fields "
            "are switched off. Change the access type to turn them back on."
        )

    return defaults
