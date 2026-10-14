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

#: The therapy option set, as WHO CODES — not as names typed here.
#:
#: Operator, 2026-10-13: *"against the rule"*. Correct. §3ad says the catalog
#: is the authority and a code is never typed from memory, and I built this
#: option set as a hand-written enum mirrored into four places (the backend
#: list, web, iOS, Android) **without checking whether WHO already coded it**.
#: It does:
#:
#:     QB94.1   Care involving extracorporeal dialysis    <- haemodialysis
#:     QB94.2   Care involving peritoneal dialysis
#:     QB96     Contact with health services for radiotherapy session
#:     QB97     Contact with health services for chemotherapy session …
#:     QB98     Blood transfusion without reported diagnosis
#:     QB95.1   Physical rehabilitation
#:     QB95.4   Psychotherapy
#:     QB95.5   Speech therapy
#:     QB95.7   Occupational therapy or vocational rehabilitation
#:     QB9C     Allergen immunotherapy
#:
#: Every one verified present in the bundled 2025-01 MMS linearization before
#: being written here, the same way `build_icd11_catalog.py` is the only source
#: of a condition code. **The LABELS are WHO's**, read from the catalog at
#: runtime, so no therapy name is typed in this codebase at all — which is what
#: lets the clients stop carrying their own copies.
#:
#: ⚠️ Selecting WHICH codes offer a surface is a routing decision and stays
#: here; inventing what a code MEANS would not. The right-hand side is a
#: screen name, never a clinical claim.
THERAPY_CODE_SURFACE = {
    "QB94.1": "hemodialysis",
    "QB94.2": "peritoneal_dialysis",
    "QB96": "therapy_other",
    "QB97": "therapy_other",
    "QB98": "therapy_other",
    "QB95.1": "therapy_other",
    "QB95.4": "therapy_other",
    "QB95.5": "therapy_other",
    "QB95.7": "therapy_other",
    "QB9C": "therapy_other",
}

#: Values stored before the codes existed (2026-10-13, one day). Read-only
#: compatibility so a declaration made this morning keeps working; nothing
#: writes these any more.
_LEGACY_TO_CODE = {
    "hemodialysis": "QB94.1",
    "dialysis": "QB94.1",
    "peritoneal_dialysis": "QB94.2",
    "radiation_therapy": "QB96",
    "chemotherapy": "QB97",
    "blood_transfusion": "QB98",
    "physical_therapy": "QB95.1",
    "occupational_therapy": "QB95.7",
    "immunotherapy": "QB9C",
}

#: Therapy SESSIONS still carry `TherapyType`; that records what a session WAS
#: and is a different fact from what a patient declares they undergo.
_MODALITY_SURFACE = {
    "hemodialysis": "hemodialysis",
    "dialysis": "hemodialysis",          # the generic value predates the split
    "peritoneal_dialysis": "peritoneal_dialysis",
}


def therapy_options() -> list[dict]:
    """The option set a patient chooses from, with WHO's own titles.

    Served to every client so none of them carries a hand-typed therapy list —
    four copies of one vocabulary was the §3ad violation this replaces.

    A code missing from the catalog is DROPPED rather than labelled from
    memory: `test_icd11_catalog` already fails the build on an alias pointing
    at a code that is not in the file, and the same discipline applies here.
    """
    from app.services.icd11_catalog import get_icd11_by_code

    out = []
    for code, surface in THERAPY_CODE_SURFACE.items():
        entry = get_icd11_by_code(code)
        if entry is None:
            continue
        out.append({"code": code, "title": entry.title, "surface": surface})
    return out


def declared_therapy_types(condition) -> set[str]:
    """The ICD-11 therapy codes a condition DECLARES it is treated with.

    Operator, 2026-10-13: *"Only PD patients must see PD. Let user add Therapy
    types in Condition and profile … use condition to determine the Therapy
    switch."*

    ⚠️ **This replaced a hand-typed keyword dict, and then its replacement was
    hand-typed too.** `_CONDITION_HINTS` matched condition TEXT against
    `("peritoneal", " pd ", "capd")` — §3an's forbidden shape, deciding which
    clinical screen a patient could reach. The declared field fixed that and
    introduced a second violation: an ALAFIA-private enum mirrored into four
    files while **WHO already codes this** (QB94.1, QB94.2, QB96, QB97 …).
    Operator: *"against the rule"*. The values are codes now.

    Values written before the codes existed still read, because a declaration
    made this morning must not stop working — but nothing writes them.

    Anything unrecognised is DISCARDED, never repaired: silently correcting
    what someone recorded about their own treatment invents a clinical fact.
    """
    raw = getattr(condition, "therapy_types", None)
    if not raw:
        return set()
    out: set[str] = set()
    for part in str(raw).split(","):
        token = part.strip()
        if not token:
            continue
        code = token.upper()
        if code in THERAPY_CODE_SURFACE:
            out.add(code)
            continue
        legacy = _LEGACY_TO_CODE.get(token.lower())
        if legacy:
            out.add(legacy)
    return out


def validate_therapy_types(values) -> str | None:
    """Client-supplied codes → the stored comma-separated string, or None.

    §3ad: the client never decides what a code means. A code outside the
    option set is dropped rather than stored, so a typo cannot silently become
    a therapy nobody offers a screen for — and the code must EXIST in the
    bundled WHO catalog, which is the same check `_apply_icd11` makes of a
    condition's own code.

    An empty list stores NULL — "not stated", a different fact from "no
    therapy" (§3aa).
    """
    if not values:
        return None
    kept: list[str] = []
    for v in values:
        token = str(v).strip()
        code = token.upper()
        if code not in THERAPY_CODE_SURFACE:
            code = _LEGACY_TO_CODE.get(token.lower().replace(" ", "_")
                                       .replace("-", "_"), "")
        if code and code not in kept:
            kept.append(code)
    return ",".join(sorted(kept)) or None


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
            surface = THERAPY_CODE_SURFACE.get(therapy, "therapy_other")
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
