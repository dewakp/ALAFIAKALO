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
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.record_tools import TOOL_SPECS, run_tool

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


async def answer_with_tools(
    db: AsyncSession,
    user_id: int,
    system_prompt: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> Conversation:
    """Run the question to an answer, executing whatever tools the model calls."""
    from app.services.alafia_model_service import alafia_chat_detailed

    # The model must not be asked to know the date. Tools default to today when
    # a date is omitted; saying so here stops it inventing one from its training
    # cutoff, which is exactly what happened (it called get_meals for 2024-12-19).
    system_prompt = system_prompt + (
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
        "and offer to check their record.")
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
            prompt.append({
                "role": "system",
                "content": "You have no further tool calls available. Answer now "
                           "with what you have, and state plainly anything you "
                           "could not check.",
            })

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
            out.text = text
            return out

        # Execute every call the model made, in order.
        results = []
        for call in calls:
            result = await run_tool(db, user_id, call["name"], call.get("arguments") or {})
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
