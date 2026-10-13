# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Hand-written prose that describes a patient's own measurements.

Operator, 2026-10-13, after a specific message was challenged: *"this is not
about a particular medication or therapy --- the hard coded trap"*. Correct —
fixing one sentence at a time is how the trap keeps its shape. I had just
replaced one hardcoded template with a map of five.

So this is a RATCHET, not a pass/fail, in the shape
`test_parser_hardcoding_ratchet.py` already uses for the parser's 290 clinical
literals. The count may only go DOWN. A guard that goes red the moment it lands
is one the team learns to ignore (§4's red CI that hid four real faults).

⚠️ §3ab's own warning, obeyed here: *"Its first baseline was fabricated. It was
written as 334 by subtracting exemptions in someone's head; the measured figure
is 290 … **Run the scan; never compute the baseline.** Slack must be 0."* The
number below is what the scan printed, pasted, with slack 0.

WHAT IS COUNTED, AND WHY ONLY THIS
----------------------------------
Measured 2026-10-13 across `app/`: prose literals reaching a patient-facing
field split by whether the sentence interpolates the patient's **own data**:

   109   OBSERVATION — prose + a runtime value. "N marker(s) sit at or below
         the bottom of their own reference band: Glucose 273" describes THIS
         patient, goes stale when the computation changes, and is what
         "no hard coded messages" is about. This is the ratchet's subject.
   255   FIXED COPY — a constant. "Invalid or expired verification link",
         "Food safety recalls and contamination". Routing those through a
         language model would be absurd; they belong in the i18n catalog,
         which §3aw already governs and tests.

⚠️ **The first baseline here was 96, and it was wrong** — by the very mistake
§3ab warns about, one layer in. The scan judged each f-string FRAGMENT: 
`f"Your potassium reached {v} today"` arrives as "Your potassium reached " (23
chars) and " today", neither long enough to count, so every sentence built that
way was invisible to the thing counting them. Caught by this file's own
`test_the_scan_can_actually_see_an_observation` failing on its example, not by
reading the code. Joined first, the real figure is **109**.

`fallback=` is exempt by design: `finding_text`'s whole contract is that a
deterministic sentence exists for when the model is slow, fails, or writes a
number the facts do not support.

THE REPLACEMENT ALREADY EXISTS
------------------------------
`app/services/finding_text.py` — ALAFIA writes the sentence from the facts,
locally (`local_only=True`, so no patient detail reaches a third party),
verified against those facts so a figure cannot be invented, cached by a hash
of the facts, and warmed in the background so the next read serves it. Four
wellness findings and the Ω interpretation go through it. Everything still
counted here does not, yet.
"""

import ast
import pathlib
import re

#: Measured, not computed. Re-run `scan()` and paste what it prints.
BASELINE = 109

#: Must be 0, or adding a literal does not fail the build (§3ab).
SLACK = 0

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

#: Fields whose value a PATIENT reads.
SINKS = {
    "interp", "interpretation", "message", "withheld", "reason", "note",
    "notes", "explanation", "description", "summary", "detail", "title",
    "label", "text", "advice", "recommendation", "rationale", "finding",
}
#: Deterministic BY DESIGN — see the module docstring.
EXEMPT_KW = {"fallback"}

_WORD = re.compile(r"[A-Za-z]{2,}")


def _is_prose(s: str) -> bool:
    if len(s) < 25:
        return False
    if s.strip().startswith(("http", "/", "SELECT", "{", "<")):
        return False
    return len(_WORD.findall(s)) >= 4 and " " in s.strip()


def _interpolates(node: ast.AST) -> bool:
    """True when the expression mixes prose with a runtime VALUE.

    That is the whole discriminator between an observation about this patient
    and a fixed string of copy.
    """
    for n in ast.walk(node):
        if isinstance(n, ast.FormattedValue):
            return True
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Mod, ast.Add)):
            return True
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in {"format", "join"}):
            return True
    return False


def _joined_text(node: ast.AST) -> str:
    """Every string constant in the expression, in source order, joined.

    An f-string's prose is split at each interpolation, so the fragments must
    be put back together before asking whether they form a sentence.
    """
    parts = [n.value for n in ast.walk(node)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return " ".join(parts).strip()


def scan() -> list[tuple[str, int, str]]:
    """Every observation literal, as (file, line, text)."""
    found: list[tuple[str, int, str]] = []

    for path in sorted(APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:               # not ours to police
            continue
        rel = str(path.relative_to(APP.parent))

        def consider(expr: ast.AST) -> None:
            # JOIN the fragments before judging them. An f-string is split at
            # every interpolation, so `f"Your potassium reached {v} today"`
            # arrives as "Your potassium reached " (23 chars) and " today" —
            # neither of which is prose on its own, and the sentence went
            # UNCOUNTED. Found by `test_the_scan_can_actually_see_an_observation`
            # failing on its own example (§3av: a scan is evidence only once it
            # is shown to see what it claims to).
            joined = _joined_text(expr)
            if _is_prose(joined) and _interpolates(expr):
                found.append((rel, expr.lineno, joined))

        for node in ast.walk(tree):
            if isinstance(node, ast.keyword):
                if node.arg in SINKS and node.arg not in EXEMPT_KW:
                    consider(node.value)
            elif isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target])
                names = {t.id for t in targets if isinstance(t, ast.Name)}
                names |= {t.attr for t in targets if isinstance(t, ast.Attribute)}
                if names & SINKS:
                    consider(node.value)
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and fn.attr == "append":
                    owner = fn.value
                    name = (owner.attr if isinstance(owner, ast.Attribute)
                            else owner.id if isinstance(owner, ast.Name) else "")
                    if name in SINKS:
                        for arg in node.args:
                            consider(arg)
    return found


def test_hand_written_patient_prose_only_decreases():
    found = scan()
    count = len(found)
    assert count <= BASELINE + SLACK, (
        f"{count} hand-written sentences describe a patient's own measurements, "
        f"up from {BASELINE}.\n\n"
        "A sentence built from a measurement goes stale when the measurement's "
        "computation changes — the Ω card said 'A pathway score is an average' "
        "for a week after that mean became geometric, and said markers sat 'at "
        "or below the bottom of their own reference band' for three values that "
        "were ABOVE the top.\n\n"
        "Use `app/services/finding_text.py`: give it the facts and a fallback, "
        "and ALAFIA writes the sentence locally with every figure verified "
        "against those facts.\n\n"
        "New since the baseline:\n  "
        + "\n  ".join(f"{f}:{ln}  {t[:70]}" for f, ln, t in found[-6:]))


def test_the_baseline_is_measured_rather_than_asserted():
    """§3ab's ratchet was first written as 334 by mental arithmetic against a
    real 290, so it reported `5 passed` while permitting 44 new entries — a
    green check measuring nothing, inside the test written to stop people
    asserting clinical facts without measuring them.

    This fails if the baseline drifts BELOW what the scan finds by more than
    the slack, which is what catches a baseline nobody re-measured.
    """
    assert SLACK == 0, "slack above 0 means adding a literal cannot fail the build"
    assert len(scan()) <= BASELINE


def test_the_scan_can_actually_see_an_observation():
    """A scan is evidence only once it is shown to see what it claims to
    (§3av: the `emptyForm` check read one key per line and reported 38 of 77).

    These two differ ONLY in whether a patient's value is interpolated, and the
    discriminator must separate them.
    """
    observation = ast.parse(
        'notes.append(f"Your potassium reached {value} today, above the limit")'
    ).body[0].value
    copy = ast.parse(
        'notes.append("Invalid or expired verification link, please try again")'
    ).body[0].value
    assert _interpolates(observation.args[0])
    assert not _interpolates(copy.args[0])
    assert _is_prose(_joined_text(observation.args[0])), (
        "the fragments must be joined before being judged a sentence")
    assert not _is_prose(_joined_text(ast.parse('f\"{a} {b}\"').body[0].value)), (
        "an f-string of nothing but values is not prose")


def test_the_fallback_keyword_is_exempt_and_stays_exempt():
    """`finding_text`'s contract REQUIRES a deterministic sentence. Counting
    those would make the ratchet fight the mechanism that lowers it."""
    assert "fallback" in EXEMPT_KW
    node = ast.parse('Finding(kind="k", facts={}, fallback=f"X is {v} today")'
                     ).body[0].value
    kw = [k for k in node.keywords if k.arg == "fallback"]
    assert kw and kw[0].arg in EXEMPT_KW
