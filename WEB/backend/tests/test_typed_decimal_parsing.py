# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A number the patient typed must be read with their decimal separator.

`"0,5".toDoubleOrNull()` is null and `Double("0,5")` is nil — both are
locale-independent and accept only a dot. Measured across ALAFIA's eleven
languages, five use something else: fr, de, es and pt use `,` and ar uses `٫`
(U+066B). The keyboard follows the DEVICE locale, so this applies however the
patient set the in-app language.

The damage was silent, and worst on the most dangerous field in the product:

    Android  dose_amount = amount.toDoubleOrNull() ?: 0.0   ->  0.0 mg
    iOS      guard let value = Double(amount)               ->  would not save

Weights, temperatures, dialysate volumes and sleep hours went to null and were
dropped without a word. §3aj exists because a wrong dose in a clinical record
is the error that replays.

A static check is the right instrument here, exactly as it is for
`test_ios_presentation_flags.py` next door: there is nothing to assert on at
runtime, the code compiles perfectly, and the failure only shows on a phone
whose locale no one on the team is using.
"""

import re
from pathlib import Path

import pytest


def _repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "Android").is_dir() and (parent / "IOS").is_dir():
            return parent
    return None


ROOT = _repo_root()

#: The one Android reader that may keep a bare parse: it converts a value that
#: came back from the API, not something a patient typed. Accepting a comma
#: there would mean accepting a malformed server payload.
_ANDROID_ALLOWED = {"views/clinician/TherapyReportScreen.kt"}


@pytest.mark.skipif(ROOT is None,
                    reason="Android/iOS sources not mounted here — the backend "
                           "test container mounts only WEB/backend")
def test_no_android_view_parses_a_typed_decimal_locale_blind():
    views = ROOT / "Android/app/src/main/java/com/alafia/android/views"
    offenders = []
    for path in sorted(views.rglob("*.kt")):
        rel = str(path.relative_to(views.parent)).replace("\\", "/")
        if any(rel.endswith(a) for a in _ANDROID_ALLOWED):
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\.to(Double|Float)OrNull\(\)", line):
                offenders.append(f"{rel}:{n}  {line.strip()[:70]}")
    assert not offenders, (
        "these read a typed number without the patient's decimal separator — "
        "use LocaleDecimal.parse/parseFloat:\n  " + "\n  ".join(offenders))


@pytest.mark.skipif(ROOT is None, reason="iOS sources not mounted here")
def test_no_ios_view_parses_a_typed_decimal_locale_blind():
    views = ROOT / "IOS/ALAFIA/Views"
    decl = re.compile(
        r'(?:@State|@Published|@Binding)?\s*(?:private\s+)?var\s+([A-Za-z_]\w*)'
        r'\s*(?::\s*String\b|\s*=\s*"")')
    offenders = []
    for path in sorted(views.rglob("*.swift")):
        src = path.read_text()
        for var in set(decl.findall(src)):
            for n, line in enumerate(src.splitlines(), 1):
                if re.search(r"\bDouble\(" + re.escape(var) + r"\)", line):
                    rel = path.relative_to(views.parent)
                    offenders.append(f"{rel}:{n}  {line.strip()[:70]}")
    assert not offenders, (
        "these read a typed String as a number locale-blind — use "
        "LocaleDecimal.parse:\n  " + "\n  ".join(offenders))


@pytest.mark.skipif(ROOT is None, reason="mobile sources not mounted here")
def test_both_clients_actually_have_the_parser():
    """§3av: when one platform handles a typed number and the other does not,
    the matching pair is the specification. A parser on one client only is
    half a fix."""
    assert (ROOT / "Android/app/src/main/java/com/alafia/android/LocaleDecimal.kt").is_file()
    assert (ROOT / "IOS/ALAFIA/Core/LocaleDecimal.swift").is_file()


@pytest.mark.skipif(ROOT is None, reason="iOS sources not mounted here")
def test_the_ios_parser_is_registered_in_the_xcode_project():
    """§3bb: a Swift file on disk is INVISIBLE to the build unless it is listed
    in project.pbxproj — as a PBXBuildFile, a PBXFileReference, a child of its
    group, and a member of the Sources phase. Four entries, or the parser
    silently is not there."""
    pbxproj = (ROOT / "IOS/ALAFIA.xcodeproj/project.pbxproj").read_text()

    # Asserted structurally, not by counting the filename: the PBXBuildFile and
    # PBXFileReference lines each name the file TWICE (once as the entry, once
    # in a /* comment */), so a count is 6 and not 4 — which is how the first
    # version of this test failed against a correct registration.
    missing = [
        label for label, pattern in (
            ("PBXBuildFile",
             r"/\* LocaleDecimal\.swift in Sources \*/ = \{isa = PBXBuildFile"),
            ("PBXFileReference",
             r"/\* LocaleDecimal\.swift \*/ = \{isa = PBXFileReference"),
            ("group children",
             r"^\s+[0-9A-F]{24} /\* LocaleDecimal\.swift \*/,\s*$"),
            ("Sources phase",
             r"^\s+[0-9A-F]{24} /\* LocaleDecimal\.swift in Sources \*/,\s*$"),
        )
        if not re.search(pattern, pbxproj, re.M)
    ]
    assert not missing, (
        "LocaleDecimal.swift is on disk but not in the build — missing: "
        f"{missing}")
