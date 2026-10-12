# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""ALAFIA writes the finding; the backend decides what the finding IS.

Operator, 2026-10-11: *"do not hard code messages, let our own LLM model do
write messages that reflect the actual observation"*, then *"message must be
written by LOCAL LLM not third party providers like Anthropic. This ensures PII
do not bleed out."*

The argument for the first is the three rounds before it: ONE sentence about
this patient's blood pressure was wrong three times running while the numbers
under it were right every time — "Resting systolic 81" (one row, fifteen days
old, "resting" asserted from nothing), then "the most recent was 15 days ago"
(true of `vitals_logs`, false of the patient, whose pressure was measured two
days earlier). Each fix was an edit to an f-string, and each new f-string was a
fresh chance to say something the data did not support.

The guards below are what make handing prose to a model safe, and each exists
because of something already in this canon.
"""

import pytest

from app.services.finding_text import Finding, _numbers_preserved, render


@pytest.fixture(autouse=True)
def _clear_render_cache():
    """`_CACHE` is process-global and survives between tests.

    Found by a real failure: `test_rendering_is_LOCAL_ONLY` cached a sentence
    for the same facts the slow-model test uses, so that test got a cache HIT
    and never exercised the timeout at all. A cache that leaks across tests
    silently turns other tests into no-ops — §3aj's shape, where a suite
    passes without reaching the thing it claims to check.
    """
    from app.services import finding_text as ft
    ft._CACHE.clear()
    yield
    ft._CACHE.clear()


def _finding(**facts) -> Finding:
    return Finding(kind="t", domain="d", facts=facts, fallback="FALLBACK.")


# ── The number guard ────────────────────────────────────────────────────────

def test_a_sentence_keeping_every_number_is_accepted():
    f = _finding(value=86, reference_band_low=90, reference_band_high=120)
    assert _numbers_preserved(
        f, "Systolic 86 mmHg sits below the 90-120 reference band.")


def test_a_DROPPED_number_is_rejected():
    """A finding that loses a number understates itself: "treatments dropped
    below 90" without the 95% or the lowest of 39 is a different claim."""
    f = _finding(below=35, total=37, percent=95, floor=90, lowest=39)
    assert not _numbers_preserved(
        f, "Most treatments dropped below 90 mmHg systolic.")


def test_an_INVENTED_number_is_rejected():
    """§3am: handed a dump, a model reported **15.0 g — a number in no row of
    the record**. A clinical figure the facts do not contain must never reach
    the patient inside a sentence presented as measured."""
    f = _finding(value=86, reference_band_low=90, reference_band_high=120)
    assert not _numbers_preserved(
        f, "Systolic 86 mmHg, down from 102, is below the 90-120 band.")


def test_the_same_number_written_differently_still_matches():
    """`54` and `54.0` are one number. The guard must not reject a faithful
    sentence over formatting, or it would fire constantly and be removed."""
    f = _finding(lowest=54.0, total=33)
    assert _numbers_preserved(f, "Lowest 54 across 33 treatments.")


# ── Behaviour of render() ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_findings_means_no_call_and_no_output():
    assert await render([]) == []


@pytest.mark.asyncio
async def test_the_model_being_unavailable_costs_PROSE_not_the_finding(monkeypatch):
    """§3ae: a template fallback is correct — but the finding must still be
    stated. These are the sentences a clinician reads, so a model outage may
    never turn one into silence."""
    import app.services.alafia_model_service as svc

    async def _down(*_a, **_k):
        raise RuntimeError("no local runtime")

    monkeypatch.setattr(svc, "alafia_chat_detailed", _down)
    out = await render([_finding(value=86)])
    assert out == ["FALLBACK."]


@pytest.mark.asyncio
async def test_an_UNFAITHFUL_sentence_falls_back_but_a_faithful_one_does_not(
        monkeypatch):
    """Per finding, not all-or-nothing: one mangled sentence must not cost the
    others their model wording."""
    import json

    import app.services.alafia_model_service as svc

    async def _reply(*_a, **_k):
        return {"text": json.dumps({"findings": [
            # faithful — keeps 86, 90, 120
            {"id": 0, "text": "Median systolic 86 mmHg is under the 90-120 band."},
            # unfaithful — invents 41
            {"id": 1, "text": "Lowest was 41 across 33 treatments."},
        ]})}

    monkeypatch.setattr(svc, "alafia_chat_detailed", _reply)
    out = await render([
        Finding(kind="a", domain="vitals",
                facts={"value": 86, "low": 90, "high": 120},
                fallback="FALLBACK A."),
        Finding(kind="b", domain="dialysis",
                facts={"lowest": 54, "total": 33}, fallback="FALLBACK B."),
    ])
    assert out[0] == "Median systolic 86 mmHg is under the 90-120 band."
    assert out[1] == "FALLBACK B.", "an invented number must not reach the patient"


# ── The privacy boundary ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rendering_is_LOCAL_ONLY(monkeypatch):
    """Operator: "message must be written by LOCAL LLM not third party
    providers like Anthropic. This ensures PII do not bleed out."

    §3al's hard guarantee is `local_only=True` — ALAFIA-operated inference with
    NO hosted fallback. The facts carry no name, but they are a dense clinical
    portrait of one person, and §3al's own passing test records that redaction
    cannot catch everything it is handed. This asserts the flag is actually
    sent, because the alternative is a privacy promise that holds only until
    someone edits one keyword argument.
    """
    import json

    import app.services.alafia_model_service as svc
    seen: dict = {}

    async def _capture(messages, **kwargs):
        seen.update(kwargs)
        return {"text": json.dumps({"findings": [{"id": 0, "text": "86 mmHg."}]})}

    monkeypatch.setattr(svc, "alafia_chat_detailed", _capture)
    await render([_finding(value=86)])
    assert seen.get("local_only") is True, (
        "findings must never be written by a hosted provider")


def test_the_wrapper_actually_forwards_local_only():
    """`local_only` has always been honoured by the capability
    (`payload["local_only"]`) and was NOT exposed by the service wrapper — so
    §3al's one guarantee for text that must not leave was unreachable from the
    backend. A control that exists and cannot be used is §3ar with a privacy
    boundary attached."""
    import inspect

    from app.services.alafia_model_service import alafia_chat_detailed

    assert "local_only" in inspect.signature(alafia_chat_detailed).parameters
    assert '"local_only": local_only' in inspect.getsource(alafia_chat_detailed)


def test_the_task_name_is_one_the_capability_HANDLES():
    """A descriptive task name reaches `llm.py`'s final branch and returns
    `Unknown LLM task`, which arrives as an ALAFIAModelError and is
    indistinguishable from a provider outage. Measured 2026-10-11: THREE
    shipped features already fail this way — `doc_classify`,
    `nutrient_quota_resolution` and `mood_score` — so this is not hypothetical
    (OPEN_ITEMS 21)."""
    import inspect

    from app.services import finding_text

    source = inspect.getsource(finding_text.render)
    assert 'task="chat"' in source, (
        "use a task the LLM capability dispatches; a descriptive name silently "
        "fails as 'Unknown LLM task'")


# ── Essential vs context numbers ────────────────────────────────────────────

def test_only_ESSENTIAL_numbers_must_survive():
    """A finding may carry eleven numbers as context. Requiring all of them
    meant no readable sentence could pass, so every finding fell back — a
    guard strict enough to disable the feature it guards."""
    f = Finding(
        kind="bp", domain="vitals",
        facts={"systolic": 86, "diastolic": 62, "systolic_reference_low": 90,
               "systolic_reference_high": 120, "readings_in_window": 2,
               "window_days": 30, "days_since": 16},
        fallback="FALLBACK.", essential=("systolic", "systolic_reference_low"))
    assert _numbers_preserved(f, "Blood pressure 86/62 mmHg, systolic under 90.")


def test_dropping_an_ESSENTIAL_number_still_fails():
    f = Finding(kind="bp", domain="vitals",
                facts={"systolic": 86, "systolic_reference_low": 90},
                fallback="FALLBACK.", essential=("systolic",))
    assert not _numbers_preserved(f, "Blood pressure is on the low side.")


def test_invention_is_absolute_even_for_non_essential_facts():
    """Omission is bounded; fabrication never is."""
    f = Finding(kind="bp", domain="vitals",
                facts={"systolic": 86, "systolic_reference_low": 90},
                fallback="FALLBACK.", essential=("systolic",))
    assert not _numbers_preserved(f, "Systolic 86, down from 110.")


@pytest.mark.asyncio
async def test_a_SLOW_model_falls_back_rather_than_hanging_the_page(monkeypatch):
    """Measured 2026-10-12: the dev local model took 65 s for one finding.
    `/wellness/score` carries the 30 s axios default (§3ae), so an unbounded
    render does not give better prose — it gives a page that fails to load."""
    import asyncio as _asyncio

    import app.services.alafia_model_service as svc
    import app.services.finding_text as ft

    async def _slow(*_a, **_k):
        await _asyncio.sleep(5)
        return {"text": "{}"}

    monkeypatch.setattr(svc, "alafia_chat_detailed", _slow)
    monkeypatch.setattr(ft, "RENDER_TIMEOUT_SECONDS", 0.05)
    out = await render([_finding(value=86)])
    assert out == ["FALLBACK."]
