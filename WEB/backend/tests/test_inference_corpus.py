"""The ALAFIA training corpus collects, and collects only what it may.

ALAFIA is the model we train ourselves. It is not Ollama — Ollama is a runtime
serving other people's weights and is the terminal rung of the lookup path. The
rungs are unchanged; what these tests pin is that whatever rung answers, the
resolution becomes a training sample.

`telemetry.register_sink` existed for this and nothing ever called it, so the
(input -> output) pair hit `if not _sinks: return` and was discarded on every
call. These tests fail against that state.
"""

import asyncio

import pytest
from sqlalchemy import select

from app.models.inference_sample import (
    InferenceSample,
    RESOLVED_BY_DB,
    RESOLVED_BY_EXTERNAL,
    RESOLVED_BY_LOCAL,
    RESOLVED_BY_NONE,
)
from app.models.user import User
from app.services import inference_corpus


@pytest.fixture(autouse=True)
def _clean_context():
    """Each test decides its own subject; none inherits the last one's."""
    inference_corpus.clear_subject()
    yield
    inference_corpus.clear_subject()
    inference_corpus._queue = None


def _queue(maxsize: int = 50) -> asyncio.Queue:
    """A queue without the drain — these tests assert on what was ENQUEUED.

    Starting the real drain would make every assertion depend on a background
    task winning a race against the assertion, which is how a suite starts
    failing for reasons that have nothing to do with the code.
    """
    q = asyncio.Queue(maxsize=maxsize)
    inference_corpus._queue = q
    return q


# ── Consent ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nothing_is_collected_without_consent():
    """`ai_training_consent` defaults to false, and false must mean nothing."""
    q = _queue()
    inference_corpus.register_subject(1, "alafia-abc", consented=False)

    inference_corpus.sink({
        "messages": [{"role": "user", "content": "my potassium was 5.8"}],
        "response": "That is above range.", "task": "chat", "tier": "local",
    })

    assert q.qsize() == 0


@pytest.mark.asyncio
async def test_a_consented_sample_is_collected():
    q = _queue()
    inference_corpus.register_subject(7, "alafia-abc", consented=True)

    inference_corpus.sink({
        "messages": [{"role": "user", "content": "my potassium was 5.8"}],
        "response": "That is above range.", "task": "chat",
        "tier": "local", "provider": "ollama", "model": "gpt-oss:20b",
        "latency_ms": 900, "tokens": 40,
    })

    assert q.qsize() == 1
    row = q.get_nowait()
    assert row["user_id"] == 7
    assert row["subject_token"] == "alafia-abc"
    assert "my potassium was 5.8" in row["prompt"]
    assert row["response"] == "That is above range."


@pytest.mark.asyncio
async def test_an_unauthenticated_subject_collects_nothing():
    """No registered subject means no consent answer, so nothing is kept.

    Degrading to "collect it anyway" is the unsafe direction for a consent
    decision — the default has to be silence.
    """
    q = _queue()
    inference_corpus.sink({"messages": "anything", "response": "x", "task": "complete"})
    assert q.qsize() == 0


# ── Which rung answered ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_rung_that_answered_is_recorded():
    """The lookup path is DB -> external provider -> local runtime.

    Recording which rung answered is the point: it is what says where ALAFIA
    has to get good, and a sample our own store answered is a different kind of
    evidence from one a vendor answered.
    """
    inference_corpus.register_subject(1, "alafia-abc", consented=True)

    local = inference_corpus.build_row(
        {"messages": "q", "response": "a", "tier": "local", "provider": "ollama"})
    hosted = inference_corpus.build_row(
        {"messages": "q", "response": "a", "tier": "free", "provider": "deepseek"})
    from_store = inference_corpus.build_row(
        {"messages": "q", "response": "a", "source": "learned"})

    assert local["resolved_by"] == RESOLVED_BY_LOCAL
    assert hosted["resolved_by"] == RESOLVED_BY_EXTERNAL
    assert from_store["resolved_by"] == RESOLVED_BY_DB


@pytest.mark.asyncio
async def test_a_failure_still_carries_its_question():
    """A question nothing could answer is the clearest thing ALAFIA can learn.

    A corpus of successes alone describes a system that always works.
    """
    inference_corpus.register_subject(1, "alafia-abc", consented=True)

    row = inference_corpus.build_row({
        "messages": [{"role": "user", "content": "why am I purging?"}],
        "success": False, "error": "ReadTimeout", "task": "chat", "tier": "local",
    })

    assert row is not None
    assert "why am I purging?" in row["prompt"]
    assert row["success"] is False
    assert row["resolved_by"] == RESOLVED_BY_NONE
    assert row["error"] == "ReadTimeout"


@pytest.mark.asyncio
async def test_a_row_with_neither_side_is_not_kept():
    """A successful call that recorded no input and no output teaches nothing."""
    inference_corpus.register_subject(1, "alafia-abc", consented=True)
    assert inference_corpus.build_row({"task": "chat", "success": True}) is None


# ── The shapes the input arrives in ───────────────────────────────────

@pytest.mark.asyncio
async def test_a_single_prompt_completion_keeps_its_input():
    """`complete` passes a bare string, not a message list.

    llm.py held `chat_msgs = arg if kind == "chat" else None`, so every
    single-prompt completion recorded NO input at all — the answer with its
    question missing. This is the corpus half of that fix.
    """
    inference_corpus.register_subject(1, "alafia-abc", consented=True)

    row = inference_corpus.build_row({
        "messages": "Estimate nutrients for: 2 cups jollof rice",
        "response": '{"calories": 620}', "task": "complete", "tier": "free",
    })

    assert row is not None
    assert row["prompt"] == "Estimate nutrients for: 2 cups jollof rice"


@pytest.mark.asyncio
async def test_the_patients_own_words_are_stored_not_the_scrubbed_copy():
    """The corpus gets the RAW input; only what LEAVES is redacted (§3al).

    The hosted rung scrubs on the way out and the local rung does not, so
    storing whatever the provider happened to be handed would train ALAFIA on
    `[name]` tokens in roughly the proportion that hosted providers won the
    race — tokens that never occur at inference time.
    """
    inference_corpus.register_subject(1, "alafia-abc", consented=True)

    row = inference_corpus.build_row({
        "messages": [{"role": "user", "content": "I'm Jane Doe and my K was 5.8"}],
        "response": "ok", "tier": "free", "provider": "anthropic",
        "input_was_redacted": False,
    })

    assert "Jane Doe" in row["prompt"]
    assert "[name]" not in row["prompt"]
    assert row["input_was_redacted"] is False


@pytest.mark.asyncio
async def test_a_scrubbed_sample_says_so():
    """Where only the redacted copy could be captured, the row admits it.

    A trainer can then drop it rather than quietly learn from text no user
    ever typed. A sample that misrepresents itself is worse than none.
    """
    inference_corpus.register_subject(1, "alafia-abc", consented=True)
    row = inference_corpus.build_row({
        "messages": "[name] asked about potassium", "response": "ok",
        "input_was_redacted": True,
    })
    assert row["input_was_redacted"] is True


# ── The sink must never cost an answer ────────────────────────────────

@pytest.mark.asyncio
async def test_the_sink_never_raises_on_a_shape_it_does_not_know():
    """It runs inside inference, on the event loop, while a patient waits.

    A side channel that can throw is a side channel that eventually takes the
    answer with it (§3ah).
    """
    _queue()
    inference_corpus.register_subject(1, "alafia-abc", consented=True)

    inference_corpus.sink({"messages": object(), "response": object()})
    inference_corpus.sink({})
    inference_corpus.sink({"messages": [1, 2, 3], "response": 7})


@pytest.mark.asyncio
async def test_a_full_queue_drops_samples_rather_than_blocking():
    """Losing training data beats making a patient wait on our bookkeeping.

    An unbounded queue would turn a database outage into memory exhaustion.
    """
    q = _queue(maxsize=2)
    inference_corpus.register_subject(1, "alafia-abc", consented=True)

    for i in range(10):
        inference_corpus.sink({"messages": f"q{i}", "response": "a", "tier": "local"})

    assert q.qsize() == 2  # and nothing raised, and nothing blocked


# ── Withdrawal ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_withdrawing_consent_purges_what_was_kept(db):
    """Consent is revocable, so the rows it covered have to be removable."""
    user = User(email="corpus-purge@example.com", hashed_password="x", full_name="T U")
    db.add(user)
    await db.flush()

    db.add_all([
        InferenceSample(user_id=user.id, modality="llm", task="chat",
                        resolved_by=RESOLVED_BY_LOCAL, prompt="q", response="a"),
        InferenceSample(user_id=user.id, modality="llm", task="complete",
                        resolved_by=RESOLVED_BY_EXTERNAL, prompt="q2", response="a2"),
    ])
    await db.commit()

    removed = await inference_corpus.purge_user(db, user.id)
    assert removed == 2

    left = (await db.execute(
        select(InferenceSample).where(InferenceSample.user_id == user.id)
    )).scalars().all()
    assert left == []
