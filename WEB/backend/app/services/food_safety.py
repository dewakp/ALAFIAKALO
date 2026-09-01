"""Foods this patient must never be offered — the one place that decides.

A meal plan is a recommendation the patient is meant to act on, so a food they
are allergic to must not reach them. Relying on the model to honour an
`ALLERGIES:` line in a prompt is not a control: a production plan recommended
"1 small apple" at breakfast, and then "choose low-potassium fruits (apples,
grapes)", to a patient whose profile reads `Raw Apples, Raw Berries`.

So this module is used TWICE on every generated plan:

  1. in the prompt, as an explicit forbidden list (helps a good model), and
  2. on the output, as a filter (catches a bad one) — including the
     deterministic TEMPLATE fallback, which is static text nobody had checked
     against a patient profile at all. The renal template serves "Cream of
     wheat with blueberries" and "Waffles with strawberries".

Canon §3aj's dose guard is the model: a guard states WHAT it blocked and WHY,
because one that cannot explain itself gets blamed for the thing it did not do.

Matching deliberately errs toward flagging. A false positive costs the patient
one menu option; a false negative is the thing this module exists to prevent.
Single-word terms match on word equality OR suffix, so "berry" catches
"blueberries" and "strawberries" — and, yes, "apple" catches "pineapple".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

# Words that qualify a food without changing what it is. "Raw Apples" is an
# apple allergy; the patient is not safe from a cooked one by this module's
# reckoning, and deciding otherwise is a clinical call we must not make.
_QUALIFIERS = frozenset({
    "raw", "fresh", "dried", "cooked", "ripe", "whole", "canned", "frozen",
    "steamed", "baked", "boiled", "grilled", "roasted", "plain", "unsweetened",
})

# Food contraindications implied by a DIAGNOSIS rather than by an allergy row.
#
# Kept deliberately small and specific. Fava beans are the classic, established
# trigger for acute haemolysis in G6PD deficiency — "favism" is named for it —
# and it is a food contraindication that follows from the diagnosis itself, so
# a patient who never listed it as an allergy is still owed the warning.
# Legumes in general are NOT contraindicated in G6PD, and adding them here
# would restrict a renal patient's protein options for no clinical reason.
_CONDITION_FORBIDDEN: dict[str, tuple[tuple[str, ...], str]] = {
    "g6pd": (
        ("fava bean", "broad bean", "faba bean", "ful medames"),
        "G6PD deficiency — fava beans can trigger acute haemolysis (favism)",
    ),
}


@dataclass(frozen=True)
class Forbidden:
    """One thing the patient must not be offered, and why."""

    term: str      # normalised, singular, lowercase — what we match on
    reason: str    # patient-facing explanation
    source: str    # "allergy" | "intolerance" | "condition"


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


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("oes"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _normalise(phrase: str) -> str:
    """Lowercase, drop qualifiers, singularise each remaining word."""
    words = [w for w in re.split(r"[^a-z0-9]+", phrase.lower()) if w]
    kept = [_singular(w) for w in words if w not in _QUALIFIERS]
    return " ".join(kept)


def _condition_names(conditions: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    for c in conditions or []:
        name = getattr(c, "name", None) or getattr(c, "condition_name", None) or str(c)
        if name:
            out.append(str(name))
    return out


def forbidden_for(user: Any, conditions: Iterable[Any] | None = None) -> list[Forbidden]:
    """Everything this patient must not be offered, from profile + diagnoses."""
    found: dict[str, Forbidden] = {}

    def _add(raw: str, reason: str, source: str) -> None:
        term = _normalise(raw)
        if term and term not in found:
            found[term] = Forbidden(term=term, reason=reason, source=source)

    for item in profile_list(getattr(user, "allergies", None)):
        _add(item, f"allergy: {item}", "allergy")
    for item in profile_list(getattr(user, "food_intolerances", None)):
        _add(item, f"food intolerance: {item}", "intolerance")

    haystack = " ".join(_condition_names(conditions)).lower()
    # The profile's own free-text fields can name the condition too — this
    # patient carries "G6PD Deficiency" under food intolerances, not diagnoses.
    haystack += " " + " ".join(
        profile_list(getattr(user, "food_intolerances", None))
        + profile_list(getattr(user, "dietary_restrictions", None))
    ).lower()
    for key, (terms, reason) in _CONDITION_FORBIDDEN.items():
        if key in haystack:
            for t in terms:
                _add(t, reason, "condition")

    return list(found.values())


def violations(text: str, forbidden: Iterable[Forbidden]) -> list[Forbidden]:
    """Which forbidden items this text offers. Empty list means safe."""
    if not text:
        return []
    words = [_singular(w) for w in re.split(r"[^a-z0-9]+", text.lower()) if w]
    if not words:
        return []
    joined = " ".join(words)

    hits: list[Forbidden] = []
    for f in forbidden:
        parts = f.term.split()
        if len(parts) > 1:
            if re.search(rf"\b{re.escape(f.term)}\b", joined):
                hits.append(f)
            continue
        term = parts[0]
        if len(term) < 3:
            continue
        # Equality, or the term appearing as either half of a compound:
        # suffix catches "blueberry"/"strawberry", prefix catches "applesauce".
        # A live plan offered "Pork tenderloin with applesauce" to an
        # apple-allergic patient because only the suffix case was handled.
        #
        # The >= 4 guard is what keeps this from over-reaching: "egg" is three
        # characters, so an egg allergy still does not reject "eggplant", while
        # "apple" is five and does reject "applesauce" — which is correct, that
        # is what applesauce is made of.
        if any(
            w == term
            or (len(term) >= 4 and (w.endswith(term) or w.startswith(term)))
            for w in words
        ):
            hits.append(f)
    return hits


def is_safe(text: str, forbidden: Iterable[Forbidden]) -> bool:
    return not violations(text, forbidden)


def prompt_block(forbidden: Iterable[Forbidden]) -> str:
    """The forbidden list as prompt text. Empty string when nothing applies."""
    items = list(forbidden)
    if not items:
        return ""
    lines = [
        "FORBIDDEN — NEVER include any of these, in any form, "
        "and never suggest them as an alternative:",
    ]
    for f in items:
        lines.append(f"  - {f.term} ({f.reason})")
    return "\n".join(lines)
