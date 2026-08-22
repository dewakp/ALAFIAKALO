"""Drugs given DURING dialysis — parsed out of the flowsheet's free-text field.

CLAUDE.md §3aa says the medication picture lives in two tables. It lives in
**three**. The third is `therapy_sessions.drugs_administered`, and it is the one
nobody reads:

    Epogene         1,962 sessions
    Venofer         1,248 sessions   (IV iron)
    Doxercalciferol   788 sessions   (vitamin D analogue)
    ---------------------------------------------------
    in medication_dose_logs:  0

A decade of ESA and IV iron, invisible to the clinician board, the AI context,
and anything else asking "what is this patient actually on". It is why a review
of that record concluded "no ESA prescribed or taken" — `medications` and
`medication_dose_logs` were both checked, and both are silent about it.

These drugs are administered by the unit, not self-logged, so they will never
appear in a dose log the patient fills in. Reading the flowsheet is the only way
to know.

Parsing notes, each from the real corpus rather than imagination:

- Items are `; `-separated, **but a semicolon also occurs inside parentheses**:
  `Sodium Citrate (12 ml  Venous; 3ml Arterial); Epogene (3,000 SQ)`.
  Splitting naively turns one record into two bogus drugs.
- Doses vary: `(20,000 SQ)`, `(100 mg)`, `(100mg)`, `(4mcg)`, `(1.8 ml x 2)`.
- Some parentheses hold no dose at all: `(NONE)`, `(Oct)`.
- Case varies (`venofer` / `Venofer`) and names are truncated
  (`Doxercalcif` for doxercalciferol), so grouping on the raw string splits one
  drug into several — the same case-sensitivity trap §3aa already documents for
  dose logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

__all__ = ["FlowsheetDrug", "parse_drugs_administered", "summarize_flowsheet_drugs"]


# Canonical names for what the corpus actually contains. Keys are matched
# case-insensitively against the leading text of an item, longest first, so
# "Doxercalcif" and "Doxercalciferol" land on one drug rather than two.
_CANONICAL: dict[str, str] = {
    "epogen": "Epoetin alfa",
    "epogene": "Epoetin alfa",
    "epoetin": "Epoetin alfa",
    "procrit": "Epoetin alfa",
    "aranesp": "Darbepoetin alfa",
    "darbepoetin": "Darbepoetin alfa",
    "mircera": "Methoxy PEG-epoetin beta",
    "venofer": "Iron sucrose",
    "iron sucrose": "Iron sucrose",
    "ferrlecit": "Sodium ferric gluconate",
    "feraheme": "Ferumoxytol",
    "injectafer": "Ferric carboxymaltose",
    "doxercalciferol": "Doxercalciferol",
    "doxercalcif": "Doxercalciferol",
    "paricalcitol": "Paricalcitol",
    "zemplar": "Paricalcitol",
    "calcitriol": "Calcitriol",
    "sodium citrate": "Sodium citrate",
    "heparin": "Heparin",
    "alteplase": "Alteplase",
    "vancomycin": "Vancomycin",
}

# What the drug is FOR. The driver analysis needs this: an ESA on board means
# an anaemia is being treated, which is a different clinical picture from an
# untreated one, and it is the difference between "eat more iron" and "the ESA
# is doing its job".
_DRUG_CLASS: dict[str, str] = {
    "Epoetin alfa": "ESA",
    "Darbepoetin alfa": "ESA",
    "Methoxy PEG-epoetin beta": "ESA",
    "Iron sucrose": "IV iron",
    "Sodium ferric gluconate": "IV iron",
    "Ferumoxytol": "IV iron",
    "Ferric carboxymaltose": "IV iron",
    "Doxercalciferol": "vitamin D analogue",
    "Paricalcitol": "vitamin D analogue",
    "Calcitriol": "vitamin D analogue",
    "Sodium citrate": "catheter lock",
    "Heparin": "anticoagulant",
    "Alteplase": "thrombolytic",
    "Vancomycin": "antibiotic",
}

# Parenthesised text that is not a dose. `(Oct)` and `(NONE)` both occur.
_NON_DOSE = re.compile(r"^(none|n/?a|nil|\W*|[a-z]{3,4})$", re.IGNORECASE)
_HAS_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class FlowsheetDrug:
    """One drug read off one flowsheet."""

    name: str                  # canonical where known, else as written
    dose: str | None = None    # verbatim, e.g. "20,000 SQ" — never invented
    raw: str = ""              # the item as it appeared
    drug_class: str | None = None
    recognised: bool = False   # False => name is unmapped, treat with care

    @property
    def is_esa(self) -> bool:
        return self.drug_class == "ESA"


def _split_items(text: str) -> list[str]:
    """Split on `;` at paren depth 0 only.

    `Sodium Citrate (12 ml  Venous; 3ml Arterial); Epogene (3,000 SQ)` is TWO
    drugs, not three. A plain `text.split(";")` invents a drug called
    "3ml Arterial)".
    """
    items: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return [i.strip() for i in items if i.strip()]


def _canonicalise(name: str) -> tuple[str, str | None, bool]:
    key = " ".join(name.lower().split())
    for alias in sorted(_CANONICAL, key=len, reverse=True):
        if key.startswith(alias):
            canon = _CANONICAL[alias]
            return canon, _DRUG_CLASS.get(canon), True
    # Unknown: keep what was written. Never guess a drug name — a wrong one on
    # a medication list is worse than an unrecognised one.
    return name.strip(), None, False


def parse_drugs_administered(text: str | None) -> list[FlowsheetDrug]:
    """Parse one `drugs_administered` value into structured drugs.

    Returns [] for empty input. Never raises: a flowsheet that cannot be parsed
    must not break the screen that shows it.
    """
    if not text or not text.strip():
        return []

    out: list[FlowsheetDrug] = []
    for item in _split_items(text):
        m = re.match(r"^([^(]+?)\s*(?:\((.*)\))?\s*$", item, re.DOTALL)
        if not m:
            continue
        raw_name = m.group(1).strip(" ,;")
        if not raw_name:
            continue
        dose = (m.group(2) or "").strip()
        # "(NONE)", "(Oct)" and anything with no digit are not doses.
        if dose and (_NON_DOSE.match(dose) or not _HAS_DIGIT.search(dose)):
            dose = ""
        name, drug_class, recognised = _canonicalise(raw_name)
        out.append(
            FlowsheetDrug(
                name=name,
                dose=dose or None,
                raw=item.strip(),
                drug_class=drug_class,
                recognised=recognised,
            )
        )
    return out


@dataclass
class FlowsheetDrugSummary:
    """What a patient has actually been given during dialysis, over a period."""

    name: str
    drug_class: str | None
    sessions: int = 0
    first_seen: str | None = None
    last_seen: str | None = None
    doses_seen: list[str] = field(default_factory=list)

    @property
    def latest_dose(self) -> str | None:
        return self.doses_seen[-1] if self.doses_seen else None


def summarize_flowsheet_drugs(sessions: Iterable) -> list[FlowsheetDrugSummary]:
    """Roll flowsheet drugs up per drug, oldest→newest.

    *sessions* is any iterable of objects with `drugs_administered` and
    `scheduled_date`. Grouping is by CANONICAL name, so "venofer" and "Venofer"
    are one drug and not two (§3aa).
    """
    rolled: dict[str, FlowsheetDrugSummary] = {}
    ordered = sorted(
        (s for s in sessions if getattr(s, "drugs_administered", None)),
        key=lambda s: (getattr(s, "scheduled_date", None) is None,
                       getattr(s, "scheduled_date", None)),
    )
    for s in ordered:
        when = getattr(s, "scheduled_date", None)
        stamp = str(when)[:10] if when else None
        for drug in parse_drugs_administered(s.drugs_administered):
            entry = rolled.setdefault(
                drug.name, FlowsheetDrugSummary(name=drug.name, drug_class=drug.drug_class)
            )
            entry.sessions += 1
            if stamp:
                entry.first_seen = entry.first_seen or stamp
                entry.last_seen = stamp
            if drug.dose:
                entry.doses_seen.append(drug.dose)
    return sorted(rolled.values(), key=lambda e: e.sessions, reverse=True)
