"""Defaults for a new treatment, so a patient re-types as little as possible.

Three things a flowsheet should already know when it opens:

* today's **target weight**, from the mean of recent post-treatment weights;
* the **settings that rarely change** — physician, nurse, equipment, dialysate
  prescription — carried from the last completed session;
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
    for name in CARRY_FORWARD_FIELDS:
        value = getattr(last, name, None)
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
    defaults.carried_forward = carried

    defaults.access_type = last.dialysis_access_type
    defaults.access_kind = classify_access(last.dialysis_access_type)
    if defaults.access_kind == ACCESS_CATHETER:
        defaults.disabled_fields = list(FISTULA_ONLY_FIELDS)
        defaults.notes.append(
            "Your last treatment used a catheter, so the needle and bruit fields "
            "are switched off. Change the access type to turn them back on."
        )

    return defaults
