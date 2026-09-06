"""The tool loop: let the model ask for what it needs, until it can answer.

This is what replaces guessing at the question. Previously the backend decided
in advance which slice of the record to attach — by keyword table, then by
sending everything, then by a token-overlap score that picked NUTRITION LOGS
for "what medications am I taking?". All three were the same mistake: the
backend trying to understand the question.

Here the model reads the question, calls for the data it needs, reads the
result, and calls again if the answer is not yet in hand. "Why am I purging?"
fetches eliminations, and — if what comes back warrants it — medications and
vitals, without anyone having predicted that sequence.

Bounded on purpose. `MAX_ROUNDS` stops a model that keeps asking; every tool
result is recorded so a caller can show its working; and when the rounds run
out the model is told to answer with what it has rather than being cut off
mid-thought.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.record_tools import TOOL_LABELS, TOOL_SPECS, run_tool

logger = logging.getLogger(__name__)

#: A question needing more than this many rounds is one the model cannot
#: answer from the record; further rounds burn latency without converging.
MAX_ROUNDS = 4

#: Tool results are JSON. A single enormous one would crowd out the question,
#: so it is truncated with a marker the model can act on.
_MAX_RESULT_CHARS = 24_000


@dataclass
class ToolTrace:
    """What was fetched, so an answer can be shown to have come from the record."""

    name: str
    arguments: dict[str, Any]
    summary: str


@dataclass
class Conversation:
    text: str
    rounds: int = 0
    traces: list[ToolTrace] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    tokens_used: int = 0


def _summarise(name: str, result: dict[str, Any]) -> str:
    """A one-line description of what a tool returned, for the trace."""
    if "error" in result:
        return f"{name}: {result['error']}"
    counts = [f"{k}={len(v)}" for k, v in result.items() if isinstance(v, list)]
    if "count" in result:
        counts.append(f"count={result['count']}")
    return f"{name}: " + (", ".join(counts) or "ok")


#: Appended to the caller's system prompt by BOTH loops. Shared deliberately:
#: two copies of the instructions is how the streaming path and the buffered one
#: start answering the same question differently.
_TOOL_LOOP_INSTRUCTIONS = (
    "\n\nYou do not know today's date and must never guess one. To ask about "
    "today, OMIT the date arguments — the server fills in the current date. "
    "Only pass explicit dates when the patient names a specific past date."
    "\n\nThree kinds of question reach you, and they need different things:"
    "\n• ABOUT THIS PATIENT ('what did I eat', 'why am I purging', 'is my "
    "potassium high') — call tools. Never answer these from memory."
    "\n• GENERAL CLINICAL KNOWLEDGE ('what are the food restrictions for an "
    "adult coeliac patient', 'what is a normal potassium level') — answer "
    "from your own knowledge. Do NOT call tools and do NOT say the record "
    "lacks the information: the question is not about this patient's record."
    "\n• BOTH ('given my labs, should I change my potassium') — fetch what "
    "you need, then combine it with what you know."
    "\nIf a general question could also be made specific, answer generally "
    "and offer to check their record."
)

#: Said out loud rather than truncating silently: an answer built on partial
#: data must be able to declare itself partial.
_FINAL_ROUND_INSTRUCTION = (
    "You have no further tool calls available. Answer now with what you have, "
    "and state plainly anything you could not check."
)


def _display_detail(result: dict[str, Any]) -> str:
    """What to SHOW for a finished tool call — not the log line.

    `_summarise` writes "get_meals: meals=6, count=6", which is right for the
    log and wrong on a patient's screen. Counting the rows keeps it honest:
    "nothing recorded" is a real finding and must not read as a failure, and a
    failure must not read as an empty result (§3aa).
    """
    if "error" in result:
        return "could not read that"
    total = sum(len(v) for v in result.values() if isinstance(v, list))
    if not total:
        return "nothing recorded"
    return f"{total} found"


async def answer_with_tools(
    db: AsyncSession,
    user_id: int,
    system_prompt: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    today: date | None = None,
    progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> Conversation:
    """Run the question to an answer, executing whatever tools the model calls.

    `progress` receives a dict per step so a streaming caller can show what is
    actually happening. The tool rounds take tens of seconds and cannot stream
    (the model must read each result before it knows what to ask next), so
    without this the patient watches a blinking cursor for the whole wait.

    These are REPORTS, not decoration: every one names a step the server really
    took. Inventing a reassuring sequence would be the §0 failure dressed as UX.
    """
    async def _say(**event: Any) -> None:
        if progress is not None:
            try:
                await progress(event)
            except Exception:  # noqa: BLE001
                # A display problem must never fail the answer.
                logger.debug("progress callback failed", exc_info=True)
    from app.services.alafia_model_service import alafia_chat_detailed

    # The model must not be asked to know the date. Tools default to today when
    # a date is omitted; saying so here stops it inventing one from its training
    # cutoff, which is exactly what happened (it called get_meals for 2024-12-19).
    system_prompt = system_prompt + _TOOL_LOOP_INSTRUCTIONS
    convo: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    convo.extend(messages)

    out = Conversation(text="")
    for round_no in range(1, MAX_ROUNDS + 1):
        out.rounds = round_no
        last = round_no == MAX_ROUNDS
        prompt = list(convo)
        if last:
            # Say so rather than truncating silently: an answer built on
            # partial data must be able to declare itself partial.
            prompt.append({"role": "system", "content": _FINAL_ROUND_INSTRUCTION})

        await _say(
            phase="thinking",
            label="Querying AI…" if round_no == 1 else "Reading what came back…",
            round=round_no,
        )
        completion = await alafia_chat_detailed(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=None if last else TOOL_SPECS,
        )
        out.provider = completion.get("provider") or out.provider
        out.model = completion.get("model") or out.model
        out.tokens_used += int(completion.get("tokens_used") or 0)

        calls = completion.get("tool_calls") or []
        text = (completion.get("text") or "").strip()

        if not calls:
            await _say(phase="composing", label="Writing your answer…")
            out.text = text
            return out

        # Execute every call the model made, in order.
        results = []
        for call in calls:
            await _say(
                phase="tool", tool=call["name"],
                label=TOOL_LABELS.get(call["name"], "Checking your record"),
            )
            result = await run_tool(db, user_id, call["name"],
                                    call.get("arguments") or {}, today)
            payload = json.dumps(result, default=str)
            if len(payload) > _MAX_RESULT_CHARS:
                payload = payload[:_MAX_RESULT_CHARS] + '…","truncated":true}'
            results.append({"id": call["id"], "name": call["name"], "content": payload})
            out.traces.append(ToolTrace(
                name=call["name"],
                arguments=call.get("arguments") or {},
                summary=_summarise(call["name"], result),
            ))
            logger.info("ai tool round=%d %s", round_no,
                        _summarise(call["name"], result))
            await _say(
                phase="tool_done", tool=call["name"],
                label=TOOL_LABELS.get(call["name"], "Checked your record"),
                detail=_display_detail(result),
            )

        convo.extend(_result_turns(calls, results))

    out.text = out.text or "I could not complete that from your record."
    return out


def _result_turns(calls: list[dict], results: list[dict]) -> list[dict]:
    """Assistant turn + tool results, in the shape the dispatcher normalises.

    Kept provider-neutral here; `alafia_chat_detailed` hands it to whichever
    adapter serves the request, and each translates to its own wire format.
    """
    return [
        {"role": "assistant", "tool_calls": calls},
        *[{"role": "tool", "tool_call_id": r["id"], "name": r["name"],
           "content": r["content"]} for r in results],
    ]


async def stream_with_tools(
    db: AsyncSession,
    user_id: int,
    system_prompt: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    today: date | None = None,
):
    """The tool loop, streaming the answer as the model writes it.

    `answer_with_tools` generates each round in full before anyone sees it, so
    even a 5-second production answer showed nothing for ~3.5s and then arrived
    all at once. The rounds themselves still cannot be streamed away — the model
    must read each tool result before it knows what to ask next — but the round
    that finally ANSWERS can be, and that is where nearly all the waiting is.

    Yields the same dicts as the progress callback plus text:

        {"phase": ...,  "label": ...}      a step being taken
        {"text": "..."}                    answer text, as it is written
        {"done": Conversation}             the finished conversation, last

    Text is streamed optimistically: a round that turns out to be a tool call
    normally emits no prose, but any it did emit is retracted with
    `{"retract": n}` rather than left on screen as part of an answer it was
    never part of.
    """
    from app.services.alafia_model_service import stream_alafia_events

    system_prompt = system_prompt + _TOOL_LOOP_INSTRUCTIONS
    convo: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    convo.extend(messages)

    out = Conversation(text="")
    for round_no in range(1, MAX_ROUNDS + 1):
        out.rounds = round_no
        last = round_no == MAX_ROUNDS
        prompt = list(convo)
        if last:
            prompt.append({"role": "system", "content": _FINAL_ROUND_INSTRUCTION})

        yield {"phase": "thinking",
               "label": "Querying AI…" if round_no == 1 else "Reading what came back…",
               "round": round_no}

        text_parts: list[str] = []
        streamed = 0
        calls: list[dict[str, Any]] = []
        async for event in stream_alafia_events(
            prompt, tools=None if last else TOOL_SPECS,
            temperature=temperature, max_tokens=max_tokens,
        ):
            if event.get("type") == "text":
                chunk = event["text"]
                text_parts.append(chunk)
                streamed += len(chunk)
                yield {"text": chunk}
            elif event.get("type") == "tool_calls":
                calls = event["calls"]

        if not calls:
            out.text = "".join(text_parts).strip()
            yield {"phase": "composing", "label": "Writing your answer…"}
            yield {"done": out}
            return

        # This round was a fetch, not the answer. Anything shown must come back:
        # leaving it would splice a fragment of the model's reasoning onto the
        # front of an answer it does not belong to.
        if streamed:
            yield {"retract": streamed}

        results = []
        for call in calls:
            yield {"phase": "tool", "tool": call["name"],
                   "label": TOOL_LABELS.get(call["name"], "Checking your record")}
            result = await run_tool(db, user_id, call["name"],
                                    call.get("arguments") or {}, today)
            payload = json.dumps(result, default=str)
            if len(payload) > _MAX_RESULT_CHARS:
                payload = payload[:_MAX_RESULT_CHARS] + '…","truncated":true}'
            results.append({"id": call["id"], "name": call["name"], "content": payload})
            out.traces.append(ToolTrace(
                name=call["name"], arguments=call.get("arguments") or {},
                summary=_summarise(call["name"], result),
            ))
            logger.info("ai tool round=%d %s", round_no, _summarise(call["name"], result))
            yield {"phase": "tool_done", "tool": call["name"],
                   "label": TOOL_LABELS.get(call["name"], "Checked your record"),
                   "detail": _display_detail(result)}

        convo.extend(_result_turns(calls, results))

    out.text = out.text or "I could not complete that from your record."
    yield {"done": out}
