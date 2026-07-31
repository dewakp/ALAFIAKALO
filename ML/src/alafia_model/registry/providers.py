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

import os
import random
import time
from dataclasses import dataclass, field

# How long to skip a provider after a quota / rate-limit / auth error (seconds).
_COOLDOWN_SECONDS = float(os.environ.get("ALAFIA_PROVIDER_COOLDOWN", "120"))
_cooldown_until: dict[str, float] = {}


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

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "") if self.api_key_env else ""

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def resolved_model(self) -> str:
        # Per-provider model override, e.g. GROQ_MODEL, GEMINI_MODEL.
        return os.environ.get(f"{self.name.upper()}_MODEL", "") or self.model


# ── The exhaustive pool. Free tiers first (higher weight), then cheap/paid. ──
PROVIDERS: list[ProviderSpec] = [
    # ---- Free tier (use these up first) ----
    ProviderSpec("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-2.0-flash", "free", 3.0),
    ProviderSpec("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile", "free", 3.0),
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
    ProviderSpec("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "deepseek-chat", "paid", 2.0),
    ProviderSpec("moonshot", "https://api.moonshot.ai/v1", "MOONSHOT_API_KEY", "moonshot-v1-8k", "paid", 1.0),
    ProviderSpec("together", "https://api.together.xyz/v1", "TOGETHER_API_KEY", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "paid", 1.0),
    ProviderSpec("fireworks", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "accounts/fireworks/models/llama-v3p3-70b-instruct", "paid", 1.0),
    ProviderSpec("deepinfra", "https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY", "meta-llama/Llama-3.3-70B-Instruct", "paid", 1.0),
    ProviderSpec("xai", "https://api.x.ai/v1", "XAI_API_KEY", "grok-2-latest", "paid", 1.0),
    ProviderSpec("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini", "paid", 1.0),
    ProviderSpec("perplexity", "https://api.perplexity.ai", "PERPLEXITY_API_KEY", "sonar", "paid", 0.5),
    # ---- Native format ----
    ProviderSpec("anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "claude-3-5-haiku-latest", "paid", 1.0, kind="anthropic"),
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
