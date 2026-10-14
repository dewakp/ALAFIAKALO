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

#: The therapy space, as WHO BRANCHES — not as a list of items chosen here.
#:
#: Operator, 2026-10-14: *"hard-coded enum for therapy will need a
#: comprehensive list … current model lacks comprehensive list"*.
#:
#: The previous version named **10** codes while the branch they came from
#: holds **31**, every one already in the bundled catalog. Picking ten of
#: thirty-one is typing them with extra steps: it covers the therapies someone
#: happened to think of (§3an), and a patient on apheresis, cardiac
#: rehabilitation or palliative care could not say so at all.
#:
#: So the ROOTS are declared and the catalog supplies the members. Adding a
#: therapy means WHO published one, not that someone edited this file.
#:
#: Each root states WHY it is in the space — not what it is called. The
#: catalog supplies the title; a reason nobody can audit is a curation
#: decision in disguise, so the first version's "apheresis" and "palliative
#: care" were labels and a test refused them.
THERAPY_BRANCHES = {
    "QB4":  "a device the patient depends on to live — aspirator, respirator, "
            "renal dialysis, artificial heart, wheelchair. Dependence is a "
            "standing therapeutic state, so it belongs to the same axis as "
            "the treatment that maintains it rather than to a diagnosis",
    "QB94": "dialysis, where WHO already separates the two modalities this "
            "product built flowsheets for — and carries the preparatory and "
            "unspecified forms, which a patient starting next week needs",
    "QB95": "rehabilitation the patient attends on a course — cardiac, "
            "physical, speech, psychotherapy, occupational, orthoptic and "
            "the alcohol, drug and tobacco programmes. Twelve codes the "
            "curated set could not express at all",
    "QB96": "radiotherapy, which is delivered in repeated sessions over "
            "weeks, so it is a regimen the patient is ON rather than a "
            "procedure that happened to them (§3bb holds the operations)",
    "QB97": "chemotherapy for neoplasm — cyclical, and the case the operator "
            "named when asking for a management score separate from Ω",
    "QB98": "transfusion with no diagnosis reported, which on this record is "
            "ordinary supportive care in anaemia rather than an emergency "
            "event, and compounds with dialysis and iron",
    "QB99": "apheresis — plasma exchange and the related procedures, an "
            "extracorporeal therapy run as a course like dialysis",
    "QB9A": "preparation for a treatment not yet given: a patient being "
            "worked up is already under care, and this is how they say so "
            "before any session exists to prove it",
    "QB9B": "palliative care, which governs what every other target is for. "
            "Omitting it would make the sickest patients the ones unable to "
            "state what their care is",
    "QB9C": "allergen immunotherapy — a desensitisation course, and the one "
            "therapy here that directly interacts with the declared "
            "allergies §3az matches food and drugs against",
}

#: Deliberately NOT branches, with the reason, so the exclusion is a stated
#: decision rather than an oversight someone has to re-derive:
#:
#:   QB80-QB86  surgical contacts — §3bb already models those as
#:              `surgical_procedures`, and two homes for one fact is the
#:              drift this codebase keeps paying for
#:   QB90-QB93  ear and body piercing, repeat prescriptions, orthodontic
#:              care — contacts with a service, not therapy a patient is on
#:   QB9Y/QB9Z  "other specified" and "unspecified" at the TOP level, which
#:              name nothing a patient could recognise as their treatment
#:
#: ⚠️ The `.Y`/`.Z` members INSIDE a root are kept, and that is not a
#: contradiction. "Care involving dialysis, unspecified" is a real statement —
#: the patient is on dialysis and the modality is not recorded — and refusing
#: it would force a guess between the two screens, which is the §3at collapse
#: this table exists to undo. A bare `QB9Z` states only that a contact
#: happened, which is not a therapy anybody is on.

#: Which codes open a DEDICATED screen. Everything else in the space is still
#: declarable and opens the Therapies group.
#:
#: ⚠️ This is a routing table — code to SCREEN NAME. Inventing what a code
#: MEANS would be the §3ad violation; choosing which of WHO's codes this
#: product has built a flowsheet for is not.
THERAPY_CODE_SURFACE = {
    "QB94.1": "hemodialysis",
    "QB94.2": "peritoneal_dialysis",
}

#: Values stored before the codes existed (2026-10-13, one day). Read-only
#: compatibility so a declaration made then keeps working; nothing writes them.
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


def _in_branch(code: str, root: str) -> bool:
    """ICD-11 children are `ROOT.N` for a stem code and `ROOTx` for a block.

    ⚠️ The first version tested `code.startswith(root + ".")`, which is right
    for QB94 -> QB94.1 and **silently wrong for QB4 -> QB40**: every
    dependence code was dropped and the "comprehensive" list quietly lost six
    entries. Caught by printing the derived set and counting it, not by
    reading the predicate (§3av).
    """
    return code == root or code.startswith(root + ".") or (
        len(root) == 3 and code.startswith(root) and len(code) > 3
    )


def therapy_codes() -> list[str]:
    """Every code in the therapy space, from the catalog. Comprehensive."""
    from app.services.icd11_catalog import all_codes

    out = [c for c in all_codes()
           if any(_in_branch(c, root) for root in THERAPY_BRANCHES)]
    return sorted(out)


def _group_title(root: str, member_titles: list[str]) -> str | None:
    """A heading for a branch, from the CATALOG or from its own members.

    Most roots are themselves codes and carry WHO's title (`QB94` is "Care
    involving dialysis"). `QB4` is a block, absent from the MMS linearization,
    and typing a heading for it would be §3ad's "never type a code from
    memory" applied to the label instead of the code.

    So where the root has no title, the shared word-prefix of its members is
    used — all seven QB4 codes begin "Dependence on …", which yields
    "Dependence on" without anybody inventing a phrase. If the members share
    nothing, the client gets None and groups under the code.
    """
    from app.services.icd11_catalog import get_icd11_by_code

    entry = get_icd11_by_code(root)
    if entry is not None:
        return entry.title
    if not member_titles:
        return None
    words = [t.split() for t in member_titles]
    shared: list[str] = []
    for column in zip(*words):
        if len(set(column)) != 1:
            break
        shared.append(column[0])
    text = " ".join(shared).strip(" ,;:-")
    return text or None


def therapy_options() -> list[dict]:
    """The option set a patient chooses from, with WHO's own titles.

    Served to every client so none of them carries a therapy list — four
    copies of one vocabulary was the §3ad violation this replaced, and a
    curated ten of thirty-one was the next one.

    `group`/`group_title` travel so a client can present 32 codes as the
    branches they are **without reading a code prefix to decide what a code
    means**. A client that split on the dot would be making the classification
    decision this module exists to keep server-side.

    A code missing from the catalog is DROPPED rather than labelled from
    memory, the same discipline `test_icd11_catalog` applies to aliases.
    """
    from app.services.icd11_catalog import get_icd11_by_code

    by_root: dict[str, list[tuple[str, str]]] = {}
    for code in therapy_codes():
        entry = get_icd11_by_code(code)
        if entry is None:
            continue
        for root in THERAPY_BRANCHES:
            if _in_branch(code, root):
                by_root.setdefault(root, []).append((code, entry.title))
                break

    out = []
    for root, members in by_root.items():
        heading = _group_title(root, [title for _, title in members])
        for code, title in members:
            out.append({
                "code": code,
                "title": title,
                "group": root,
                "group_title": heading,
                "surface": THERAPY_CODE_SURFACE.get(code, "therapy_other"),
            })
    return out


def _known_codes() -> frozenset[str]:
    """The whole declarable space, cached per process."""
    global _KNOWN
    if _KNOWN is None:
        _KNOWN = frozenset(therapy_codes())
    return _KNOWN


_KNOWN: frozenset[str] | None = None


async def therapy_switches(db, user_id: int) -> dict[str, dict]:
    """Every therapy this patient has a STATEMENT about, keyed by code.

    Operator, 2026-10-14: *"a comprehensive list with items zeroed out (no
    impact) when not present (like a switch)"*.

    Three states, and the row is what separates them:

        absent from this dict   never asked           -> unknown
        receiving = False       explicitly not on it  -> a measured ZERO
        receiving = True        undergoing it         -> contributes

    A set could only ever hold the third. Absence meant "not on it" AND
    "nobody asked" at once — §3at's checkbox, where *"absent, the finding
    that needs to shout, was indistinguishable from a box nobody had
    touched"*, applied to a patient's whole therapy picture.

    `regimen` travels so a reader can tell a COMBINATION from a coincidence:
    therapies sharing a label are given as one treatment. What a combination
    MEANS is not asserted anywhere — naming an interaction is a clinical
    claim (§3an).
    """
    from app.models.chronic_conditions import ChronicCondition, ConditionTherapy

    rows = (await db.execute(
        select(ConditionTherapy, ChronicCondition.condition_name)
        .join(ChronicCondition,
              ChronicCondition.id == ConditionTherapy.condition_id)
        .where(ChronicCondition.user_id == user_id)
    )).all()

    out: dict[str, dict] = {}
    for therapy, condition_name in rows:
        code = (therapy.therapy_code or "").upper()
        if code not in _known_codes():
            continue        # a code outside the space states nothing
        prior = out.get(code)
        # Receiving on ANY condition wins: a patient on dialysis for ESRD is
        # on dialysis, whatever a second condition records.
        if prior is None or (therapy.receiving and not prior["receiving"]):
            out[code] = {
                "code": code,
                "receiving": bool(therapy.receiving),
                "regimen": therapy.regimen,
                "condition": condition_name,
                "started_on": therapy.started_on,
                "ended_on": therapy.ended_on,
            }
    return out


def regimens(switches: dict[str, dict]) -> dict[str, list[str]]:
    """Codes grouped by the regimen they are given as part of.

    The compounding mechanism, and deliberately the whole of it: it reports
    what the patient says is given TOGETHER. It does not decide that a
    combination has an effect its members do not — that is a clinical claim,
    and inventing one is what §3an forbids.
    """
    out: dict[str, list[str]] = {}
    for code, row in switches.items():
        if row["receiving"] and row.get("regimen"):
            out.setdefault(row["regimen"], []).append(code)
    return {k: sorted(v) for k, v in sorted(out.items())}


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
        if code in _known_codes():
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
        if code not in _known_codes():
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

    # The SWITCH table is the authority where it has a statement. A row saying
    # `receiving = False` is a measured ZERO and must retire the screen, which
    # the legacy set could not express at all — absence there meant "not on it"
    # and "nobody asked" at once.
    switches = await therapy_switches(db, user_id)
    for code, row in switches.items():
        if row["receiving"]:
            declared.setdefault(code, row["condition"] or "a recorded condition")

    # The legacy column still speaks for a condition the switch table has no
    # statement about, so a declaration made before the table existed keeps
    # working. A statement always beats a membership.
    for condition in conditions:
        for therapy in declared_therapy_types(condition):
            if therapy in switches:
                continue        # the switch already answered, either way
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
