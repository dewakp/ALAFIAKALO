"""Capture every resolution as an ALAFIA training sample.

This is the sink `alafia_model.telemetry.register_sink` was written for and
which nothing ever registered, so the (input -> output) pair reached
`if not _sinks: return` and was discarded on every call.

WHY IT DOES NOT WRITE INLINE
----------------------------
`telemetry.record()` is called SYNCHRONOUSLY from inside the inference path, on
the event loop, while the patient waits. A DB write there would block the loop
and — worse — couple every AI answer to the database being reachable. So the
sink does the smallest possible thing (put a dict on a bounded queue) and a
drain task writes with its OWN session, the same shape nutrition enrichment uses
(§3c): the request's session is closed by the time the row is written.

The queue is BOUNDED and drops when full, loudly. An unbounded queue turns a
database outage into memory exhaustion, and losing training samples is a cost
worth paying to keep answering patients — §3ah's rule that a side channel must
never fail the thing it observes.

CONSENT
-------
`users.ai_training_consent`, default false. Until now all three clients offered
that toggle and nothing on the server read it — a control that set a flag
nothing observed (§3ar), on a consent flag, which is the worst place for it.
The ML package cannot make this check itself: `privacy.register_identity` keeps
only the HMAC subject token, deliberately, because that is all a provider may
ever see. So the decision is carried here, in the backend, seeded from the one
dependency every authenticated request already passes through.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from typing import Any

from sqlalchemy import func, select

from app.models.inference_sample import (
    InferenceSample,
    RESOLVED_BY_DB,
    RESOLVED_BY_EXTERNAL,
    RESOLVED_BY_LOCAL,
    RESOLVED_BY_NONE,
)

logger = logging.getLogger(__name__)

# Who this request belongs to, and whether they agreed to train a shared model.
# Two vars rather than one object: the consent answer is read on a hot path and
# must not depend on a user row still being attached to a session.
_user_id: ContextVar[int | None] = ContextVar("alafia_corpus_user_id", default=None)
_subject: ContextVar[str | None] = ContextVar("alafia_corpus_subject", default=None)
_consented: ContextVar[bool] = ContextVar("alafia_corpus_consent", default=False)

# Enough to absorb a burst while the database is briefly unavailable; small
# enough that a long outage cannot grow without bound.
MAX_QUEUED = 2000

_queue: asyncio.Queue | None = None
_drain: asyncio.Task | None = None
_dropped = 0


def register_subject(user_id: int | None, subject_token: str | None, consented: bool) -> None:
    """Record who is asking and whether their data may train a shared model."""
    _user_id.set(user_id)
    _subject.set(subject_token)
    _consented.set(bool(consented))


def clear_subject() -> None:
    _user_id.set(None)
    _subject.set(None)
    _consented.set(False)


def _rung(fields: dict[str, Any]) -> str:
    """Normalise the answering rung across surfaces that name it differently.

    The LLM capability reports a `tier` (local/free/paid); the nutrient
    estimator reports a `source` (learned/curated/usda/ai). A corpus that stored
    both vocabularies could not be counted, and counting per rung is the whole
    point — it says where ALAFIA has to get good.
    """
    if not fields.get("success", True):
        return RESOLVED_BY_NONE
    explicit = fields.get("resolved_by")
    if explicit:
        return str(explicit)
    tier = (fields.get("tier") or "").lower()
    if tier == "local":
        return RESOLVED_BY_LOCAL
    if tier in ("free", "paid", "hosted"):
        return RESOLVED_BY_EXTERNAL
    source = (fields.get("source") or "").lower()
    if source in ("learned", "curated", "cache", "usda", "learned-recall", "db"):
        return RESOLVED_BY_DB
    return RESOLVED_BY_EXTERNAL


def _as_text(value: Any) -> str | None:
    """Flatten an input to the text a model actually saw.

    A chat request is a list of message dicts; a completion is a bare string.
    Both become one prompt string, because that is the shape a fine-tune reads.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for msg in value:
            if isinstance(msg, dict):
                role = msg.get("role") or "user"
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    parts.append(f"{role}: {content}")
            elif isinstance(msg, str):
                parts.append(msg)
        return "\n".join(parts) or None
    return None


def build_row(fields: dict[str, Any]) -> dict[str, Any] | None:
    """Turn one recorded attempt into a corpus row, or None if there is nothing
    to learn from it.

    Split out from `sink` so the decisions can be tested without a queue or a
    database — which rung answered, whether a failure still carries its
    question, whether the input survived the trip at all. Behind a queue those
    are only observable by timing, and a test that waits is a test that flakes.
    """
    prompt = _as_text(fields.get("messages"))
    response = fields.get("response")
    structured = fields.get("structured")
    # Nothing to learn from a row with neither side of the pair. A failure is
    # exempt: the question that could not be answered IS the sample.
    if prompt is None and response is None and structured is None:
        if fields.get("success", True):
            return None

    return {
        "user_id": _user_id.get(),
        "subject_token": _subject.get(),
        "modality": str(fields.get("modality") or "llm")[:16],
        "task": str(fields.get("task") or "unknown")[:60],
        "resolved_by": _rung(fields)[:20],
        "tier": (str(fields["tier"])[:16] if fields.get("tier") else None),
        "provider": (str(fields["provider"])[:40] if fields.get("provider") else None),
        "model": (str(fields["model"])[:120] if fields.get("model") else None),
        "prompt": prompt,
        "response": (response if isinstance(response, str) else None),
        "structured": structured if isinstance(structured, (dict, list)) else None,
        "input_was_redacted": bool(fields.get("input_was_redacted")),
        "tokens": _int_or_none(fields.get("tokens")),
        "latency_ms": _int_or_none(fields.get("latency_ms")),
        "success": bool(fields.get("success", True)),
        "error": (str(fields["error"])[:300] if fields.get("error") else None),
    }


def sink(fields: dict[str, Any]) -> None:
    """Receive one recorded attempt. Synchronous, non-blocking, never raises.

    Called on the event loop from inside inference. Everything expensive —
    flattening aside — happens in the drain.
    """
    global _dropped
    try:
        if not _consented.get():
            return
        if _queue is None:
            return
        row = build_row(fields)
        if row is None:
            return
        _queue.put_nowait(row)
    except asyncio.QueueFull:
        _dropped += 1
        # Every 100th, so a sustained outage says so without flooding the log.
        if _dropped % 100 == 1:
            logger.warning(
                "inference corpus: queue full, %d samples dropped so far "
                "(inference is unaffected)", _dropped,
            )
    except Exception:  # noqa: BLE001 — a sink must never break inference
        logger.debug("inference corpus sink error", exc_info=True)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _drain_loop() -> None:
    """Write queued samples with a session of our own, forever, never raising."""
    from app.core.database import async_session

    assert _queue is not None
    while True:
        row = await _queue.get()
        batch = [row]
        # Opportunistically take whatever else is already waiting: one commit
        # for a burst rather than one per sample.
        while len(batch) < 50:
            try:
                batch.append(_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        try:
            async with async_session() as db:
                db.add_all([InferenceSample(**r) for r in batch])
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            # Losing samples is survivable; a crashed drain is not, because it
            # would silently stop the corpus while everything looked healthy.
            logger.warning("inference corpus: could not persist %d samples: %s",
                           len(batch), exc)
        finally:
            for _ in batch:
                _queue.task_done()


def start() -> None:
    """Register the sink and start the drain. Idempotent."""
    global _queue, _drain
    if _drain is not None and not _drain.done():
        return
    from alafia_model import telemetry

    _queue = asyncio.Queue(maxsize=MAX_QUEUED)
    _drain = asyncio.create_task(_drain_loop())
    telemetry.register_sink(sink)
    logger.info("ALAFIA training corpus: sink registered, drain started")


async def stop() -> None:
    """Stop the drain. Used by tests; a process exit does not need it."""
    global _drain
    from alafia_model import telemetry

    telemetry.clear_sinks()
    if _drain is not None:
        _drain.cancel()
        try:
            await _drain
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _drain = None


async def corpus_stats(db) -> dict[str, Any]:
    """How much ALAFIA has to learn from, and from which rung it came."""
    total = (await db.execute(select(func.count(InferenceSample.id)))).scalar() or 0
    untrained = (await db.execute(
        select(func.count(InferenceSample.id)).where(InferenceSample.trained_on.is_(False))
    )).scalar() or 0
    by_rung = dict((await db.execute(
        select(InferenceSample.resolved_by, func.count())
        .group_by(InferenceSample.resolved_by)
    )).all())
    by_modality = dict((await db.execute(
        select(InferenceSample.modality, func.count())
        .group_by(InferenceSample.modality)
    )).all())
    return {
        "samples": total,
        "untrained": untrained,
        "by_rung": by_rung,
        "by_modality": by_modality,
        "dropped_this_process": _dropped,
    }


async def purge_user(db, user_id: int) -> int:
    """Delete a user's samples. Withdrawing consent must remove what was kept."""
    rows = (await db.execute(
        select(InferenceSample).where(InferenceSample.user_id == user_id)
    )).scalars().all()
    for row in rows:
        await db.delete(row)
    await db.commit()
    return len(rows)
