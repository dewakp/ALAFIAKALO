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
* **No number may be invented, and the ESSENTIAL ones may not be dropped.**
  The two directions are deliberately not symmetrical. Invention is absolute —
  every figure in the sentence must come from the facts. Omission is bounded
  to the keys a finding names `essential`, because requiring all of them meant
  a finding carrying a systolic, a diastolic, two reference bands, a count, a
  window and two dates could not be stated in any readable sentence, so every
  one failed and fell back: a guard so strict it turned off the thing it
  guarded.
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

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Any number the facts contain, including decimals and percentages.
_NUMBER = re.compile(r"\d+(?:\.\d+)?")

#: How significant a finding is, named so a raise site STATES which kind of
#: claim it is making rather than passing a bare integer. See
#: `Finding.severity` for why the scale is about the kind of claim and not
#: about a clinical threshold.
HARM = 1        #: an event that has already happened to the patient
DEVIATION = 2   #: a measurement outside a clinical target or reference
CONTEXT = 3     #: true, and too thin or too old to lead with


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
    #: Fact keys whose numbers MUST appear in the sentence. Everything else is
    #: context the model may leave out for readability.
    #:
    #: The first version required every number in the facts, which sounds
    #: safer and is not: once a finding carried the systolic, the diastolic,
    #: both reference bands, a reading count, a window length and two dates,
    #: no readable English sentence could contain all eleven, so every finding
    #: failed verification and fell back — a guard so strict it turned the
    #: feature off. Invention stays absolutely forbidden; omission is allowed
    #: except for the numbers that ARE the finding.
    essential: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    #: How the findings are ORDERED on the screen. Set where the finding is
    #: raised, because that is the only place the clinical context is known.
    #:
    #: Operator, 2026-10-22, reading the wellness card: *"The purpose of this
    #: long but faulty analysis is unknown to me … The significance I cannot
    #: understand."* The findings were emitted by
    #: `[line for c in scored for line in (c.critical or [])]` — **the order
    #: the components happen to appear in a Python list**. So a single
    #: 26-day-old blood pressure led the card while *"35 of 37 treatments
    #: dropped below 90 mmHg systolic (lowest 39); 16 fell below 70"*, a
    #: 9/10 abdominal pain and blood in the stool came after it, because
    #: `vitals_component` is listed third and the rest are listed later.
    #:
    #: The scale is deliberately about the KIND of claim, not a clinical
    #: threshold (§3az forbids inventing those):
    #:
    #:   1 HARM      an event that has already happened to the patient —
    #:               treatments ending in hypotension, blood, severe pain
    #:   2 DEVIATION a measurement outside a clinical target or reference
    #:   3 CONTEXT   true, and too thin or too old to lead with
    #:
    #: Ties keep component order, which is deterministic, so the ranking only
    #: ever moves a finding past one of a different kind.
    severity: int = 2

    def numbers(self) -> set[str]:
        """Every numeric token in the facts, normalised for comparison."""
        return self._numbers_in(self.facts.values())

    def essential_numbers(self) -> set[str]:
        """The numbers the sentence may not omit."""
        keys = self.essential or tuple(self.facts)
        return self._numbers_in(self.facts.get(k) for k in keys)

    @staticmethod
    def _numbers_in(values) -> set[str]:
        found: set[str] = set()
        for value in values:
            if value is None or isinstance(value, bool):
                continue
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
    """No number invented, and none of the ESSENTIAL ones dropped.

    The two directions are not symmetrical, and treating them as though they
    were is what made the first version unusable:

    * **Invention is absolute.** Every number in the sentence must come from
      the facts. §3am: handed a dump, a model reported **15.0 g — a number in
      no row of the record** — inside an answer presented as measured.
    * **Omission is bounded.** Only `essential` keys must survive. A finding
      may carry eleven numbers as context; a sentence containing all eleven is
      not a sentence. Requiring them all meant every finding failed and fell
      back, which is a guard that silently disables the thing it guards.
    """
    present = {_norm_number(t) for t in _NUMBER.findall(sentence)}
    if not present.issubset(finding.numbers()):
        return False                      # invented a figure
    return finding.essential_numbers().issubset(present)


_INSTRUCTION = (
    "You write ONE short observation per finding, for the patient it is "
    "about. Aim for 25 words.\n"
    "RULES, all absolute:\n"
    "1. Use ONLY the facts given. Never add a number, a date, a drug, a "
    "diagnosis or a cause. A number not in the facts is a fabrication.\n"
    "2. Never change a number, and never CALCULATE one. No differences, no "
    "percentages, no sums, no averages — if the facts say 86 and 90, you may "
    "not write 'below by 4'. Report a blood pressure as systolic/diastolic "
    "together, never the systolic alone.\n"
    "3. Say what is OUT of range and by what bound. Do NOT recite bounds a "
    "value is comfortably inside — 'below the reference high of 120' is not "
    "an observation, it is noise.\n"
    "4. State what was measured and WHERE IT CAME FROM, in the facts' own "
    "plain words — a reading the patient took and one taken during treatment "
    "are different facts and must not be blurred.\n"
    "5. Do not advise, reassure, alarm, or explain WHY. You are not told why "
    "and must not guess.\n"
    "6. Plain words a patient reads without a glossary. No jargon, no bullet "
    "characters, no markdown.\n"
    "Reply as JSON: {\"findings\": [{\"id\": <id>, \"text\": \"...\"}]}"
)

#: How long rendering may take before the deterministic wording is used.
#:
#: Measured 2026-10-12: the dev local model (`gpt-oss:20b`) took **65 s** for
#: one finding on a cold load, and §3am records ~57 s for a comparable call —
#: that is a property of a 20B reasoning model on a laptop, not of this code.
#: WARM it is **17.1 s** — the 65 s was mostly loading 13 GB of weights.
#: `/wellness/score` is ordinary CRUD on the client and carries the 30 s axios
#: default (§3ae), so an unbounded render does not produce better prose, it
#: produces a page that fails to load. 20 s clears the warm case and stays
#: under the client. Prose is the thing that may be late; the finding is not.
#:
#: ⚠️ This is a bound, not the fix. 17 s on a page load is poor, and a COLD
#: model still falls back. The right shape is §3c's: return the deterministic
#: wording immediately, render in the background with its own session, and
#: store it on the daily score row so the next read serves ALAFIA's words.
#: Queued rather than half-built here (TASKS 16).
RENDER_TIMEOUT_SECONDS = 20.0


#: Sentences ALAFIA has already written, keyed by the EXACT facts they
#: describe. Bounded, and dropped oldest-first.
#:
#: Why a cache at all: the local model needs 14-17 s warm for ONE finding and
#: over 20 s for a card, while `/wellness/score` has 30 s. Rendering
#: synchronously therefore ALWAYS fell back, which meant the sentences on
#: screen were the hand-written fallbacks — every time. An architecture where
#: the model writes the prose, and a screen that never shows a word of it, is
#: not the same thing, and only the first was true.
#:
#: Keyed by the facts, never by user or date: if a measurement changes, the
#: key changes, so a stale sentence can never describe a new number. That is
#: the property that makes serving a cached clinical sentence safe at all.
_CACHE: dict[str, str] = {}
_CACHE_MAX = 512


def _facts_key(finding: Finding, language: str | None) -> str:
    blob = json.dumps({"k": finding.kind, "f": finding.facts, "l": language},
                      sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _remember(key: str, sentence: str) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        for old in list(_CACHE)[: _CACHE_MAX // 4]:
            _CACHE.pop(old, None)
    _CACHE[key] = sentence


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
    keys = [_facts_key(f, language) for f in findings]

    # Already written for these exact facts — serve them and ask nothing.
    if all(k in _CACHE for k in keys):
        return [_CACHE[k] for k in keys]
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
        result = await asyncio.wait_for(alafia_chat_detailed(
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
        ), timeout=RENDER_TIMEOUT_SECONDS)
        import json

        written = json.loads(result.get("text") or "{}").get("findings") or []
        by_id = {int(item["id"]): str(item.get("text") or "").strip()
                 for item in written if "id" in item}
    except Exception as exc:  # noqa: BLE001 - prose must never fail a score
        # §3ae: a template fallback is correct, but SAY why — otherwise a
        # month-long outage is indistinguishable from the template being fine.
        # §3ae: distinguish "slower than the client" from "not there". Those
        # looked like one outage three separate times in one day.
        logger.info(
            "finding text unavailable (%s%s); using deterministic wording "
            "for %d findings", type(exc).__name__,
            f", over {RENDER_TIMEOUT_SECONDS:g}s" if isinstance(
                exc, asyncio.TimeoutError) else "",
            len(findings))
        return fallbacks

    out: list[str] = []
    rejected = 0
    for index, finding in enumerate(findings):
        sentence = by_id.get(index, "")
        if sentence and _numbers_preserved(finding, sentence):
            _remember(keys[index], sentence)
            out.append(sentence)
        else:
            rejected += 1
            out.append(finding.fallback)
    if rejected:
        logger.info("%d of %d findings failed number verification and used "
                    "their deterministic wording", rejected, len(findings))
    return out


async def warm(findings: list[Finding], *, language: str | None = None) -> None:
    """Render in the background so the NEXT read shows ALAFIA's words.

    §3c's shape, which this product already relies on for nutrition: return
    what you have immediately, fill in afterwards. The read path stays fast
    and bounded; this one may take the 65 s a cold local model needs, because
    nobody is waiting on it.

    Deliberately fire-and-forget and deliberately silent on failure: a prose
    renderer that can delay a score, or raise into a request that already
    returned, is worse than one that occasionally produces nothing.
    """
    keys = [_facts_key(f, language) for f in findings]
    if not findings or all(k in _CACHE for k in keys):
        return
    try:
        await asyncio.wait_for(
            _render_uncached(findings, language), timeout=WARM_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - background prose, never a failure
        logger.info("background finding render did not finish (%s)",
                    type(exc).__name__)


#: The background pass may take as long as a cold local model needs — measured
#: 65 s on `gpt-oss:20b` including the 13 GB load. Nobody is waiting on it.
WARM_TIMEOUT_SECONDS = 180.0


async def _render_uncached(findings: list[Finding], language: str | None) -> None:
    """Populate the cache. Shares `render`'s verification by calling it."""
    previous = RENDER_TIMEOUT_SECONDS
    try:
        globals()["RENDER_TIMEOUT_SECONDS"] = WARM_TIMEOUT_SECONDS
        await render(findings, language=language)
    finally:
        globals()["RENDER_TIMEOUT_SECONDS"] = previous
