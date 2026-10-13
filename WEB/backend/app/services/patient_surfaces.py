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

from app.models.chronic_conditions import TherapySession, TherapyType
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

def declared_therapy_types(condition) -> set[str]:
    """The `TherapyType` values a condition DECLARES it is treated with.

    Operator, 2026-10-13: *"Only PD patients must see PD. Let user add Therapy
    types in Condition and profile. Same as other health conditions. use
    condition to determine the Therapy switch."*

    ⚠️ **This replaces a hand-typed keyword dict.** `_CONDITION_HINTS` matched
    condition text against `("peritoneal", " pd ", "capd", "ccpd")` and
    `("hemodialysis", "haemodialysis", "esrd", "dialysis", …)` — §3an's
    forbidden shape, *"covers only the condition someone happened to think of,
    cannot say why, has no source, never improves, and goes stale silently"* —
    deciding which clinical screen a patient could reach. A condition recorded
    as "ESKD" or "renal replacement therapy" matched nothing, and one reading
    "history of dialysis" matched everything.

    Now the patient says so, and the app reads what they said.

    Unrecognised values are DISCARDED rather than repaired: silently
    correcting what someone wrote about their own treatment invents a clinical
    fact (§3am — naming a unit is not an override), and the API validates on
    the way in so a stored value should already be an enum member.
    """
    raw = getattr(condition, "therapy_types", None)
    if not raw:
        return set()
    known = {t.value for t in TherapyType}
    return {part.strip().lower() for part in str(raw).split(",")
            if part.strip().lower() in known}


def validate_therapy_types(values) -> str | None:
    """Client-supplied names → the stored comma-separated string, or None.

    §3ad: the client never decides what a code means. An unrecognised name is
    dropped rather than stored, so a typo cannot silently become a modality
    nobody offers a screen for.

    An empty list stores NULL — "not stated", which is a different fact from
    "no therapy" and must stay distinguishable (§3aa).
    """
    if not values:
        return None
    known = {t.value: t.value for t in TherapyType}
    known.update({t.name.lower(): t.value for t in TherapyType})
    kept = []
    for v in values:
        key = str(v).strip().lower().replace(" ", "_").replace("-", "_")
        resolved = known.get(key)
        if resolved and resolved not in kept:
            kept.append(resolved)
    return ",".join(kept) or None


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
    """Derive the surface set from what the record actually holds.

    **A DECLARATION GOVERNS; sessions are history.** Operator, 2026-10-13:
    *"user can choose the therapy or therapies they undergo and only those
    therapies are surfaced in navigation."*

    Measured before this rule existed: user 63 declared **only** peritoneal
    dialysis and was still offered the HD flowsheet, because 2,035 HD sessions
    opened it regardless — both modalities on screen for a patient who had just
    said which one they are on. A declaration that the navigation overrules is
    not a choice.

    So the precedence is:

      declared anything  -> the DECLARATION decides which treatment screens
                            appear. It is a statement about what the patient
                            undergoes NOW.
      declared nothing   -> fall back to the sessions on record. We cannot
                            tell, and stranding a patient away from their own
                            flowsheet is the worse error.

    **Therapy History is offered either way.** A patient who moved from
    haemodialysis to PD stops needing the HD flowsheet and never stops owning
    their HD record: hiding it would hide their own history from them (§3aa).
    Losing the screen you work in daily and losing your past are different
    harms, and only the first is what a declaration should cause.
    """
    s = Surfaces()
    for name in CORE:
        s.offer(name, "always available")

    # ── What the patient DECLARED they undergo ───────────────────────────
    conditions = list(await sources.conditions(db, user_id, active_only=True))
    declared: dict[str, str] = {}          # therapy -> the condition it treats
    for condition in conditions:
        for therapy in declared_therapy_types(condition):
            declared.setdefault(
                therapy, getattr(condition, "name", None) or "a recorded condition")

    # ── What the record SHOWS they have had ──────────────────────────────
    rows = (await db.execute(
        select(TherapySession.therapy_type, func.count(TherapySession.id))
        .where(TherapySession.user_id == user_id)
        .group_by(TherapySession.therapy_type)
    )).all()
    sessions: dict[str, int] = {}
    for therapy_type, count in rows:
        if not count:
            continue
        raw = getattr(therapy_type, "value", therapy_type)
        sessions[str(raw).lower()] = count

    # ── The declaration governs the treatment screens ────────────────────
    if declared:
        for therapy, condition_name in declared.items():
            # A therapy this map does not name — chemotherapy, infusion,
            # phototherapy — still opens the group rather than vanishing.
            surface = _MODALITY_SURFACE.get(therapy, "therapy_other")
            s.offer(surface, f"declared therapy for {condition_name}")
        s.offer("therapies", "declared therapy")
    else:
        for therapy, count in sessions.items():
            surface = _MODALITY_SURFACE.get(therapy, "therapy_other")
            s.offer(surface,
                    f"{count} {therapy.replace(chr(95), chr(32))} session(s) on record")
        if sessions:
            s.offer("therapies", "therapy sessions on record")

    # ── History is owned, not prescribed ─────────────────────────────────
    if sessions:
        s.offer("therapies", "therapy sessions on record")
        s.offer("therapy_history",
                f"{sum(sessions.values())} session(s) on record")
    elif declared:
        s.offer("therapy_history", "declared therapy")

    if conditions:
        s.offer("conditions_active", f"{len(conditions)} active condition(s)")

    return s
