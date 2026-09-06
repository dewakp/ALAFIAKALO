"""ALAFIAModel LLM Capability — Health Coaching & Clinical Reasoning.

Phase 3 (planned): Fine-tuned BioMistral 7B served via Ollama for:
  - Health coaching chat (personalized to ALAFIA user profile)
  - Nutrition guidance with RAG over USDA + WAFCT
  - CBT-style mental health support (with safety guardrails)
  - Exercise recommendation formatting

Current behavior: Routes to adapter layer (Ollama local → OpenAI fallback).
All calls are logged with TODO(alafia-model) markers so we can track
migration progress.

TODO(alafia-model): Phase 3 — fine-tune BioMistral 7B on ALAFIA health coaching data
TODO(alafia-model): Phase 4 — build RAG index over USDA + WAFCT and wire into LLM infer
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)

_HEALTH_SYSTEM_PROMPT = """\
You are ALAFIA's AI health coach. You provide personalized, evidence-based
health and wellness guidance. You are knowledgeable about nutrition, exercise,
chronic disease management, and preventive care.

Guidelines:
- Always recommend consulting a healthcare provider for medical decisions
- Use plain, empathetic language appropriate for non-clinical users
- Reference West African, African diaspora, and global food traditions
- Never diagnose; guide toward professional care when symptoms arise
- Keep responses concise and actionable
"""

_NUTRITION_SYSTEM_PROMPT = """\
You are ALAFIA's nutrition AI. You provide personalized dietary guidance
grounded in clinical nutrition science and global food traditions.
You have deep knowledge of West African, South Asian, Caribbean, and
Western food composition from USDA SR Legacy, WAFCT 2019, and IFCT.
"""



def _env_flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("true", "1", "yes")


def _ollama_first() -> bool:
    """Try Ollama ahead of the hosted pool. ON in dev, OFF in production.

    Production's Ollama is scale-to-zero on Cloud Run, so a cold call costs ~250 s
    (canon 5). That is the right price for a fallback and the wrong one for a
    front door.
    """
    return _env_flag("OLLAMA_FIRST")


def _ollama_required() -> bool:
    """Whether a dead Ollama is a hard failure rather than a fallback trigger.

    ON in dev, OFF everywhere else. Dev wants the loud error: a hosted provider
    quietly standing in is exactly how the AI tier went unproven locally.
    Production wants the fallback — there it is the difference between a degraded
    answer and no answer at all for a real patient. Only consulted when
    OLLAMA_FIRST is set.
    """
    return _env_flag("OLLAMA_REQUIRED")


class LLMCapability(BaseCapability):
    """LLM (Language Model) capability for health coaching and clinical reasoning.

    Current status: Delegates to adapter layer (Ollama → OpenAI).
    Target state: Fine-tuned BioMistral 7B running on ALAFIA's own GPU VM.

    Supported tasks:
        "health_chat"        → conversational health coaching
        "nutrition_guidance" → dietary advice with food context
        "symptom_triage"     → guide user to appropriate care level [PLANNED]
        "cbt_support"        → CBT-style mental health guidance [PLANNED]
    """

    capability_id = "llm"
    version = "0.1.0-adapter-delegation"
    is_implemented = True  # Implemented via adapter delegation

    def __init__(self) -> None:
        super().__init__()
        self._adapter: Any = None
        self._fallback: Any = None
        self._pool: dict[str, Any] = {}   # provider name → cached adapter

    def _get_adapter(self, model: str | None = None) -> Any:
        from alafia_model.adapters.ollama_adapter import OllamaAdapter
        # A per-call model override gets its own (uncached) adapter so it doesn't
        # disturb the shared default instance.
        if model:
            if self._adapter is not None and getattr(self._adapter, "model_name", None) == model:
                return self._adapter
            return OllamaAdapter(model=model)
        if self._adapter is None:
            self._adapter = OllamaAdapter()
        return self._adapter

    def _adapter_for(self, spec) -> Any:
        """Build (and cache) the adapter for a registry provider spec."""
        cached = self._pool.get(spec.name)
        if cached is not None:
            return cached
        if spec.kind == "anthropic":
            from alafia_model.adapters.anthropic_adapter import AnthropicAdapter
            adapter = AnthropicAdapter(api_key=spec.api_key, model=spec.resolved_model())
        else:
            from alafia_model.adapters.openai_compat_adapter import OpenAICompatAdapter
            from alafia_model.registry.providers import base_url_for
            adapter = OpenAICompatAdapter(
                provider=spec.name,
                base_url=base_url_for(spec),
                api_key=spec.api_key,
                model=spec.resolved_model(),
                extra_headers=spec.extra_headers,
            )
        self._pool[spec.name] = adapter
        return adapter

    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        task = payload.get("task", "health_chat")
        messages = payload.get("messages", [])
        context = payload.get("context", {})
        temperature = payload.get("temperature", 0.7)
        max_tokens = payload.get("max_tokens", 2048)
        json_mode = bool(payload.get("json_mode", False))
        model = payload.get("model") or None
        # Hosted providers carry the load, deliberately: production's Ollama is
        # scale-to-zero and warming it is a standing cost decision (canon 5), so
        # a ~250 s cold call is the wrong front door. The privacy guarantee
        # therefore rests ENTIRELY on redaction at the egress point below — the
        # patient's IDENTITY is stripped, never their clinical detail, which the
        # model needs to answer at all.
        #
        # `local_only=True` stays available for anything that must not leave
        # regardless, and is what the tests use to pin that boundary.
        local_only = bool(payload.get("local_only", False))
        tools = payload.get("tools") or None
        # Extra identifiers for this call. The signed-in user's own name, email
        # and phone are picked up from the request context inside `scrub_payload`
        # — a hint each caller must remember is one someone eventually forgets.
        identity_hints = tuple(payload.get("identity_hints") or ())

        # Tasks that prepend an ALAFIA system prompt
        if task == "health_chat":
            system = _HEALTH_SYSTEM_PROMPT
            if context.get("user_profile"):
                system += f"\n\nUser profile context:\n{context['user_profile']}"
            return await self._chat(system, messages, temperature, max_tokens, json_mode, model, local_only, identity_hints, tools)

        if task == "nutrition_guidance":
            system = _NUTRITION_SYSTEM_PROMPT
            if context.get("nutrition_summary"):
                system += f"\n\nRecent nutrition summary:\n{context['nutrition_summary']}"
            return await self._chat(system, messages, temperature, max_tokens, json_mode, model, local_only, identity_hints, tools)

        # Generic passthrough — the caller supplies its own system message (if any).
        # This is the entry point backend services use so every LLM call is routed
        # through ALAFIAModel rather than hitting Ollama/OpenAI directly.
        if task in ("chat", "raw_chat", "health_coaching"):
            # `tools` belongs here most of all: this is the generic passthrough
            # every backend service uses, so omitting it here meant tools were
            # threaded through six call sites and dropped at the only one that
            # runs.
            return await self._chat(None, messages, temperature, max_tokens, json_mode,
                                    model, local_only, identity_hints, tools)

        # Single-prompt completion (maps to /api/generate style structured output).
        if task == "complete":
            return await self._complete(payload.get("text", ""), temperature, max_tokens, model, local_only, identity_hints)

        if task in ("symptom_triage", "cbt_support"):
            return CapabilityResult(
                success=False,
                error=f"LLM task '{task}' is planned but not yet implemented. See ALAFIAModel Phase 3.",
            )
        return CapabilityResult(
            success=False,
            error=f"Unknown LLM task: {task}",
        )

    # ── Internal dispatch with Ollama → OpenAI fallback ────────────────────────

    async def _chat(
        self,
        system: str | None,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        model: str | None = None,
        local_only: bool = False,
        identity_hints: tuple[str, ...] = (),
        tools: list[dict] | None = None,
    ) -> CapabilityResult:
        # TODO(alafia-model): replace adapters with native fine-tuned BioMistral 7B
        full_messages = ([{"role": "system", "content": system}] if system else []) + list(messages)
        return await self._dispatch("chat", full_messages, temperature, max_tokens, json_mode,
                                    model, local_only, identity_hints, tools)

    async def _complete(
        self, prompt: str, temperature: float, max_tokens: int, model: str | None = None,
        local_only: bool = False,
        identity_hints: tuple[str, ...] = (),
    ) -> CapabilityResult:
        return await self._dispatch("complete", prompt, temperature, max_tokens, True,
                                    model, local_only, identity_hints)

    async def _dispatch(
        self, kind: str, arg: Any, temperature: float, max_tokens: int, json_mode: bool,
        model: str | None = None, local_only: bool = False,
        identity_hints: tuple[str, ...] = (),
        tools: list[dict] | None = None,
    ) -> CapabilityResult:
        """Dispatch across Ollama and the hosted provider pool. Order is per-environment.

        The two environments want OPPOSITE orders, and picking one globally is
        wrong in whichever half it is not:

          dev  — Ollama FIRST and REQUIRED. It is free, never rate-limited, keeps
                 user content on our own infrastructure, and is what production
                 ultimately runs. If it is down the dispatch fails loudly, because
                 a hosted provider quietly standing in is precisely how the AI tier
                 stayed unproven locally while every AI change was checked in prod.

          prod — hosted providers FIRST, Ollama as the terminal fallback. Prod's
                 Ollama is Cloud Run with minScale unset (canon 5): a cold call
                 pays a ~77 s model load on top of generation, about 250 s all in.
                 Preferring it there would put that on every request to save a few
                 cents — the fallback is the point, not the front door.

        Controlled by OLLAMA_FIRST / OLLAMA_REQUIRED, both set in
        WEB/docker-compose.yml and both off by default. Every attempt is recorded
        for the ALAFIA-model training corpus (telemetry)."""
        from alafia_model.registry.providers import ordered_for_selection, mark_cooldown
        from alafia_model import privacy, telemetry

        chat_msgs = arg if kind == "chat" else None
        state = {"cloud_error": None, "ollama_error": None}

        async def try_ollama() -> CapabilityResult | None:
            ollama = self._get_adapter(model)
            t0 = time.monotonic()
            try:
                resp = await self._call(ollama, kind, arg, temperature, max_tokens,
                                        json_mode, tools)
                telemetry.record(
                    provider="ollama", model=resp.get("model"), task=kind, tier="local",
                    latency_ms=int((time.monotonic() - t0) * 1000), tokens=resp.get("tokens_used", 0),
                    success=True, messages=chat_msgs, response=resp.get("content"),
                )
                return CapabilityResult(
                    success=True,
                    data={
                        "text": resp["content"],
                        # A tool call is the answer to "what do you need?" and
                        # must not be dropped between adapter and caller.
                        "tool_calls": resp.get("tool_calls") or [],
                        "tokens_used": resp.get("tokens_used", 0),
                        "model": resp.get("model", ollama.model_name),
                        "provider": "ollama",
                    },
                    confidence=0.75,
                    source=f"ollama:{resp.get('model', ollama.model_name)}",
                )
            except Exception as exc:
                # Name the TYPE: httpx timeouts carry an empty str(), which once
                # rendered as "all providers failed (last: )" and sent an operator
                # hunting a healthy service.
                state["ollama_error"] = f"{type(exc).__name__}: {exc}".rstrip(": ")
                telemetry.record(provider="ollama", task=kind, tier="local", success=False,
                                 error=str(exc)[:300])
                logger.warning("ollama %s failed (%s)", kind, exc)
                return None

        async def try_hosted() -> CapabilityResult | None:
            # Nothing leaves for a third party wearing the patient's identity.
            # Redaction happens HERE, at the single egress point, rather than in
            # each caller: free text is written by patients who type their own
            # name, their clinician's, an email or a phone number without
            # thinking about it, and a new call site cannot forget a step it
            # never had to take. The subject is identified to a provider only by
            # `privacy.subject_token()` — our handle, meaningless to them.
            outbound = privacy.scrub_payload(arg, identity_hints)
            # When the request carries tools, providers that cannot accept them
            # are skipped BEFORE selection — one of them answering in prose is
            # indistinguishable from success and strands the caller.
            #
            # Called WITHOUT the keyword on the ordinary path so the signature
            # every existing caller and test stub relies on is unchanged; the
            # narrowing applies only to requests that actually carry tools.
            _specs = (ordered_for_selection(require_tools=True) if tools
                      else ordered_for_selection())
            for spec in _specs:
                t0 = time.monotonic()
                try:
                    resp = await self._call(self._adapter_for(spec), kind, outbound,
                                            temperature, max_tokens, json_mode, tools)
                    telemetry.record(
                        provider=spec.name, model=resp.get("model"), task=kind, tier=spec.tier,
                        latency_ms=int((time.monotonic() - t0) * 1000), tokens=resp.get("tokens_used", 0),
                        success=True,
                        messages=outbound if kind == "chat" else chat_msgs,
                        response=resp.get("content"),
                    )
                    return CapabilityResult(
                        # tokens_used/model travel in `data`, not just telemetry: the
                        # backend records per-user usage from here, and dropping them
                        # is why AIInteraction.tokens_used was always 0.
                        success=True,
                        data={
                            "text": resp["content"],
                            # Same on the hosted path: dropping tool_calls here
                            # would make the model's request for data look like
                            # an empty answer.
                            "tool_calls": resp.get("tool_calls") or [],
                            "tokens_used": resp.get("tokens_used", 0),
                            "model": resp.get("model", spec.resolved_model()),
                            "provider": spec.name,
                        },
                        confidence=0.7,
                        source=f"{spec.name}:{resp.get('model', spec.resolved_model())}",
                    )
                except Exception as exc:
                    state["cloud_error"] = str(exc)
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    blob = str(exc).lower()
                    if status in (401, 402, 403, 429) or "quota" in blob or "rate" in blob or "insufficient" in blob:
                        mark_cooldown(spec.name)  # back this provider off; free tier likely spent
                    telemetry.record(
                        provider=spec.name, task=kind, tier=spec.tier,
                        latency_ms=int((time.monotonic() - t0) * 1000), success=False, error=str(exc)[:300],
                    )
                    logger.warning("provider %s %s failed (%s); trying next", spec.name, kind, exc)
            return None

        if local_only:
            # PHI boundary. The prompt carries patient material, so ALAFIA-operated
            # inference is the ONLY permitted destination — there is no fallback,
            # because "the local model was busy" is not a reason to disclose a
            # patient's conditions to a third party. A failure here is an outage;
            # a silent hosted retry would be a privacy breach that no log records.
            result = await try_ollama()
            if result is not None:
                return result
            detail = state["ollama_error"] or "no error reported"
            logger.error("local-only LLM call failed; refusing hosted fallback (%s)", detail)
            return CapabilityResult(
                success=False,
                error=("LLM unavailable: this request carries health data and may only be "
                       f"answered by ALAFIA-operated inference, which failed ({detail}). "
                       "It was NOT sent to any third-party provider."),
            )

        if _ollama_first():
            result = await try_ollama()
            if result is not None:
                return result
            if _ollama_required():
                # Loud, not silent. Standing a hosted provider in here would make
                # dev green on a path production does not run.
                detail = state["ollama_error"]
                logger.error("OLLAMA_REQUIRED is set and Ollama is unreachable: %s", detail)
                return CapabilityResult(
                    success=False,
                    error=("LLM unavailable: Ollama is required in this environment and could "
                           f"not be reached ({detail}). Start it on the host with "
                           "`OLLAMA_HOST=0.0.0.0:11434 ollama serve` — the default localhost "
                           "bind is not reachable from the container — or set "
                           "OLLAMA_REQUIRED=false to allow hosted providers."),
                )
            result = await try_hosted()
        else:
            result = await try_hosted()
            if result is None:
                result = await try_ollama()

        if result is not None:
            return result

        logger.error("all LLM providers failed; ollama=%s last cloud=%s",
                     state["ollama_error"], state["cloud_error"])
        detail = state["cloud_error"] or state["ollama_error"] or "no provider produced an error"
        return CapabilityResult(
            success=False,
            error=f"LLM unavailable: all providers failed (last: {detail})",
        )

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        identity_hints: tuple = (),
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """Text-only view of `stream_events`. Unchanged for every caller.

        Implemented on top of the event stream rather than beside it so the
        provider order and the redaction below have exactly ONE implementation:
        two copies is how a fix lands on one path and misses the other (§3ae).
        """
        async for event in self.stream_events(
            messages, tools=None, identity_hints=identity_hints,
            temperature=temperature, max_tokens=max_tokens,
        ):
            if event.get("type") == "text":
                yield event["text"]

    async def stream_events(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict] | None = None,
        identity_hints: tuple = (),
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """Stream a chat completion through the SAME egress point as `run()`.

        `/ai/chat/stream` used to POST straight to Ollama, so token streaming was
        the one LLM path that never passed `privacy.scrub_payload`, never
        consulted the provider order, and could never reach Anthropic — while
        APP_REVIEW_RESPONSE.md told Apple that Anthropic was the primary provider
        and our own servers were the fallback.

        The redaction below is the reason this lives here rather than in the
        endpoint: a caller that has to remember to scrub is a caller that
        eventually forgets, and what gets forgotten is a patient's name reaching
        a vendor (CLAUDE.md §3al).

        Provider order matches `run()`: hosted first in production, Ollama first
        in dev, Ollama always the fallback. Yields text chunks.
        """
        from alafia_model import privacy
        from alafia_model.registry.providers import ordered_for_selection, mark_cooldown

        def _events_from(adapter):
            """The adapter's event stream, or its text stream adapted to one.

            An adapter that only implements `stream_chat` can still serve a
            text-only request, and refusing it would drop a funded provider for
            no reason. But when the request carries TOOLS it must be skipped:
            a provider that answers in prose instead of calling is worse than
            one that refuses, because the caller waits for a call that never
            comes (§3am).
            """
            events = getattr(adapter, "stream_chat_events", None)
            if events is not None:
                def _run(msgs, temp, maxt):
                    return events(msgs, temp, maxt, tools)
                return _run
            if tools:
                return None
            text_only = getattr(adapter, "stream_chat", None)
            if text_only is None:
                return None

            async def _wrap(msgs, temp, maxt):
                async for chunk in text_only(msgs, temp, maxt):
                    yield {"type": "text", "text": chunk}
            return _wrap

        async def _stream_ollama():
            adapter = self._get_adapter(None)
            runner = _events_from(adapter)
            if runner is None:
                raise RuntimeError(
                    "ollama adapter cannot stream tool calls for this request")
            async for event in runner(messages, temperature, max_tokens):
                yield event

        async def _stream_hosted():
            # Redaction HERE, at the single egress point — identical to try_hosted().
            outbound = privacy.scrub_payload(messages, identity_hints)
            last_error = None
            # A provider that cannot take tools is skipped BEFORE selection when
            # the request carries them — one answering in prose is worse than one
            # refusing, because the caller waits for a call that never comes.
            specs = (ordered_for_selection(require_tools=True) if tools
                     else ordered_for_selection())
            for spec in specs:
                adapter = self._adapter_for(spec)
                runner = _events_from(adapter)
                if runner is None:
                    continue  # cannot stream, or cannot do tools; the next may
                try:
                    produced = False
                    async for event in runner(outbound, temperature, max_tokens):
                        produced = True
                        yield event
                    if produced:
                        return
                except Exception as exc:  # noqa: BLE001 — try the next provider
                    last_error = f"{type(exc).__name__}: {exc}".rstrip(": ")
                    logger.warning("streaming via %s failed (%s)", spec.name, last_error)
                    mark_cooldown(spec.name)
                    continue
            if last_error:
                # Named, never blank: `str(httpx.ReadTimeout(''))` is '' and the
                # most likely failure would otherwise render as nothing (§3ae).
                raise RuntimeError(f"all streaming providers failed (last: {last_error})")
            raise RuntimeError("no streaming-capable provider is configured")

        if _ollama_first():
            try:
                async for event in _stream_ollama():
                    yield event
                return
            except Exception as exc:  # noqa: BLE001
                if _ollama_required():
                    raise
                logger.warning("ollama streaming failed, falling back to hosted (%s)", exc)
            async for event in _stream_hosted():
                yield event
            return

        try:
            async for event in _stream_hosted():
                yield event
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("hosted streaming failed, falling back to ollama (%s)", exc)
        async for event in _stream_ollama():
            yield event


    @staticmethod
    async def _call(adapter, kind, arg, temperature, max_tokens, json_mode, tools=None):
        if kind == "chat":
            # `tools` is passed only when present so an adapter that predates
            # tool support still receives the call it expects.
            extra = {"tools": tools} if tools else {}
            return await adapter.chat(arg, temperature=temperature,
                                      max_tokens=max_tokens, json_mode=json_mode, **extra)
        return await adapter.complete(arg, temperature=temperature, max_tokens=max_tokens)
