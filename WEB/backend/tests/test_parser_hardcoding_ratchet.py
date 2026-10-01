"""Clinical vocabulary typed into the parser may only ever DECREASE.

§3ad: never type an ICD code from memory. §3aj: RxNorm is the authority on
whether a name is a drug, not a 23-row table that was wrong in both directions.
§3c: do not add aliases — fix what blocks the lookup. §3an has an AST guard that
fails the build if a condition→food literal reappears in executable code.

None of that reached `docparse`, and it shows. Measured 2026-09-30 across the
parser: **385 hand-written elements in 25 collections**, including a 136-entry
`ANALYTE_NAMES` which recognises only **136 of the 411 distinct test names in
production — 33.1%**. It cannot name `ALT`, `AST`, `BILIRUBIN, TOTAL`,
`Anion Gap` or `BUN/CREATININE RATIO`. A hand-written vocabulary is a list of
the spellings somebody happened to meet.

WHY THIS IS A RATCHET AND NOT A PASS/FAIL
-----------------------------------------
The debt is real and cannot be deleted in one change: LOINC is a 76 MB
account-gated download, and some of these lists have no authority behind them at
all. A test that goes red the moment it lands is a test the team learns to
ignore — §4 says exactly that about the CI that was red for months and hid four
real faults.

So this records the CURRENT size and fails when it GROWS. Adding a new clinical
literal to the parser now costs a conversation; removing one is free.

WHAT IS COUNTED, AND WHAT IS DELIBERATELY NOT
---------------------------------------------
Counted: collections of clinical *vocabulary* — analyte names, routes, frequency
shorthand, condition categories, result words. Those have authorities (LOINC,
RxNorm, UCUM, ICD-11) and belong to them.

NOT counted: parsing *mechanics* — `_DATE_FORMATS`, `_ROW_ROLES`,
`_PERIOD_PATTERNS`, regexes, column-role keywords. Those describe how a PDF is
drawn, not what is clinically true, and no external vocabulary owns them.
§3ap's lesson: classify a static finding before acting on it, or you break a
working screen to satisfy a check.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_PARSER_DIR = (
    pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "docparse"
)

#: Collections that are parsing mechanics, not clinical knowledge. Each needs a
#: reason: an exemption without one is how a guard quietly stops guarding.
_MECHANICS = {
    "_DATE_FORMATS":        "strptime patterns — how a date is written, not what it means",
    "_ROW_ROLES":           "which column roles exist in our own Row model",
    "_PERIOD_PATTERNS":     "regexes for trend-grid column headers",
    "ROLE_KEYWORDS":        "header words that name a COLUMN, not an analyte",
    "SIGNATURES":           "document-type scoring; classify.py already defers to a model",
    "NO_RESULT_MARKERS":    "typographic placeholders ('-', '--', '—'), not clinical terms",
    # VERIFIED 2026-09-30 against the live APIs, not assumed:
    #
    # RxNorm was the obvious candidate and does NOT carry either of these. Its
    # TTY=DF holds 126 DOSE FORMS ("Buccal Tablet") and TTY=DFG holds 44 product
    # groups ("Injectable Product") — neither is a route. Probing RxNav for
    # 'bid', 'tid', 'qhs' and 'twice daily' returned 0 rxcui matches each.
    # Maps a specimen word a report prints ("serum", "urine") onto LOINC's own
    # SYSTEM vocabulary ("Ser/Plas", "Urine"). It is presentation→authority
    # translation and asserts no clinical fact: it adds no analyte, no range and
    # no relationship. Without it the authority's own axis is unreachable from a
    # document, which is the opposite of the goal.
    "_SYSTEM_HINTS": (
        "maps printed specimen words onto LOINC's SYSTEM axis — translation to "
        "the authority's vocabulary, not clinical knowledge of our own"
    ),
    "_ROUTES": (
        "routes are SNOMED CT 284009009, whose Affiliate License restricts "
        "redistribution — not shippable like ICD-11/GTS, so the list stays"
    ),
    "_FREQUENCY_HINTS": (
        "HL7 v3-GTSAbbreviation (CC0) defines only 16 codes and covers neither "
        "'prn', 'hs', 'as needed' nor 'with meals'; and looks_like_frequency() "
        "does substring detection on free text, not code lookup — a 16-code "
        "enumeration would silently stop recognising real prescriptions"
    ),
}

#: Measured 2026-09-30 BY RUNNING THE SCAN BELOW — not by arithmetic.
#:
#: It was first written as 334, computed in someone's head by subtracting the
#: exemptions from a total. The real figure is 290, so the guard carried 44 of
#: slack: it would have passed while 44 new hardcoded entries were added, and it
#: reported "5 passed" the whole time. A green check that measures nothing is
#: §3aa's error-as-empty-state, inside the very test written to stop people
#: asserting clinical facts without measuring them.
#:
#: This number may DECREASE and must never increase. Each reduction should name
#: the authority that replaced the list. To re-measure:
#:     docker compose --profile test run --rm backend-test python -c "..."
#: (see the commit that introduced this file)
BASELINE_CLINICAL_LITERALS = 290


def _clinical_collections() -> dict[str, tuple[str, int]]:
    """name -> (file, element count) for hand-written clinical vocabulary."""
    found: dict[str, tuple[str, int]] = {}
    for path in sorted(_PARSER_DIR.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names, value = [node.target.id], node.value
            else:
                continue
            if not names or value is None or names[0] in _MECHANICS:
                continue

            count = None
            if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
                count = len(value.elts)
            elif isinstance(value, ast.Dict):
                count = len(value.keys)
            elif isinstance(value, ast.Call) and getattr(value.func, "id", "") == "frozenset":
                arg = value.args[0] if value.args else None
                if isinstance(arg, ast.Call) and getattr(arg.func, "attr", "") == "split":
                    inner = arg.func.value
                    count = len(inner.value.split()) if isinstance(inner, ast.Constant) else 0
                elif isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
                    count = len(arg.elts)
            if count and count >= 3:
                found[names[0]] = (path.name, count)
    return found


def test_the_parser_hardcodes_no_MORE_clinical_vocabulary_than_it_did():
    found = _clinical_collections()
    total = sum(n for _, n in found.values())
    detail = "\n".join(
        f"    {name:24s} {file:22s} {n:4d}"
        for name, (file, n) in sorted(found.items(), key=lambda kv: -kv[1][1])
    )
    assert total <= BASELINE_CLINICAL_LITERALS, (
        f"Hand-written clinical vocabulary in the parser grew to {total} "
        f"(baseline {BASELINE_CLINICAL_LITERALS}).\n\n{detail}\n\n"
        "A vocabulary belongs to an authority — LOINC for analytes, RxNorm for "
        "drugs, UCUM for units, ICD-11 for conditions (§3ad, §3aj, §3c). If you "
        "genuinely need a literal here, add it to _MECHANICS with a reason "
        "saying why no authority owns it."
    )


def test_the_ratchet_is_honest_about_what_it_measures():
    """A guard that measures nothing passes forever.

    If a refactor empties the parser of clinical literals this should be updated
    downward, not left reading a stale baseline that nothing can breach.
    """
    found = _clinical_collections()
    assert found, "the scan found no collections at all — the AST walk is broken"
    assert "ANALYTE_NAMES" in found, (
        "ANALYTE_NAMES is the single largest hand-written clinical vocabulary "
        "in the parser and the main reason this guard exists; the scan must see it"
    )


def test_every_mechanics_exemption_states_a_reason():
    """§3al's allow-list rule: an exemption with no reason is how a guard rots."""
    for name, reason in _MECHANICS.items():
        assert reason and len(reason) > 15, (
            f"{name} is exempted from the hardcoding guard with no real reason. "
            "Say why no external vocabulary owns it."
        )


@pytest.mark.parametrize("name", ["ANALYTE_NAMES", "CATEGORY_RULES"])
def test_the_known_offenders_are_still_visible(name):
    """These are the ones with a real authority waiting for them.

    ANALYTE_NAMES -> LOINC (observation identity, scale, system, units)
    CATEGORY_RULES -> derivable from the LOINC class/component axis

    When either is replaced, delete its case here and lower the baseline.
    """
    assert name in _clinical_collections()
