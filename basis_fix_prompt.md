# Basis Fix Prompts — Aligning ALAFIA to `Basis.md`

> **Purpose.** `Basis.md` describes what ALAFIA *fundamentally is*. This file translates that
> vision into a sequence of self-contained, reviewable implementation prompts. Each prompt can be
> handed to a coding agent (or done by hand) and is scoped to one coherent change with explicit
> acceptance criteria. Prompts are ordered by dependency — do them top to bottom.
>
> **Generated:** 2026-06-25 · against commit `be9f4a5` (branch `main`).
>
> **Implementation status (updated 2026-06-26):**
> - ✅ **Pillar A** (A1 `/ai/route`, A2 `classify_intent`, A3 `PromptHub`, A4 prefill) — done & tested
> - ✅ **Pillar B** (B1 Vision via Ollama/llava→moondream + `/ai/vision`, B2 camera/voice in hub) — done & tested
> - ✅ **Pillar C** — C1 Symptoms ✅, C2 Sleep ✅ (full CRUD+UI), C3 genetics + environmental/social ✅ (models+migration+CRUD, fed into D/E signals & AI context) — verified live
> - ✅ **Pillar G** (ask_question → GP chat auto-ask; + "?" question guard for weak local model) — done & verified live
> - ✅ **Pillar D** (relationship/correlation engine `/insights/relationships` + Insights view) — done & verified live (detected seeded sodium→BP lag-1 edge, r=1.0)
> - ✅ **Pillar E** (forecast engine `/insights/forecast` + chart) — done & verified live (weight trend projection)
> - ✅ **Pillar H** (iOS + Android PromptHub parity — text **+ voice + camera**) — **iOS `xcodebuild` BUILD SUCCEEDED**, **Android `compileDebugKotlin` BUILD SUCCESSFUL**. True web↔mobile parity.
>
> **All Basis pillars A–H are now implemented except F (HEBCS serving), which the user deferred.**
> Remaining polish: a capture UI for C3 ground truths; mobile cert-pin hashes for release builds.
>
> Dev note: LLM engine is local **Ollama** (`llama3.2:3b` text, `moondream` vision). nginx upload
> limit raised to 25M; voice uses the browser Web Speech API in dev.

---

## 0. What `Basis.md` actually asks for

`Basis.md` defines ALAFIA as a **data-collection hub** with one organizing idea on top:

| # | Basis requirement | Current state | Verdict |
|---|---|---|---|
| 1 | **Prompt is the entry point.** Login → Prompt Page. Modality (voice/text/image/video) determines which UI is surfaced. Camera icon next to the prompt for capture. *Reuse existing UIs.* | App opens to `Dashboard` (web) / `MainTabView` (mobile). AI is siloed in `AIChat` (text-only, persona-first), `Capture` (manual form), `ImageAI`. No intent→UI routing exists. | **MISSING — the heart of Basis** |
| 2 | **Collect** what a person consumes, discharges, does, thinks, their symptoms, sleep. | Nutrition, Medications, Elimination, Fitness, Journal, Mood, MentalHealth pages exist. Sleep is referenced but has no dedicated capture. Symptoms have an NLM extractor but no first-class capture surface. | **PARTIAL** |
| 3 | **Overlay on ground truths:** biology (age/sex/height/body/weight/labs/genetics), hospital notes, therapies (dialysis/chemo), environmental & social factors. | Profile, Labs, Hemodialysis/PD/Chemotherapy pages exist. Genetics, environmental & social factors absent. | **PARTIAL** |
| 4 | **Identify patterns, relationship graphs, cause & effects.** | `HealthTrends`, `ChartDashboard` show series. No correlation/relationship-graph/cause-effect engine. | **MISSING** |
| 5 | **Predict future outcomes (states).** | None beyond HEBCS scoring scaffolding. | **MISSING** |
| 6 | **Calculate scores vs expected outcomes.** | HEBCS exists in ML/ but the feature→inference serving seam to the backend is not wired (see gap analysis #4/#9). | **PARTIAL** |
| 7 | **Interact via Agents.** | Persona/specialist agents exist (`/ai/personas`, `AIChat`). | **DONE (text)** |

**Conclusion.** The single most important missing piece is **requirement #1** — the universal,
modality-aware prompt entry point that routes a user's input to the right capability and surfaces
the right *existing* UI. Everything else in Basis is an enrichment of the data the hub collects and
the intelligence it returns. The prompts below lead with #1 and build outward.

---

## Pillar A — The Universal Prompt Entry Point (the heart of Basis)

### Prompt A1 — Backend: intent-routing endpoint

```
Add a new endpoint POST /api/v1/ai/route to WEB/backend/app/api/ai.py.

Goal: classify a user's prompt into an INTENT + TARGET UI + extracted STRUCTURED DATA, so the
client can surface the correct existing screen pre-filled. This is the brain behind ALAFIA's
"prompt determines what UI is surfaced" model (Basis.md).

Request body (JSON):
  {
    "text": "optional typed/transcribed prompt",
    "modality": "text" | "voice" | "image" | "video",
    "has_attachment": bool
  }

Behavior:
  - Route the text through the ALAFIAModel NLM capability with a new task "classify_intent"
    (see Prompt A2). Do NOT call OpenAI/Ollama directly — go through
    app.services.alafia_model_service.alafia_infer (keeps the router abstraction, per gap #2).
  - Map the classified intent to one of the existing app routes. Use a single source-of-truth
    INTENT_ROUTE_MAP dict, e.g.:
        "log_meal"        -> {"route": "/nutrition",   "action": "create"}
        "log_medication"  -> {"route": "/medications", "action": "log_dose"}
        "log_elimination" -> {"route": "/elimination", "action": "create"}
        "log_symptom"     -> {"route": "/mental-health" or symptom surface, "action": "create"}
        "log_activity"    -> {"route": "/fitness",      "action": "create"}
        "journal"         -> {"route": "/journal",      "action": "create"}
        "log_sleep"       -> {"route": "/lifestyle",    "action": "create"}  (until Prompt C2)
        "view_labs"       -> {"route": "/labs",         "action": "view"}
        "view_trends"     -> {"route": "/health-trends","action": "view"}
        "ask_question"    -> {"route": "/ai",           "action": "chat"}   (fallback)
  - For image/voice attachments, set intent from the attachment type when text is empty
    (image -> likely food/lab/pill photo -> "vision_capture"; voice handled client-side first
    via /ai/voice then re-routed with the transcript).

Response:
  {
    "intent": "log_meal",
    "confidence": 0.0-1.0,
    "route": "/nutrition",
    "action": "create",
    "prefill": { ...structured fields the target screen can consume... },
    "assistant_message": "short confirmation/clarifying line to show the user"
  }

Acceptance:
  - Endpoint is auth-protected (Depends(get_current_user)) like the others in ai.py.
  - Unknown / ambiguous input returns intent "ask_question" routed to /ai with confidence < 0.5.
  - Add a unit test that asserts "I ate jollof rice and beef suya" -> intent "log_meal",
    route "/nutrition", and prefill contains the meal text.
```

### Prompt A2 — ML: `classify_intent` NLM task

```
Add a "classify_intent" task to ML/src/alafia_model/capabilities/nlm.py (NLMCapability.infer).

It already supports parse_meal / extract_icd10 / extract_symptoms. Add classify_intent that
prompts the LLM (via the existing adapter chain — Ollama then OpenAI fallback, json_mode=True)
to return STRICT JSON:
  { "intent": "<one of the fixed enum>", "confidence": 0.0-1.0, "entities": { ... } }

The intent enum must match INTENT_ROUTE_MAP in Prompt A1. Keep the system prompt tight and
forbid free-form intents. Return a CapabilityResult with success/data/confidence/source.

Acceptance:
  - "took my 10mg lisinopril" -> intent "log_medication", entities.name "lisinopril",
    entities.dose "10mg".
  - Returns confidence and a deterministic fallback intent "ask_question" if the model output
    fails to parse.
  - Add/extend the capability test in ML/tests.
```

### Prompt A3 — Web: the PromptHub landing surface

```
Create WEB/frontend/src/pages/PromptHub.jsx and make it the authenticated index route.

This replaces Dashboard as the first screen after login (Basis: "Login to App. See Prompt Page").
Keep Dashboard reachable at /dashboard.

UI (reuse existing styles/components — chat-input-area, card, BackButton):
  - A large centered prompt input with three affordances, matching Basis exactly:
      * type -> text intent (LLM/NLM)
      * mic button -> record audio, POST to /ai/voice, take transcript, then call /ai/route
      * camera button (icon next to prompt) -> file/camera capture -> vision flow (Prompt B1)
  - On submit (any modality): call POST /ai/route, show assistant_message, then
    navigate(result.route, { state: { prefill: result.prefill, fromPrompt: true } }).
  - Show a small "recent intents" / quick-action row (Log meal, Log meds, Journal, Ask) that
    pre-seed the prompt — optional polish.

Wire-up in App.jsx:
  - <Route index element={<PromptHub />} />
  - <Route path="dashboard" element={<Dashboard />} />
  - Lazy-import PromptHub.

Acceptance:
  - Typing "log that I drank 2 cups of water" navigates to the elimination/nutrition surface
    with prefill populated.
  - Mic and camera buttons are present and functional (camera can defer to Prompt B1 if vision
    isn't ready, but must at least open the capture flow).
  - Dashboard still works at /dashboard and its nav link is updated.
```

### Prompt A4 — Web: make target screens consume `prefill`

```
Update the screens referenced by INTENT_ROUTE_MAP to read location.state.prefill (react-router)
and open their create/log form pre-populated when fromPrompt is true. Start with the highest-value
ones: Nutrition.jsx, Medications.jsx, Elimination.jsx, Journal.jsx, Fitness.jsx.

Pattern:
  const { state } = useLocation();
  useEffect(() => { if (state?.fromPrompt && state.prefill) { openFormWith(state.prefill); } }, []);

Acceptance:
  - Arriving at /nutrition from the prompt with prefill { meal_text, items } opens the add-meal
    form with those values filled, not a blank page.
  - Arriving normally (clicking the nav link) shows the screen's default state — no regression.
```

---

## Pillar B — Multimodal capture (voice exists; finish vision + camera)

### Prompt B1 — ML + Backend: implement Vision food/label capture

```
Implement VisionCapability.food_photo_nutrition in ML/src/alafia_model/capabilities/vision.py.
It is currently a scaffold (is_implemented = False).

Near-term, pragmatic approach (do NOT block on training a custom MobileNetV3):
  - Route image_bytes to a vision-capable LLM through the OpenAI adapter (gpt-4o family) when
    OPENAI_API_KEY is set; structured-extract food items + estimated portions as JSON.
  - Fall back to a clear "vision unavailable" CapabilityResult when no vision backend is set,
    so the client degrades gracefully to the manual Capture form.
  - Set is_implemented = True only when a backend is actually reachable (mirror the
    is_available() pattern used by other capabilities).

Backend: add POST /api/v1/ai/vision in ai.py (multipart image upload, like /ai/voice) that calls
alafia_infer("vision", {image_bytes, task}) and returns the structured result. Keep the lab-report
OCR task (lab_report_ocr) as a follow-up TODO but wire the same endpoint shape.

Acceptance:
  - Uploading a food photo returns { items: [...], estimated_nutrition: {...}, source }.
  - With no vision backend configured, endpoint returns 503 with a clear message and the web
    Capture flow still lets the user save the photo manually.
```

### Prompt B2 — Web: camera + voice in the PromptHub talk to A1/B1

```
Finish the camera and mic affordances in PromptHub.jsx (Prompt A3):
  - Camera -> capture/upload image -> POST /ai/vision -> if food items detected, route to
    /nutrition with prefill; else save via /media (existing Capture endpoint) and confirm.
  - Mic -> record (MediaRecorder) -> POST /ai/voice -> take transcript -> POST /ai/route with
    that transcript and modality "voice" -> navigate per result.

Acceptance:
  - Voice note "I have a headache and took paracetamol" routes to the symptom/medication surface
    pre-filled.
  - Food photo routes to /nutrition pre-filled with detected items.
```

---

## Pillar C — Complete the collection domains (Basis: consume / discharge / do / think / symptoms / sleep)

### Prompt C1 — First-class Symptom capture

```
Symptoms are a Basis collection domain but have no dedicated capture surface (only an NLM
extractor). Add a Symptoms log:
  - Backend: a symptoms table + CRUD api (model + schema + WEB/backend/app/api/symptoms.py),
    mirroring the shape of an existing simple log (e.g. mood.py / elimination.py).
  - Web: a Symptoms page (reuse Mood/Elimination page structure) and add to INTENT_ROUTE_MAP
    ("log_symptom" -> "/symptoms").
  - Mobile parity is handled in Pillar H.

Acceptance: prompt "my left knee hurts when I climb stairs" routes to /symptoms pre-filled.
```

### Prompt C2 — First-class Sleep capture

```
Sleep is named in Basis but only referenced incidentally. Add a Sleep log (duration, quality,
wake count, notes) following the same CRUD pattern as C1, surface it (web page + route), and map
"log_sleep" -> "/sleep" in INTENT_ROUTE_MAP. Pull from HealthKit/Health Connect on mobile where
available (Pillar H).

Acceptance: "I slept 6 hours but woke up twice" routes to /sleep pre-filled.
```

### Prompt C3 — Ground-truth gaps: genetics + environmental/social factors (schema only)

```
Add (schema + minimal CRUD, no fancy UI yet) for the two missing ground-truth categories Basis
lists: genetic data and environmental/social factors (e.g. location/air-quality, household,
occupation, stressors). Store them on the profile/ground-truth side so the patterns engine
(Pillar D) and HEBCS (Pillar F) can consume them later. Document them as inputs in the data model.

Acceptance: fields persist and are returned by the profile/context fetch used in
ai.py::_fetch_patient_context.
```

---

## Pillar D — Patterns, relationship graphs, cause & effect

### Prompt D1 — Correlation / relationship engine (backend service)

```
Create WEB/backend/app/services/insights_engine.py that computes relationships across the
collected domains overlaid on ground truths (Basis req #3/#4):
  - Pull time-series for the user's logged domains (nutrition nutrients, meds, vitals, labs,
    mood, sleep, symptoms, elimination).
  - Compute lagged correlations / simple cause-effect candidates (e.g. high-sodium day ->
    next-day weight/BP; missed dialysis -> potassium). Start with Pearson/Spearman over aligned
    daily aggregates + a configurable lag window. Be explicit that these are associations, not
    clinical causation.
  - Expose GET /api/v1/insights/relationships returning ranked edges
    { source, target, strength, lag_days, direction, sample_size, caveat }.

Acceptance: with seeded data, returns at least the obvious sodium->BP style edge and never
asserts causation in the copy.
```

### Prompt D2 — Web: relationship graph view

```
Add a "Relationships" view (or a section on HealthTrends) that renders the edges from D1 as a
simple graph / ranked list. Reuse existing chart libs. Link "view_trends"/"view_relationships"
intents to it.

Acceptance: graph renders the ranked edges with the association caveat visible.
```

---

## Pillar E — Prediction of future states

### Prompt E1 — Forecasting seam

```
Add WEB/backend/app/services/forecast_engine.py + GET /api/v1/insights/forecast that projects
near-term states (e.g. next lab value bands, weight/fluid trajectory, HEBCS trajectory) from the
collected series. Start simple (rolling trend / Holt-Winters or last-value+drift) with clearly
labelled confidence intervals; leave a documented seam to swap in the ML models later (gap #5
"ML serving undefined").

Acceptance: returns forecast points with intervals; surfaced as a card on PromptHub/HealthTrends.
```

---

## Pillar F — Scores vs expected outcomes (HEBCS serving seam)

### Prompt F1 — Wire HEBCS feature→inference into the backend

```
Close gap #4/#9: HEBCS models exist in ML/models/*.joblib but the backend cannot trigger scoring
because it needs the engineered features the ML pipeline produces.

  - Define the serving contract: either (a) a thin ML REST endpoint that accepts raw user data and
    runs feature extraction + inference, or (b) a backend-side feature extractor that mirrors the
    ML pipeline. Pick (a) if the ML feature code can be containerized; document the choice.
  - Add GET /api/v1/wellness/hebcs that returns the score + subscores + "vs expected" delta for
    the current user, calling that serving path.
  - Surface the score on PromptHub and Wellness.

Acceptance: a user with sufficient data gets a real HEBCS score (not a placeholder); insufficient
data returns a clear "need more data" state.
```

---

## Pillar G — Agents (mostly done; integrate with the hub)

### Prompt G1 — Route "ask_question" intents into the existing persona chat

```
When /ai/route returns intent "ask_question", PromptHub should hand off to the existing AIChat
flow with the typed text as the first message (optionally defaulting to the general_practitioner
persona so the user isn't forced through the picker for a quick question). Keep the full persona
picker available from the AI nav entry.

Acceptance: typing a health question on PromptHub lands in a chat answering it, without a separate
persona-selection step (picker still reachable from the AI menu).
```

---

## Pillar H — Mobile parity (iOS + Android)

### Prompt H1 — iOS PromptHub as the launch surface

```
Add a PromptView (SwiftUI) as the first tab / launch surface in
IOS/ALAFIA/Views/Main/MainTabView.swift, mirroring web PromptHub: text field + mic + camera,
calling /ai/route, /ai/voice, /ai/vision, then navigating to the matching existing screen with
prefill. Reuse existing views. Keep the tab bar for direct navigation.

Acceptance: voice and photo capture route to the correct pre-filled screen on device/simulator.
```

### Prompt H2 — Android PromptHub as the launch surface

```
Add a PromptScreen (Compose) as the start destination in
Android/app/src/main/java/com/alafia/android/views/main/MainTabView.kt, mirroring web PromptHub
(text + mic + camera -> /ai/route, /ai/voice, /ai/vision -> navigate with prefill). Follow the
existing Compose/nav pattern. Note: gap analysis flags Android isn't using MVVM/StateFlow yet —
prefer a small ViewModel for the prompt state here to set the pattern.

Acceptance: parity with H1.
```

---

## Suggested execution order (dependency-aware)

1. **A2 → A1 → A3 → A4** (the hub; nothing else matters without it)
2. **B1 → B2** (vision + camera/voice wired into the hub)
3. **C1, C2, C3** (complete the collection/ground-truth domains the hub routes to)
4. **F1** (real scores — high user value, infra already exists)
5. **D1 → D2 → E1** (intelligence layer)
6. **G1** (agent integration polish)
7. **H1, H2** (mobile parity, last so the contract is stable)

## Cross-cutting guardrails (apply to every prompt)

- **Never bypass the ALAFIAModel router** — all AI calls go through `alafia_infer` /
  `app.services.alafia_model_service` (gap #2).
- **No fabricated clinical data** — extractors return null/empty rather than inventing values.
- **Associations ≠ causation** — pattern/forecast copy must say so.
- **Reuse existing UIs** — Basis is explicit: *"Prompt determines what UI is surfaced. We reuse
  current UIs."* Do not build parallel screens; pre-fill the ones that exist.
- **Auth + CSRF** parity with sibling endpoints.
- Add/extend tests for each backend task and capability.
</content>
</invoke>
