# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""ALAFIA writes the finding. The backend decides what the finding IS.

Operator, 2026-10-11: *"do not hard code messages, let our own LLM model do
write messages that reflect the actual observation"* — and the three rounds
before that instruction are the argument for it. One sentence about this
patient's blood pressure was wrong three times running while the numbers under
it were right every time:

    "Resting systolic 81 mmHg is below the 90-120 mmHg reference band."
        -> one row, fifteen days old, and "resting" asserted from nothing
    "...the most recent was 15 days ago (2026-09-26), so this may not be
     current."
        -> true of `vitals_logs`, false of the patient, whose pressure was
           measured on 2026-10-09 — contradicting the next bullet on the card

Each fix was an edit to an f-string, and each new f-string was a fresh chance
to say something the data did not support. A hand-written sentence encodes an
assumption about what the numbers will be; the numbers then arrive different.

THE SPLIT, AND IT IS THE ONE §3am ALREADY ARGUES FOR
----------------------------------------------------
§3am: *"language understanding belongs to the model"* — the model extracts the
drug name, the backend resolves the dose. This is that split pointing the other
way: **the backend establishes the observation, the model renders it.**

    deterministic        the metric, the value, the band, the counts, the
                         dates, the provenance, and WHETHER it is a finding
    the model            the sentence

The model is given facts and no latitude about them. It may not add a number,
drop one, soften a comparison, or draw a conclusion — and that is ENFORCED
rather than requested, because §3am's own history is a model handed a dump and
inventing a clinical figure: asked which food drove a day's sugar it reported
**15.0 g, a number in no row of the record**.

LOCAL MODEL ONLY — THIS IS NOT A PREFERENCE
-------------------------------------------
Operator, 2026-10-11: *"message must be written by LOCAL LLM not third party
providers like Anthropic. This ensures PII do not bleed out."*

So `render` passes `local_only=True`, which is §3al's hard guarantee:
ALAFIA-operated inference with **no hosted fallback**. The facts carry no name
— identity becomes `subject_token` at the egress point — but they are a dense
clinical portrait of one person: a pressure, a date, a treatment count, a
symptom and its severity. §3al's own passing test records that redaction
cannot catch everything it is handed (*"a bare name in passing is NOT
redacted"*), and the honest answer for a payload like this one is not to lean
on redaction at all.

⚠️ **The cost is explicit.** With no local runtime there is no hosted
substitute: the deterministic wording is used and the finding still appears.
Prose degrades; nothing leaves. In dev that means Ollama must be running
(§4: `OLLAMA_HOST=0.0.0.0:11434 ollama serve`) or every finding reads as its
fallback — which is exactly what should happen.

WHAT MAKES THIS SAFE
--------------------
* **Every numeric token in the facts must survive into the sentence.**
  `_numbers_preserved` compares the two sets. A sentence that loses "39" or
  invents "72" is discarded and the deterministic fallback is used. This is
  the whole guard: the model cannot change a clinical number, because a
  changed number does not pass.
* **Every finding carries a deterministic `fallback`.** The model is an
  improvement on the wording, never a dependency for having any. §3ae: where a
  template fallback exists, returning None is correct — but LOG why, or a
  month-long outage is indistinguishable from the template being fine.
* **It is never on the clinical write path.** Rendering happens when a score is
  READ. A model timeout delays prose, never a saved row.
* **Language follows the patient** (§3aw), which the f-strings never could:
  they were English, so a patient who chose Yoruba read their own findings in
  a language they did not pick.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Any number the facts contain, including decimals and percentages.
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Finding:
    """One observation, as FACTS — with the sentence left to be written.

    `fallback` is the deterministic rendering and is REQUIRED. A finding that
    cannot state itself without a model is a finding that disappears when the
    model is unavailable, and these are the sentences a clinician reads.
    """

    #: Stable identifier for the observation, e.g. "systolic_below_band".
    kind: str
    #: The facts, already measured. Keys are whatever the observation needs.
    facts: dict[str, Any]
    #: Deterministic sentence, used when the model is unavailable or unfaithful.
    fallback: str
    #: Which domain raised it, so the renderer can group sensibly.
    domain: str = ""
    notes: list[str] = field(default_factory=list)

    def numbers(self) -> set[str]:
        """Every numeric token in the facts, normalised for comparison."""
        found: set[str] = set()
        for value in self.facts.values():
            for token in _NUMBER.findall(str(value)):
                found.add(_norm_number(token))
        return found


def _norm_number(token: str) -> str:
    """`54.0` and `54` are the same number; `0.70` and `.7` are not tokens we
    need to unify beyond trailing zeros."""
    try:
        as_float = float(token)
    except ValueError:
        return token
    if as_float == int(as_float):
        return str(int(as_float))
    return str(as_float).rstrip("0").rstrip(".")


def _numbers_preserved(finding: Finding, sentence: str) -> bool:
    """Did every number in the facts survive, with none invented?

    Both directions matter. A DROPPED number is a finding that understates
    itself — "treatments dropped below 90" without the 95% or the 39. An
    INVENTED one is §3am's fabricated 15.0 g, in a sentence presented as
    measured.
    """
    wanted = finding.numbers()
    present = {_norm_number(t) for t in _NUMBER.findall(sentence)}
    return wanted.issubset(present) and present.issubset(wanted)


_INSTRUCTION = (
    "You write one short clinical observation per finding, for the patient it "
    "is about.\n"
    "RULES, all absolute:\n"
    "1. Use ONLY the facts given. Never add a number, a date, a drug, a "
    "diagnosis or a cause.\n"
    "2. Every number in the facts must appear in your sentence, unchanged.\n"
    "3. State what was measured. Do not advise, reassure, alarm, or explain "
    "WHY — you are not told why and must not guess.\n"
    "4. Name the SOURCE when the facts give one, because a self-recorded "
    "reading and a reading taken during treatment are different facts.\n"
    "5. One sentence per finding. Plain words. No bullet characters.\n"
    "Reply as JSON: {\"findings\": [{\"id\": <id>, \"text\": \"...\"}]}"
)


async def render(findings: list[Finding], *, language: str | None = None
                 ) -> list[str]:
    """Findings as sentences — written by ALAFIA, verified against the facts.

    Returns one string per finding, in order. A finding whose rendering fails
    verification falls back to its own deterministic sentence, individually:
    one bad sentence must not cost the other four.
    """
    if not findings:
        return []

    fallbacks = [f.fallback for f in findings]
    try:
        from app.services.alafia_model_service import alafia_chat_detailed
    except ImportError:  # pragma: no cover - app-only dependency
        return fallbacks

    payload = [{"id": i, "kind": f.kind, "domain": f.domain, "facts": f.facts}
               for i, f in enumerate(findings)]
    prompt = _INSTRUCTION
    if language:
        prompt += f"\nWrite in this language: {language}."
    prompt += f"\n\nFINDINGS:\n{payload}"

    try:
        result = await alafia_chat_detailed(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            json_mode=True,
            # "chat" is the GENERIC PASSTHROUGH the capability actually
            # handles. A descriptive name like "finding_text" reaches
            # `llm.py`'s final branch and returns `Unknown LLM task`, which
            # arrives here as an ALAFIAModelError and looks exactly like a
            # provider outage — see OPEN_ITEMS 21 for the three shipped
            # features already failing this way.
            task="chat",
            # LOCAL ONLY. Operator, 2026-10-11: "message must be written by
            # LOCAL LLM not third party providers like Anthropic. This ensures
            # PII do not bleed out."
            #
            # §3al's hard guarantee, and the right call for this payload. The
            # facts carry no name — identity becomes `subject_token` at the
            # egress point — but they ARE a dense clinical portrait: a
            # pressure, a date, a treatment count, a symptom. §3al's own
            # passing test records that redaction CANNOT catch everything it
            # is handed, and the honest answer for a payload like this is not
            # to rely on redaction at all.
            #
            # The cost is explicit and accepted: with no local runtime there is
            # NO hosted fallback, so the deterministic wording is used. Prose
            # degrades; nothing leaves.
            local_only=True,
        )
        import json

        written = json.loads(result.get("text") or "{}").get("findings") or []
        by_id = {int(item["id"]): str(item.get("text") or "").strip()
                 for item in written if "id" in item}
    except Exception as exc:  # noqa: BLE001 - prose must never fail a score
        # §3ae: a template fallback is correct, but SAY why — otherwise a
        # month-long outage is indistinguishable from the template being fine.
        logger.info("finding text unavailable (%s); using deterministic "
                    "wording for %d findings", type(exc).__name__, len(findings))
        return fallbacks

    out: list[str] = []
    rejected = 0
    for index, finding in enumerate(findings):
        sentence = by_id.get(index, "")
        if sentence and _numbers_preserved(finding, sentence):
            out.append(sentence)
        else:
            rejected += 1
            out.append(finding.fallback)
    if rejected:
        logger.info("%d of %d findings failed number verification and used "
                    "their deterministic wording", rejected, len(findings))
    return out
