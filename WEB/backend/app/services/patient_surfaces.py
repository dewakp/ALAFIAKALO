# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Which screens this patient's record justifies.

Operator, 2026-10-12, after asking more than once:

  *"Primary goal == patient specific surfacing. for example someone who has
  listed no condition need not see therapies. they still do despite my repeated
  request. HD patient need not see PD in navigation."*

The web sidebar is a **static 62-entry list**, so every account sees HD
Flowsheet, PD Report, Therapy History and Pharmacy whatever their record holds.
Measured on production 2026-10-12: **2,035 therapy sessions, every one
`HEMODIALYSIS`, belonging to one user. Zero peritoneal sessions exist for any
account on the platform** — so "PD Report" has never been a live screen for
anybody, and it sits one row under the HD screen the one dialysis patient
actually uses.

**The backend decides and the clients render.** Three clients each applying
their own rule is the drift this codebase keeps paying for (§3), and a surface
rule is a clinical statement about what a patient has.

Two rules, and the second is the one that keeps this safe:

1. A surface is offered when the record INDICATES it — a condition, or a
   therapy modality on file.
2. **A surface is offered whenever it HOLDS DATA, regardless of rule 1.**
   Absence of a diagnosis is not absence of records (§3aa). A patient whose
   conditions were never coded still has their own sessions, and hiding the
   screen would hide their history from them. Data always wins.

`CORE` is never gated: you cannot hide the screen where a condition would be
added, or a patient with an empty record has nowhere to begin.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chronic_conditions import TherapySession
from app.services import clinical_sources as sources

#: Surfaces every account sees. Gating these strands a new or uncoded patient.
CORE = (
    "dashboard", "ask_alafia", "insights", "trends", "wellness", "calendar",
    "meals", "nutrition", "conditions", "medications", "labs", "logs",
    "hospital_history", "data_sharing", "community", "profile",
)

#: Dialysis modalities, by the `TherapyType` value that evidences each.
_MODALITY_SURFACE = {
    "hemodialysis": "hemodialysis",
    "dialysis": "hemodialysis",          # the generic value predates the split
    "peritoneal_dialysis": "peritoneal_dialysis",
}

#: Condition text that indicates a modality where no session is on file yet —
#: a patient starting dialysis needs the screen BEFORE their first session.
#: Deliberately small and matched case-folded; data is the primary evidence and
#: this only ever ADDS a surface.
_CONDITION_HINTS = {
    "peritoneal_dialysis": ("peritoneal", " pd ", "capd", "ccpd"),
    "hemodialysis": ("hemodialysis", "haemodialysis", "end-stage renal",
                     "end stage renal", "esrd", "dialysis"),
}


@dataclass
class Surfaces:
    """What to offer, and why — the reason travels so a client can explain it
    and so the decision is auditable rather than mysterious."""
    offered: set[str] = field(default_factory=set)
    because: dict[str, str] = field(default_factory=dict)

    def offer(self, surface: str, reason: str) -> None:
        # First reason wins: DATA is evaluated before hints, so a surface that
        # holds records says so rather than citing a diagnosis.
        self.offered.add(surface)
        self.because.setdefault(surface, reason)

    def as_payload(self) -> dict:
        return {
            "offered": sorted(self.offered),
            "because": dict(sorted(self.because.items())),
        }


async def for_user(db: AsyncSession, user_id: int) -> Surfaces:
    """Derive the surface set from what the record actually holds."""
    s = Surfaces()
    for name in CORE:
        s.offer(name, "always available")

    # ── Therapy modalities, from sessions that EXIST ─────────────────────
    rows = (await db.execute(
        select(TherapySession.therapy_type, func.count(TherapySession.id))
        .where(TherapySession.user_id == user_id)
        .group_by(TherapySession.therapy_type)
    )).all()

    any_therapy = False
    for therapy_type, count in rows:
        if not count:
            continue
        any_therapy = True
        raw = getattr(therapy_type, "value", therapy_type)
        key = str(raw).lower()
        surface = _MODALITY_SURFACE.get(key)
        if surface:
            s.offer(surface, f"{count} {key.replace('_', ' ')} session(s) on record")
        else:
            # Chemotherapy, infusion, phototherapy … each is a real therapy and
            # must not be silently dropped because this map does not name it.
            s.offer("therapy_other", f"{count} {key.replace('_', ' ')} session(s) on record")

    if any_therapy:
        s.offer("therapies", "therapy sessions on record")
        s.offer("therapy_history", "therapy sessions on record")

    # ── Conditions can indicate a modality before the first session ──────
    conditions = list(await sources.conditions(db, user_id, active_only=True))
    text = " ".join(
        f" {(getattr(c, 'name', '') or '').lower()} "
        f"{(getattr(c, 'icd11_title', '') or '').lower()} "
        for c in conditions
    )
    for surface, hints in _CONDITION_HINTS.items():
        if any(h in text for h in hints):
            s.offer(surface, "indicated by a recorded condition")
            s.offer("therapies", "indicated by a recorded condition")
            s.offer("therapy_history", "indicated by a recorded condition")

    if conditions:
        s.offer("conditions_active", f"{len(conditions)} active condition(s)")

    return s
