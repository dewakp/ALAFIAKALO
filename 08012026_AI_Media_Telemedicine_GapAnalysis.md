# AI · Voice · Video · Telemedicine — Instructions Surfaced vs. Delivery Gaps

> **Generated:** 2026-08-01 · **Against:** local HEAD `c7dd01b` (prod backend rev `00026` = `f9f7143`).
> **Why:** Per the request — *"Surface my original instructions (60+ days old) on AI architecture
> and provider use. Surface my instructions on Video, voice, Telemedicine and show current
> implementation and delivery gaps. See api_keys.md for the list of current APIs. Normalize to
> always-zoned ISO-8601 at the backend. DOCUMENT."*
>
> This surfaces the founder's own words from the source docs, states what is actually built as of
> this commit, and names the gaps. Nothing here is aspiration — every "Built" claim is anchored to a
> file/endpoint, every "Gap" to a missing or stubbed one.

Legend: ✅ **Done** · 🟡 **Partial** · 🔴 **Missing / stub** · 📱 **mobile-parity gap** (iOS **and** Android must match web).

---

## 0. Executive status

| Capability | Instruction source | State | One-line gap |
|---|---|---|---|
| **AI router abstraction** (no baked-in provider) | `Basis.md`, `basis_fix_prompt.md`, gap #2 | ✅ | Clients call `/ai/*`; backend routes through `alafia_infer`. No provider is baked into web/iOS/Android. |
| **Multi-provider round-robin** (free-first → Ollama) | this-session canon (extends the router) | 🟡 | Code shipped (20 providers) but **only 4 keys wired**; the big *free* wins (Groq, Gemini, Cerebras, SambaNova) are unkeyed. |
| **Voice** (speech → clinical NLP) | `Basis.md` "Start speaking, Voice AI kicks in" | ✅ | `/ai/voice` live (Whisper→OpenAI, 8 languages); web + mobile capture wired. |
| **Video-AI** (camera → "Video/Image AI kicks in") | `Basis.md`, `basis_fix_prompt.md` Pillar B | 🔴 | **Image** works (`/ai/vision`, moondream). **Video** capability is a `0.1.0-scaffold` — no `/ai/video`, no analysis. |
| **Telemedicine** (video visits) | `04142026Audit.md`, telehealth models | 🟡 📱 | Backend complete (RTC config + signaling + WS). **Web does real WebRTC; iOS is an explicit stub; Android has none.** |
| **Always-zoned datetimes** | this-session directive | ✅ | Global normalizer shipped in `main.py` (this session). See §4. |

---

## 1. Your instructions — AI architecture & provider use (surfaced)

**Primary source — `Basis.md` (the founding vision):**

> *"Interfaces are inferred from commands which are based on devices being used — voice, images,
> video, text, documents, other tools. Use prompt as entry point … prompt determines what UI is
> surfaced. We reuse current UIs."*

**Primary source — `basis_fix_prompt.md` (2026-06-25, the implementation plan), Prompt A1:**

> *"Do NOT call OpenAI/Ollama directly — go through `app.services.alafia_model_service.alafia_infer`
> (keeps the router abstraction, per gap #2)."*

**This-session canon (the round-robin extension of that abstraction):**

> *"We set up a round-robin. I will provide API keys for Google, OpenAI, Anthropic, Kimi, DeepSeek,
> Mistral and others. We randomly use tokens from these providers and fall back to Ollama. The goal
> is to use up free resources and fall back. The holy grail is the ALAFIA model, so we learn."*
>
> *"Don't bake in any single AI (that was always canon) so AI changes can be made on the backend
> without requiring new versions of the front end (web, iOS, Android)."*

**The through-line:** one abstraction (`alafia_infer` → `ALAFIAModel` router) owns all model choice.
Frontends never name a provider. Provider strategy (which model, in what order) is a backend concern
that can change without shipping a new app.

### Current implementation

- **Router abstraction — ✅ delivered.** All AI features call backend `/ai/*` endpoints; the backend
  dispatches through `app/services/alafia_model_service.py::alafia_infer` → `ML/src/alafia_model`.
  No provider SDK is referenced in web/iOS/Android.
- **Round-robin — 🟡 code shipped, under-keyed.** `ML/src/alafia_model/registry/providers.py` defines
  **20 providers**, free-tier weighted first, cooldown on failure, terminal Ollama fallback + telemetry.
  `deploy.sh` mounts provider keys from Secret Manager (`LLM_PROVIDER_SECRETS`).

  | Tier | Providers (weight) |
  |---|---|
  | **Free** (tried first) | gemini (3), groq (3), cerebras (2), sambanova (2), mistral (2), openrouter (2), github (1.5), nvidia (1.5), dashscope (1), zhipu (1), cloudflare (1) |
  | **Paid** (fallback band) | deepseek (2), anthropic (1), openai (1), moonshot (1), together (1), fireworks (1), deepinfra (1), xai (1), perplexity (0.5) |
  | **Terminal** | self-hosted **Ollama** (private GPU Cloud Run, OIDC-authed) |

### Gaps

1. **Only ~4 of 20 providers are keyed** (see §3). The stated goal — *"use up free resources"* — is
   unrealized because the highest-value **free** providers (Groq, Gemini, Cerebras, SambaNova) have
   **no key wired**. Today traffic effectively lands on the paid keys that exist, then Ollama.
2. **`alafia-model` ("the holy grail") is not yet a learning loop.** Telemetry records provider
   outcomes (`telemetry.py`), but there is no training/eval pipeline consuming it. HEBCS serving
   (Pillar F) remains deferred.

---

## 2. Your instructions — Voice, Video, Telemedicine (surfaced)

**Primary source — `Basis.md`:**

> *"voice, text or image will determine the interface to surface. Prompt will respond to text, voice
> and click camera icon next to prompt window will let user upload or take new pictures … Start
> speaking, Voice AI kicks in … Click on Camera, Video/Image AI kicks in."*

**Primary source — `04142026Audit.md`** lists **Telehealth + WebSocket** as a first-class subsystem
("sessions, participants, notes, recordings, WebSocket" — signaling + chat).

### 2a. Voice — ✅ Delivered

- **Backend:** `POST /ai/voice` (`app/api/ai.py:163`). Pipeline `capabilities/voice.py`: audio →
  transcript → LLM clinical extraction. `whisper_adapter.py` = self-hosted Whisper primary, OpenAI
  fallback. 8 languages. (Went from a 404 stub → live per `06112026_GapAnalysis.md`.)
- **Clients:** voice capture in the PromptHub on **web (Web Speech API), iOS, and Android**
  (`basis_fix_prompt.md` Pillar H — both mobile builds compiled). Transcript is re-routed via `/ai/route`.
- **Gap:** none blocking. Watch item: production voice quality depends on the self-hosted Whisper
  service being healthy; confirm it's deployed (not just OpenAI-fallback in prod).

### 2b. Video — 🔴 Two different "videos", both incomplete

There are two things called "video." Keep them separate:

1. **Video-AI** (analyze a captured video clip, the `Basis.md` "Video AI kicks in"):
   `ML/src/alafia_model/capabilities/video.py` is still **`0.1.0-scaffold`** (`is_implemented=False`,
   Phase 8). There is **no `/ai/video` endpoint**. Today "click camera" resolves to **image only**
   (`/ai/vision`, moondream) — the still-image half of the instruction works; the moving-video half
   does not exist.
2. **Telemedicine video** (a live visit) — covered in 2c.

**Gap:** the "Video AI kicks in" instruction is half-met. Recommend either (a) implement `video.py`
(sample frames → vision capability + transcribe audio → voice capability), or (b) explicitly defer it
like HEBCS/Pillar F so it stops reading as a silent hole.

### 2c. Telemedicine — 🟡 backend done, client 📱 parity gap

- **Backend — ✅ complete** (`app/api/telehealth.py`): sessions CRUD, participants, notes,
  recordings, transcripts, **`/rtc-config`** (ICE/TURN), **`/signal`** (WebRTC offer/answer/ICE
  exchange, POST+GET), plus `ws_telehealth` WebSocket for realtime signaling + chat.
- **Web — ✅ real WebRTC** (`WEB/frontend/src/pages/Telehealth.jsx`): `getUserMedia` →
  `new RTCPeerConnection(config)` → `createOffer` → signal exchange. A visit actually connects.
- **iOS — 🔴 stub** (`IOS/ALAFIA/Views/Telehealth/TelehealthView.swift:1035`): fetches `/rtc-config`
  then the code comment reads *"In a full implementation, WebRTC peer connection would be established
  here using the native WebRTC framework."* No peer connection, no media. The screen exists; the call
  does not.
- **Android — 🔴 missing:** no WebRTC/`PeerConnection` implementation found.

**Gap (📱):** telemedicine is web-only. Per standing canon *"mobile means Android and iOS, always,"*
this is a two-platform parity hole. Closing it needs the native WebRTC framework on each
(`WebRTC`/`GoogleWebRTC` pod on iOS; `io.getstream:stream-webrtc-android` or Google's lib on Android),
wired to the existing `/rtc-config` + `/signal` + WS the backend already serves.

---

## 3. Current API inventory (from `api_keys.md`, values redacted)

| Provider | Registry env var | Key present today? | Notes |
|---|---|---|---|
| OpenAI | `OPENAI_API_KEY` | ✅ present | paid tier |
| Anthropic | `ANTHROPIC_API_KEY` | ✅ present | paid tier |
| DeepSeek | `DEEPSEEK_API_KEY` | ✅ present | paid tier |
| Kimi / Moonshot | `MOONSHOT_API_KEY` | ✅ present | paid tier |
| Google / Gemini | `GEMINI_API_KEY` | ⚠️ ADC script only, no key | **free tier, highest weight — unkeyed** |
| Mistral | `MISTRAL_API_KEY` | 🔴 empty (`##`) | free tier |
| Groq · Cerebras · SambaNova · OpenRouter · GitHub · NVIDIA · DashScope · Zhipu · Cloudflare | (respective) | 🔴 not in file | **free tier — the "use up free resources" wins, all unkeyed** |

**Takeaway:** the round-robin can only spend what it's given keys for. Right now that's 4 paid
providers + Ollama. To honor *"use up free resources first,"* wire the free keys into Secret Manager
(`gemini-api-key`, `groq-api-key`, `cerebras-api-key`, `sambanova-api-key`, …) and let `deploy.sh`
mount them via `LLM_PROVIDER_SECRETS`.

### ⚠️ SECURITY — `api_keys.md`

- The file holds **real, live secrets** (OpenAI `sk-proj-…`, Anthropic `sk-ant-…`, DeepSeek, Kimi).
- It was **not gitignored** — one `git add .` from being committed to a GitHub-hosted repo. **Fixed
  this session:** added `api_keys.md` to `.gitignore`. It is not currently tracked, so no history scrub
  is needed *yet*.
- **Recommended:** (1) treat every key in that file as **exposed → rotate** them; (2) move them to
  **Secret Manager** as the single source of truth; (3) keep only *references* (secret names) in the
  repo, never values.

---

## 4. Shipped this session — always-zoned ISO-8601

**Root cause:** naive datetimes. Columns like `ChronicCondition.created_at` are
`Column(DateTime, default=datetime.utcnow)` — `utcnow()` returns a **naive** datetime, and Pydantic v2
serializes it **without a zone** (`2026-07-31T17:11:03.523040`). iOS's decoder rejected it
("Chronic Conditions … isn't in the correct format"). This was one instance of a recurring class.

**Fix:** a global response normalizer in `WEB/backend/app/main.py`
(`normalize_datetimes_middleware`). For every `application/json` response, any bare
`YYYY-MM-DDTHH:MM:SS[.ffffff]` string (no zone) is treated as UTC and gets a trailing `Z`. Strings
already zoned (`…Z` / `…±hh:mm`) and date-only values are untouched — verified against 6 edge cases
including a datetime embedded in prose (left alone). Multi-value headers (e.g. `Set-Cookie` on
`/auth/login`) are preserved via `raw_headers`. **This repairs existing naive rows on read**, not just
new writes — no data migration required.

> Complement (not done here): also fix at the source going forward — `datetime.utcnow()` →
> `datetime.now(timezone.utc)` and tz-aware columns — so data is born zoned. The middleware is the
> safety net that covers all endpoints and legacy data today.

---

## 5. Prioritized next actions

1. **🔴 Rotate the keys in `api_keys.md`** and move them to Secret Manager. (Security first.)
2. **🟡 Wire the free-tier keys** (Groq, Gemini, Cerebras, SambaNova at minimum) so the round-robin
   actually "uses up free resources" before touching paid/Ollama.
3. **📱 Close telemedicine mobile parity** — native WebRTC on iOS + Android against the existing
   `/rtc-config` + `/signal` + WS. (Or explicitly descope mobile video visits.)
4. **🔴 Decide Video-AI:** implement `capabilities/video.py` (frames→vision + audio→voice) or formally
   defer it alongside HEBCS.
5. **✅→verify:** confirm the self-hosted Whisper voice service is live in prod (not silently on OpenAI
   fallback), and deploy the datetime normalizer (§4) so parity holds in prod.
6. **Guard rail:** `tools/contract_drift_check.py` already catches naive datetimes + missing required
   fields against live endpoints — run it in CI so this class of bug can't silently return.
