"""Every `show…` flag an iOS view sets must be observed by something.

Found from a real report: the meal form's Camera button set `showCamera = true`
and NO `.sheet(isPresented: $showCamera)` existed anywhere in the file. Tapping
the one control a patient reaches for while the food is in front of them did
nothing at all — no error, no sheet, no hint that anything was wrong.

That is §3ad's "the page existed but had no route", one layer down: a control
and its destination both existed and nothing connected them. It cannot be
caught by a unit test (there is nothing to assert on) and it survives every
build, because setting an unread Bool compiles perfectly.

A static check is the right instrument, as it was for the eleven wrong column
names in §3ag: it costs nothing and covers every screen rather than the ones
someone thought to open.
"""

import re
from pathlib import Path

import pytest

def _locate_ios_views() -> Path | None:
    """Find IOS/ALAFIA/Views by walking up from here.

    The backend test container mounts only `WEB/backend`, so the iOS tree is
    not visible there and this skips. It runs on a developer machine and in the
    mobile job, which is where an iOS change is made in the first place —
    stated plainly rather than left to look like coverage that does not exist.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "IOS" / "ALAFIA" / "Views"
        if candidate.is_dir():
            return candidate
    return None


IOS_VIEWS = _locate_ios_views()

FLAG = re.compile(r"@State\s+(?:private\s+)?var\s+(show[A-Z]\w*)\s*(?::\s*Bool\s*)?=\s*false")

# The rule is "is it ever READ", not "is it handed to a sheet".
#
# The first version of this check listed the presentation modifiers and flagged
# anything not passed to one. It reported HealthSyncView's `showResult`, which
# is perfectly wired — read by an inline `if …, showResult {` rather than by a
# `.sheet`. Fixing that screen would have broken a working one. A flag that is
# only ever ASSIGNED is dead however it was meant to be consumed; a flag read
# anywhere is somebody's business, not this check's.
ASSIGNMENT = re.compile(r"=\s*(?:true|false)\b")


def _swift_files():
    if IOS_VIEWS is None:
        pytest.skip("iOS sources not mounted here (backend container); "
                    "run this from a full checkout")
    return sorted(IOS_VIEWS.rglob("*.swift"))


def _dead_flags(text: str) -> list[str]:
    dead = []
    declarations = {m.group(1): m.span() for m in FLAG.finditer(text)}
    for name, decl_span in declarations.items():
        # Only flags something actually turns ON matter — a declared-and-never-
        # set one is dead code, which is the compiler's business, not a control
        # that misleads a patient.
        if not re.search(rf"\b{name}\s*=\s*true", text):
            continue

        read = False
        # Walk EVERY occurrence rather than working line by line: a SwiftUI
        # body routinely puts the button and its modifier on one line, and a
        # line-based rule sees the assignment first and never reaches the read.
        for m in re.finditer(rf"\$?\b{name}\b", text):
            if decl_span[0] <= m.start() < decl_span[1]:
                continue                                  # its own declaration
            if ASSIGNMENT.match(text[m.end():].lstrip()) and not m.group().startswith("$"):
                continue                                  # a write, not a read
            read = True
            break

        if not read:
            dead.append(name)
    return dead


def test_no_ios_control_sets_a_flag_that_nothing_presents():
    offenders = []
    for path in _swift_files():
        for name in _dead_flags(path.read_text(encoding="utf-8", errors="replace")):
            offenders.append(f"{path.name}: `{name}` is set to true but nothing presents on it")
    assert not offenders, (
        "These iOS controls do nothing when tapped:\n  " + "\n  ".join(offenders)
    )


def test_the_check_can_actually_fail():
    # A green static check that cannot go red is worse than none — §3ab's
    # "the corpus harness measures recall, not precision", applied to a gate.
    broken = (
        'struct V: View {\n'
        '    @State private var showCamera = false\n'
        '    var body: some View { Button { showCamera = true } label: { Text("Camera") } }\n'
        '}'
    )
    assert _dead_flags(broken) == ["showCamera"]

    presented = broken.replace(
        'label: { Text("Camera") }',
        'label: { Text("Camera") }.sheet(isPresented: $showCamera) { CameraPicker() }',
    )
    assert _dead_flags(presented) == []


def test_a_flag_read_by_an_inline_if_is_not_dead():
    """The false positive this check shipped with, pinned.

    Its first version listed the presentation modifiers and flagged anything
    not handed to one — which reported HealthSyncView's `showResult`, a
    perfectly wired flag read by `if let result = …, showResult {`. Acting on
    that would have broken a working screen to satisfy a check. §3ap: classify
    a static finding before fixing it.
    """
    inline = (
        'struct V: View {\n'
        '    @State private var showResult = false\n'
        '    var body: some View {\n'
        '        Button { showResult = true } label: { Text("Sync") }\n'
        '        if showResult { Text("done") }\n'
        '    }\n'
        '}'
    )
    assert _dead_flags(inline) == []
