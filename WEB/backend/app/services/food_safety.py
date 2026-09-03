"""What this patient should avoid, and what would help them — one decider.

Two corrections are baked into this module's shape, both of which the first
version got wrong.

**A condition trigger is not an allergy.** An allergy is immune-mediated and is
declared by the patient in their profile. Favism is enzymatic. Coeliac disease
is autoimmune. Sickle cell has its own precipitants. They are all enforced the
same way — the food does not reach the patient — but they must be EXPLAINED
differently, so `kind` and `mechanism` travel with every restriction instead of
collapsing into one undifferentiated "forbidden" list.

**Avoidance is only half of nutrition.** The first version modelled restriction
and nothing else, which makes ALAFIA a list of prohibitions rather than an
advisor. Conditions also have MITIGATORS: antioxidants that reduce oxidative
stress in G6PD deficiency; B12, folate and iron — with vitamin C for absorption
— that support red cell production in anaemia. Those belong in a plan as
positive guidance, so `Guidance` carries `favour` beside `avoid`.

**Nothing here is hardcoded.** An earlier version held a nine-line dict mapping
"g6pd" to four bean names. That is the mistake §3ad and §3c already name: it
covers only the condition someone thought of, cannot say why, has no source and
never improves. Condition knowledge is resolved once and stored by
`condition_nutrition_service`; this module only decides what to do with it.

Matching errs toward flagging. A false positive costs the patient one menu
option; a false negative is the thing this module exists to prevent. Terms match
on word equality or as either half of a compound, so "berry" catches
"blueberries" and "apple" catches "applesauce" — the latter found only by
driving a real plan against a real profile.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# Words that qualify a food without changing what it is. "Raw Apples" is an
# apple allergy; the patient is not safe from a cooked one by this module's
# reckoning, and deciding otherwise is a clinical call we must not make.
_QUALIFIERS = frozenset({
    "raw", "fresh", "dried", "cooked", "ripe", "whole", "canned", "frozen",
    "steamed", "baked", "boiled", "grilled", "roasted", "plain", "unsweetened",
})

# Restriction kinds, in the order a clinician would rank their certainty.
ALLERGY = "allergy"
INTOLERANCE = "intolerance"
CONDITION_TRIGGER = "condition_trigger"


@dataclass(frozen=True)
class Restriction:
    """Something the patient must not be offered, and why."""

    term: str            # normalised, singular, lowercase — what we match on
    label: str           # what the patient wrote or the fact named
    kind: str            # allergy | intolerance | condition_trigger
    reason: str          # patient-facing explanation
    mechanism: str | None = None

    @property
    def source(self) -> str:  # kept for callers written against the old field
        return self.kind


@dataclass(frozen=True)
class Encouragement:
    """Something that would help this patient, and why."""

    subject: str
    subject_kind: str    # food | nutrient | ingredient
    reason: str
    mechanism: str | None = None


@dataclass(frozen=True)
class Guidance:
    """Both directions. A plan needs each."""

    avoid: list[Restriction] = field(default_factory=list)
    favour: list[Encouragement] = field(default_factory=list)
    # Guidance that one condition asks for and another limits. NOT hidden:
    # silently dropping it left the model unable to reason about a real
    # clinical trade-off, and the resolution often depends on the patient's
    # measured state rather than on their diagnosis labels.
    tensions: list[str] = field(default_factory=list)
    # What the record actually measures, and where it contradicts a label.
    observations: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.avoid or self.favour or self.tensions
                    or self.observations or self.contradictions)


def profile_list(value: Any) -> list[str]:
    """Profile list fields, however they were stored.

    The Profile screen writes COMMA-SEPARATED TEXT ("Penicilin, Latex,
    Heparine"), not JSON — its own placeholder says so. Some older rows are JSON
    arrays. Canon §3ag: `json.loads()` on the comma form is what took down
    /personalization/*, so both shapes are accepted here and nowhere else.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except ValueError:
            pass
    return [part.strip() for part in text.split(",") if part.strip()]


# Words ending in -us/-is/-ss are not plurals. Stripping the s produced
# "citru" and "phosphoru" in real resolved guidance.
_NOT_PLURAL_SUFFIXES = ("ss", "us", "is", "as", "os")


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("oes"):
        return word[:-2]
    if (len(word) > 3 and word.endswith("s")
            and not word.endswith(_NOT_PLURAL_SUFFIXES)):
        return word[:-1]
    return word


def _normalise(phrase: str) -> str:
    """Lowercase, drop qualifiers, singularise each remaining word."""
    words = [w for w in re.split(r"[^a-z0-9]+", phrase.lower()) if w]
    kept = [_singular(w) for w in words if w not in _QUALIFIERS]
    return " ".join(kept)


# Subjects that are not food and must never appear as meal guidance. Matched
# by shape, not by a list of drug names: anything the resolver returns that is
# really a THERAPY belongs on the medication screen, not in a meal plan.
_NOT_FOOD_MARKERS = ("binder", "supplement tablet", "injection", "infusion",
                     "medication", "drug", "therapy")


def _is_food_advice(subject: str) -> bool:
    low = subject.lower()
    return not any(m in low for m in _NOT_FOOD_MARKERS)


def _conditional(subject: str) -> bool:
    """Advice the system cannot evaluate for this patient.

    "Potassium (in non-CKD stage 5 patients)" is a clinician's caveat, not an
    instruction. Surfacing it to a planner invites it to guess which side of
    the caveat the patient falls on.
    """
    low = subject.lower()
    return any(m in low for m in ("in non-", "if not", "unless", "stage-dependent",
                                  "patients)", "when not"))


def build_guidance(user: Any, facts: Iterable[Any] = (),
                   nutrient_limits: Iterable[str] = ()) -> Guidance:
    """Everything this patient should avoid and should favour.

    `facts` are `NutritionFact`s from `condition_nutrition_service` — resolved
    from their diagnoses and stored, never written here. Passing none yields
    profile-declared allergies and intolerances only, which is the correct
    behaviour when the knowledge tier is unavailable: a degraded guard that
    still honours what the patient told us beats no guard.

    `nutrient_limits` are the nutrients CAPPED for this patient by
    `compute_goals` ("potassium", "phosphorus", "sodium"…), and they arbitrate
    between conditions that disagree.

    They disagree often, and dangerously. This patient carries both
    hypertension and ESRD: hypertension resolves to "prioritise potassium,
    fruit, legumes, nuts" — textbook DASH — while ESRD resolves to "avoid
    fruit, avoid nuts, potassium is a hyperkalemia risk". Taking the union
    would hand the planner an instruction to load a dialysis patient with
    potassium. The patient's own computed limit is the tie-break, because it
    already accounts for every condition they have.
    """
    avoid: dict[str, Restriction] = {}
    favour: dict[str, Encouragement] = {}

    def _add_avoid(raw: str, kind: str, reason: str, mechanism: str | None = None) -> None:
        term = _normalise(raw)
        if term and term not in avoid:
            avoid[term] = Restriction(term=term, label=raw, kind=kind,
                                      reason=reason, mechanism=mechanism)

    for item in profile_list(getattr(user, "allergies", None)):
        _add_avoid(item, ALLERGY, f"allergy: {item}")
    for item in profile_list(getattr(user, "food_intolerances", None)):
        _add_avoid(item, INTOLERANCE, f"food intolerance: {item}")

    for f in facts or ():
        relation = getattr(f, "relation", None)
        subject = getattr(f, "subject", None)
        if not subject:
            continue
        mechanism = getattr(f, "mechanism", None)
        if relation == "avoid":
            # A trigger is stated as what it is — the mechanism, not "allergy".
            _add_avoid(subject, CONDITION_TRIGGER,
                       getattr(f, "reason", None) or str(subject), mechanism)
        elif relation == "favour":
            if not _is_food_advice(subject) or _conditional(subject):
                continue
            key = _normalise(subject)
            if key and key not in favour:
                favour[key] = Encouragement(
                    subject=subject,
                    subject_kind=getattr(f, "subject_kind", "food"),
                    reason=getattr(f, "reason", None) or str(subject),
                    mechanism=mechanism,
                )

    # A restriction always outranks an encouragement. One condition's mitigator
    # is another's trigger, and the safe direction is never in doubt.
    for term in list(favour):
        if term in avoid or violations(term, avoid.values()):
            favour.pop(term, None)

    # A nutrient this patient is CAPPED on is not presented as "prioritise" —
    # but it is not deleted either. It becomes a stated tension, because which
    # way it resolves depends on measurements, not on the label that produced
    # the cap. A patient labelled hypertensive whose 1,840 sessions average
    # 118/77 and end below 90 systolic 43% of the time is not a DASH candidate,
    # and no amount of reasoning from the label would discover that.
    tensions: list[str] = []
    capped = {_normalise(n) for n in (nutrient_limits or ()) if n}
    if capped:
        for term in list(favour):
            if any(c and (c in term or term in c) for c in capped):
                enc = favour.pop(term)
                tensions.append(
                    f"{enc.subject} helps one of this patient's conditions "
                    f"({enc.mechanism or enc.reason}) but is capped for another. "
                    "Weigh it against the measurements below rather than "
                    "applying either rule blindly.")

    return Guidance(avoid=list(avoid.values()), favour=list(favour.values()),
                    tensions=tensions)


def violations(text: str, restrictions: Iterable[Restriction]) -> list[Restriction]:
    """Which restricted items this text offers. Empty list means safe."""
    if not text:
        return []
    words = [_singular(w) for w in re.split(r"[^a-z0-9]+", text.lower()) if w]
    if not words:
        return []
    joined = " ".join(words)

    hits: list[Restriction] = []
    for r in restrictions or ():
        parts = r.term.split()
        if len(parts) > 1:
            if re.search(rf"\b{re.escape(r.term)}\b", joined):
                hits.append(r)
            continue
        term = parts[0]
        if len(term) < 3:
            continue
        # Equality, or the term as either half of a compound: suffix catches
        # "blueberry", prefix catches "applesauce". The >= 4 guard is what
        # keeps this from over-reaching — "egg" is three characters, so an egg
        # allergy still does not reject "eggplant".
        if any(
            w == term
            or (len(term) >= 4 and (w.endswith(term) or w.startswith(term)))
            for w in words
        ):
            hits.append(r)
    return hits


def is_safe(text: str, restrictions: Iterable[Restriction]) -> bool:
    return not violations(text, restrictions)


def prompt_block(guidance: Guidance) -> str:
    """Both halves as prompt text. Empty string when nothing applies."""
    if not guidance:
        return ""
    lines: list[str] = []

    if guidance.avoid:
        lines.append(
            "MUST NOT BE OFFERED — never include these, in any form, and never "
            "suggest them as an alternative:")
        for r in guidance.avoid:
            detail = r.mechanism or r.reason
            lines.append(f"  - {r.term} ({detail})")

    if guidance.favour:
        if lines:
            lines.append("")
        lines.append(
            "PRIORITISE — these actively help this patient's conditions; work "
            "them into meals wherever they fit:")
        for e in guidance.favour:
            detail = e.mechanism or e.reason
            lines.append(f"  - {e.subject} ({detail})")

    if guidance.tensions:
        if lines:
            lines.append("")
        lines.append(
            "UNRESOLVED — one condition asks for these and another limits them. "
            "Decide using the measurements below, and say which way you went:")
        for t in guidance.tensions:
            lines.append(f"  - {t}")

    if guidance.observations:
        if lines:
            lines.append("")
        lines.append("WHAT THIS PATIENT'S RECORD ACTUALLY MEASURES:")
        for o in guidance.observations:
            lines.append(f"  - {o}")

    if guidance.contradictions:
        if lines:
            lines.append("")
        lines.append(
            "⚠ THE RECORD CONTRADICTS A DIAGNOSIS — trust the measurements:")
        for c in guidance.contradictions:
            lines.append(f"  - {c}")

    return "\n".join(lines)
