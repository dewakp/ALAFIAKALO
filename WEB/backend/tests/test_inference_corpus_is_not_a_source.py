"""Drift guard: the ALAFIA corpus is training data, never a retrieval source.

`inference_samples.prompt` holds the patient's own words UNREDACTED, and that is
deliberate — ALAFIA is our own model, the rows never leave, and training on the
scrubbed copy would teach it to expect `[name]` tokens that never occur at
inference (§3ay). The whole design rests on nothing reading those rows back into
a prompt.

That constraint is written in the migration, the model docstring and canon, and
until this file it was enforced NOWHERE. A comment that nothing checks is the
failure this codebase keeps paying for: `profile_picture_url` nothing ever wrote,
`ai_training_consent` nothing ever read, an iOS flag nothing ever observed. So
the rule gets a test, in the same shape as `test_clinical_sources.py`.

Why a source scan rather than a behavioural test: the failure mode is "somebody
builds a prompt from the corpus six months from now". No end-to-end test of
today's endpoints could ever catch that — and if it ever fires in production,
what leaves is unredacted patient text bound for a third-party provider, which
is precisely what §3al's single egress point exists to prevent. Redaction runs
on what it is HANDED; it cannot know the text was already stored raw.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

MODEL = "InferenceSample"

# Files allowed to touch the corpus directly.
ALLOWED = {
    "services/inference_corpus.py",  # the canonical writer/reader itself
    "models/",                       # the model definition and registration
    # These two read COUNTS, never prompt text: `corpus_stats` aggregates
    # sample totals per rung and modality so readiness is visible without a
    # psql session. An aggregate cannot leak a prompt into a provider request.
    "api/ai.py",
    "api/admin.py",
}


def _python_files() -> list[Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in str(p)]


def _is_allowed(path: Path) -> bool:
    rel = str(path.relative_to(APP))
    return any(rel.startswith(a) or rel == a for a in ALLOWED)


def test_the_corpus_is_never_read_outside_its_own_service():
    """No new reader of `inference_samples` outside the corpus service.

    To add a legitimate one, put the file in ALLOWED with a comment saying why
    it cannot carry a prompt back out to a provider.
    """
    pattern = re.compile(rf"(select\(\s*{MODEL}\b|\.query\(\s*{MODEL}\b)")

    offenders = []
    for path in _python_files():
        if _is_allowed(path):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(APP)}:{lineno}: {line.strip()}")

    assert not offenders, (
        "The ALAFIA corpus holds UNREDACTED patient text and must never be read "
        "back into a prompt (§3ay). New direct readers:\n  "
        + "\n  ".join(offenders)
        + "\n\nIf this read genuinely cannot reach a provider, add the file to "
          "ALLOWED with a reason."
    )


def test_the_prompt_builders_do_not_import_the_corpus():
    """Stronger than the query check: a prompt builder must not even import it.

    `select()` is not the only way to reach a row — a helper could be handed a
    session and a list of ids. The modules that assemble prompts are named here
    explicitly, because those are the ones where a corpus row turns into egress.
    """
    prompt_builders = [
        APP / "services" / "ai_conversation.py",
        APP / "services" / "prompt_identity.py",
        APP / "services" / "record_tools.py",
        APP / "api" / "planners.py",
        APP / "api" / "image_ai.py",
        APP / "api" / "personalization.py",
    ]

    offenders = []
    for path in prompt_builders:
        if not path.exists():
            continue
        text = path.read_text()
        if MODEL in text or "inference_corpus" in text or "inference_samples" in text:
            offenders.append(str(path.relative_to(APP)))

    assert not offenders, (
        "A prompt-building module references the ALAFIA corpus: "
        + ", ".join(offenders)
        + ". Rows there are unredacted by design; anything that reaches a "
          "provider must be built from the record, not from the corpus."
    )
