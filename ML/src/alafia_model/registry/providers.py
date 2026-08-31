"""LLM provider registry — the round-robin pool.

Every hosted provider is one row here. A provider is ENABLED only when its API
key env var is set (keys come from Secret Manager in prod), so the pool grows as
keys are added — no code change. Selection is "free-first weighted round-robin":
pick randomly (by weight) among enabled, non-cooling, free-tier providers; on
quota/429 a provider is put on a short cooldown and the next is tried; free tiers
exhaust to paid, and everything ultimately falls back to self-hosted Ollama
(handled by the LLM capability, not listed here).

This is the backend realization of the "AI stays server-side" canon: the model
mix changes here, never in the web/iOS/Android clients.
"""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field

# How long to skip a provider after a quota / rate-limit / auth error (seconds).
_COOLDOWN_SECONDS = float(os.environ.get("ALAFIA_PROVIDER_COOLDOWN", "120"))
_cooldown_until: dict[str, float] = {}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str          # OpenAI-compatible base (…/v1); ignored for kind="anthropic"
    api_key_env: str       # env var holding the key
    model: str             # default model id for this provider
    tier: str = "free"     # "free" | "paid"
    weight: float = 1.0    # relative selection weight within its tier
    kind: str = "openai"   # "openai" (compat) | "anthropic"
    extra_headers: dict[str, str] = field(default_factory=dict)
    # Ordered substrings naming the FAMILY we want from this provider, best
    # first. Discovery picks the newest live model matching the earliest
    # preference that matches anything — so "haiku" keeps choosing the current
    # haiku as the provider ships new ones, without anyone editing this file.
    model_prefer: tuple[str, ...] = ()

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "") if self.api_key_env else ""

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def resolved_model(self) -> str:
        """Which model id to actually call, in order of authority.

        1. An explicit operator override (GROQ_MODEL, ANTHROPIC_MODEL, …).
        2. The newest live model discovered from the provider (see
           `refresh_provider_models`), cached in-process.
        3. `self.model` — the pinned default, and ONLY a last resort.

        The pin used to be the sole source, which is naive against providers
        that keep shipping: `claude-3-5-haiku-latest` was retired and every
        Anthropic call returned 404 not_found_error until someone read a log.
        A pin cannot notice that it has died; discovery can.
        """
        override = os.environ.get(f"{self.name.upper()}_MODEL", "")
        if override:
            return override
        discovered = _discovered_model(self.name)
        return discovered or self.model


# ══════════════════════════════════════════════════════════════════════════
# Live model discovery
# ══════════════════════════════════════════════════════════════════════════
# Hardcoding a model id is a bet that the provider will not move, and providers
# move constantly. `claude-3-5-haiku-latest` was pinned here, retired upstream,
# and returned 404 on EVERY Anthropic call — invisible until a user's meal
# failed to resolve, because a dead pin looks exactly like a dead account.
#
# So: ask the provider what it actually serves, cache it, and fall back to the
# pin only when the provider cannot be reached. Discovery is async and never on
# the request path — `resolved_model()` reads the cache and never blocks.

_MODEL_TTL_SECONDS = float(os.environ.get("ALAFIA_MODEL_DISCOVERY_TTL", "21600"))  # 6h
_MODEL_TTL_ON_FAILURE = 300.0   # re-try a failed provider sooner than a good one
_model_cache: dict[str, tuple[float, str]] = {}   # provider -> (expires_at, model_id)


def _discovered_model(provider: str) -> str:
    entry = _model_cache.get(provider)
    if entry and entry[0] > time.time():
        return entry[1]
    return ""


def invalidate_model(provider: str) -> None:
    """Drop a provider's cached model — call when it answers 'no such model'."""
    _model_cache.pop(provider, None)


def _select_model(spec: "ProviderSpec", models: list[dict]) -> str:
    """Newest model matching the earliest preference that matches anything.

    `models` entries are {id, created} — `created` is epoch seconds where the
    provider supplies it (Anthropic and the OpenAI-compatible APIs both do) and
    0 where it does not, in which case ordering falls back to the provider's own
    listing order, which is generally newest-last.
    """
    ids = [m for m in models if m.get("id")]
    if not ids:
        return ""
    for want in (spec.model_prefer or ()):
        matches = [m for m in ids if want in m["id"].lower()]
        if matches:
            return max(matches, key=lambda m: m.get("created") or 0)["id"]
    # No preference matched: refuse to guess. A wrong model is worse than the
    # pin, which at least was chosen deliberately.
    return ""


async def refresh_provider_models(spec: "ProviderSpec", *, timeout: float = 10.0) -> str:
    """Ask one provider what it serves; cache and return the selected model id."""
    import httpx

    if not spec.enabled:
        return ""
    try:
        if spec.kind == "anthropic":
            # Same builder the adapter uses, so an identity-linked key's
            # workspace header is never present on chat but missing on
            # discovery — which would silently pin the model to the fallback.
            from alafia_model.adapters.anthropic_adapter import anthropic_headers

            url = "https://api.anthropic.com/v1/models"
            headers = anthropic_headers(spec.api_key)
        else:
            url = f"{_resolve_base_url(spec).rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {spec.api_key}", **spec.extra_headers}

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("data") if isinstance(payload, dict) else payload
        models = [
            {"id": str(r.get("id") or ""), "created": r.get("created") or r.get("created_at") or 0}
            for r in (rows or []) if isinstance(r, dict)
        ]
        # created_at may be an ISO string (Anthropic); only epoch ints sort.
        for m in models:
            if not isinstance(m["created"], (int, float)):
                m["created"] = 0

        chosen = _select_model(spec, models)
        if chosen:
            _model_cache[spec.name] = (time.time() + _MODEL_TTL_SECONDS, chosen)
            if chosen != spec.model:
                logger.info("provider %s: using discovered model %r (pin was %r)",
                            spec.name, chosen, spec.model)
        else:
            # Reachable but nothing matched — keep the pin, retry sooner.
            _model_cache[spec.name] = (time.time() + _MODEL_TTL_ON_FAILURE, spec.model)
        return chosen
    except Exception as exc:
        logger.warning("provider %s: model discovery failed (%s: %s); keeping pin %r",
                       spec.name, type(exc).__name__, str(exc)[:120], spec.model)
        _model_cache[spec.name] = (time.time() + _MODEL_TTL_ON_FAILURE, spec.model)
        return ""


async def refresh_all_models() -> dict[str, str]:
    """Refresh every enabled provider. Safe to call at startup and on a timer."""
    import asyncio

    specs = [s for s in enabled_providers()]
    results = await asyncio.gather(
        *(refresh_provider_models(s) for s in specs), return_exceptions=True
    )
    return {s.name: (r if isinstance(r, str) else "") for s, r in zip(specs, results)}


# ── The exhaustive pool. Free tiers first (higher weight), then cheap/paid. ──
PROVIDERS: list[ProviderSpec] = [
    # ---- Free tier (use these up first) ----
    ProviderSpec("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-2.0-flash", "free", 3.0, model_prefer=("flash",)),
    ProviderSpec("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile", "free", 3.0, model_prefer=("llama",)),
    ProviderSpec("cerebras", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", "llama-3.3-70b", "free", 2.0),
    ProviderSpec("sambanova", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY", "Meta-Llama-3.3-70B-Instruct", "free", 2.0),
    ProviderSpec("mistral", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-small-latest", "free", 2.0),
    ProviderSpec("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "meta-llama/llama-3.3-70b-instruct:free", "free", 2.0,
                 extra_headers={"HTTP-Referer": "https://alafia.app", "X-Title": "ALAFIA"}),
    ProviderSpec("github", "https://models.inference.ai.azure.com", "GITHUB_MODELS_TOKEN", "gpt-4o-mini", "free", 1.5),
    ProviderSpec("nvidia", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", "meta/llama-3.3-70b-instruct", "free", 1.5),
    ProviderSpec("dashscope", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY", "qwen-plus", "free", 1.0),
    ProviderSpec("zhipu", "https://open.bigmodel.cn/api/paas/v4", "ZHIPU_API_KEY", "glm-4-flash", "free", 1.0),
    ProviderSpec("cloudflare", "", "CLOUDFLARE_API_TOKEN", "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "free", 1.0),  # base_url set from CLOUDFLARE_ACCOUNT_ID below
    # ---- Cheap / paid ----
    ProviderSpec("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "deepseek-chat", "paid", 2.0, model_prefer=("chat",)),
    ProviderSpec("moonshot", "https://api.moonshot.ai/v1", "MOONSHOT_API_KEY", "moonshot-v1-8k", "paid", 1.0, model_prefer=("moonshot",)),
    ProviderSpec("together", "https://api.together.xyz/v1", "TOGETHER_API_KEY", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "paid", 1.0),
    ProviderSpec("fireworks", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "accounts/fireworks/models/llama-v3p3-70b-instruct", "paid", 1.0),
    ProviderSpec("deepinfra", "https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY", "meta-llama/Llama-3.3-70B-Instruct", "paid", 1.0, model_prefer=("llama",)),
    ProviderSpec("xai", "https://api.x.ai/v1", "XAI_API_KEY", "grok-2-latest", "paid", 1.0),
    ProviderSpec("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini", "paid", 1.0, model_prefer=("mini",)),
    ProviderSpec("perplexity", "https://api.perplexity.ai", "PERPLEXITY_API_KEY", "sonar", "paid", 0.5),
    # ---- Native format ----
    # claude-haiku-4-5 replaces the retired claude-3-5-haiku-latest, which
    # returned 404 not_found_error ("model: claude-3-5-haiku-latest") on EVERY
    # call — a dead model id, not a billing failure, though it looked like one
    # sitting beside deepseek's 402 and openai's 429 in the same log.
    # Same tier as the id it replaces; use claude-opus-5 instead if you want the
    # fallback to be the strong model rather than the cheap fast one.
    ProviderSpec("anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "claude-haiku-4-5", "paid", 1.0, kind="anthropic", model_prefer=("haiku", "sonnet")),
]


def _resolve_base_url(spec: ProviderSpec) -> str:
    # Cloudflare Workers AI's OpenAI endpoint embeds the account id in the path.
    if spec.name == "cloudflare":
        acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        return f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1" if acct else ""
    return spec.base_url


def mark_cooldown(name: str, seconds: float | None = None) -> None:
    _cooldown_until[name] = time.monotonic() + (seconds if seconds is not None else _COOLDOWN_SECONDS)


def _is_cooling(name: str) -> bool:
    until = _cooldown_until.get(name)
    return until is not None and time.monotonic() < until


def enabled_providers() -> list[ProviderSpec]:
    """Providers with a configured key and a resolvable base_url."""
    out = []
    for s in PROVIDERS:
        if not s.enabled:
            continue
        if s.kind == "openai" and not _resolve_base_url(s):
            continue  # e.g. cloudflare without CLOUDFLARE_ACCOUNT_ID
        out.append(s)
    return out


def base_url_for(spec: ProviderSpec) -> str:
    return _resolve_base_url(spec)


def _weighted_shuffle(specs: list[ProviderSpec]) -> list[ProviderSpec]:
    """Random order, biased by weight (weighted sampling without replacement)."""
    pool = list(specs)
    ordered: list[ProviderSpec] = []
    while pool:
        total = sum(s.weight for s in pool) or 1.0
        r = random.uniform(0, total)
        upto = 0.0
        for i, s in enumerate(pool):
            upto += s.weight
            if r <= upto:
                ordered.append(pool.pop(i))
                break
        else:
            ordered.append(pool.pop())
    return ordered


def ordered_for_selection() -> list[ProviderSpec]:
    """Free-first weighted round-robin: free tier (shuffled) then paid (shuffled),
    skipping any provider currently on cooldown."""
    live = [s for s in enabled_providers() if not _is_cooling(s.name)]
    free = [s for s in live if s.tier == "free"]
    paid = [s for s in live if s.tier != "free"]
    return _weighted_shuffle(free) + _weighted_shuffle(paid)
