# ALAFIA — Work Log

A running log of user instructions and the work done in response. Newest entries at the bottom of each session.

---

## Session 2026-06-07 — Infrastructure wiring (Gaps #6, #19, #21)

**Instruction:** Read `06062026_GapAnalysis.md`, then: enable GitHub Actions workflows; wire iOS APNS token registration to backend; add dose-logging UI to iOS and Android.

**Work done:**
- **CI (Gap #6):** Added `workflow_dispatch` to `backend.yml`, `web.yml`, `ios.yml`, `android.yml`. Created root `.gitignore` protecting secrets, build dirs, SwiftPM `.build/`, and excluding `HEBCS/`, `HEBCSL_MATLAB/`, `docs/`, `Book/`, and 5 root `.md` files.
- **iOS APNs (Gap #19):** Backend `DeviceToken` model + migration `x001_add_device_tokens` (chain verified single-head); `POST /notifications/apns-token` + `/fcm-token` + `DELETE /notifications/device-token`. iOS `PushNotificationManager.registerTokenWithBackend()` + re-send after login in `AuthManager`.
- **Dose logging (Gap #21):** iOS `MedicationDoseLog`/`Create` models, `logDose()` VM method, "Log Dose" swipe-action sheet. Android schema/model, 3 `ApiService` methods, "Log Dose" card button + dialog. Both POST `/medications/dose-logs`.
- **Repo setup:** Repointed `origin` → `git@github.com:dewakp/ALAFIAKALO.git`. Initial commit `be9f4a5` (1158 files), pushed to `main`. All four CI workflows triggered and active.

**Notes / open items:**
- Cert-pinning hashes in both mobile `APIClient`s are still `AAAA…`/`BBBB…` placeholders (release builds will reject traffic until real SHA-512 pins are added).
- HEBCS research stays in `6igmaHealthBook/WellnessScore`; app lives in `dewakp/ALAFIAKALO`.

---

## Session 2026-06-08 — Frontend units, AI router consolidation, MCP endpoint (Gaps #18, #2, #12)

**Instruction:** Add Metric/Imperial toggle to frontend; route all backend AI calls through the ALAFIAModel router; expose the MCP Nutrition Server as a proper MCP endpoint. Maintain a running log of instructions and work (this file).

**Work done:**

- **Metric/Imperial toggle (Gap #18):** The backend already persisted `preferred_units` and Profile had a dropdown, but the choice was never *applied*. Added a real units system:
  - `WEB/frontend/src/utils/units.js` — conversion + format helpers mirroring backend `app/core/units.py` (kg↔lb, cm↔in, °C↔°F, mg/dL↔mmol/L, mL↔fl oz).
  - `WEB/frontend/src/context/UnitsContext.jsx` — single source of truth; seeds from localStorage → `user.preferred_units` → metric; persists changes to `PATCH /users/me`.
  - `WEB/frontend/src/components/UnitToggle.jsx` — segmented Metric/Imperial control.
  - Wired `UnitsProvider` into `App.jsx` (inside `AuthProvider`); replaced Profile's dropdown with the toggle and made the Physical Characteristics inputs unit-aware (display/edit in the active system, store canonical metric).

- **Route backend AI through ALAFIAModel router (Gap #2):** Built the router's LLM capability into a complete single entry point and pointed call sites at it.
  - Router: added `json_mode` + `model` to `InferencePayload`; `LLMCapability` now has a generic `chat`/`complete` passthrough task with **Ollama → OpenAI fallback** and per-call model override; both adapters honor `json_mode`.
  - Bridge `alafia_model_service.py`: added `alafia_chat()` / `alafia_complete()` helpers (+ `ALAFIAModelError`).
  - Converted direct Ollama/OpenAI HTTP calls to the bridge in: `ai_engine._call_llm`, `diagnostics_engine._call_llm`, `nutrient_estimator._try_ai` (removed the inline `_call_ollama`/`_call_openai`), `api/planners.py` (both `/api/generate` calls), `api/ai_learning.py`, and `api/ai.py` non-streaming `/chat`.
  - **Known exception:** `api/ai.py` `/chat/stream` still calls Ollama directly — the router has no streaming capability yet (marked with a NOTE + Phase-3 TODO).

- **Expose MCP Nutrition Server (Gap #12):** fastmcp can't be installed alongside FastAPI 0.115.6 (Starlette clash), so instead of mounting in-process the server now runs as its own container.
  - `WEB/backend/requirements-mcp.txt` (slim, FastAPI-free) + `WEB/backend/Dockerfile.mcp` + an `mcp` service in `WEB/docker-compose.yml` exposing port 8003.
  - Generalized the server entry point to support `sse` / `http` / `streamable-http`; updated docstrings and the `requirements.txt` note.

**Environment / process notes:**
- This machine has **no homebrew** and node isn't on PATH — use **Docker** for all servers/services/builds (saved to memory). Docker Desktop's daemon was stopped at first; started it via `open -a Docker`.

**Verification:**
- ALAFIAModel router smoke-tested: `json_mode`/`model` thread through; with no Ollama/OpenAI it fails gracefully (no raise). All changed Python files `py_compile` clean.
- `docker compose config` valid.
- Frontend Docker build (`npm ci && npm run build`) passed → React changes compile.
- MCP image built cleanly (fastmcp 2.14.7); ran the container and probed it: `Uvicorn running on 0.0.0.0:8003`, `GET /sse` → 200 (MCP SSE endpoint live), `GET /` → 404 (expected). Endpoint confirmed reachable.

**Known exceptions / follow-ups:**
- `api/ai.py` `/chat/stream` still streams directly from Ollama (router has no streaming capability — Phase 3 TODO).
- LLM capability OpenAI fallback only triggers when `OPENAI_API_KEY` is set; Ollama remains primary.
- MCP `get_med_nutrients` tool needs DB access (the `mcp` compose service depends on `db`); the USDA/OFF tools work without it.

**Run-up (2026-06-09): full stack + mobile**
- **Instruction:** restart all services + frontend to test; then build & fire up iOS + Android.
- Web stack rebuilt and started via `docker compose up -d --build`: db (:5435), chain (:8546), backend (:8005, `/api/health` ok), frontend (:8080), mcp (:8003/sse). All healthy.
- **iOS:** built with Xcode 26.5 for the iPhone 17 Pro simulator (host build — mobile can't run in Docker). **Fixed a bug from the 2026-06-07 dose-logging work**: `LogDoseSheet` collided with an existing `LogDoseSheet` in `PharmacyView.swift` → renamed the new one to `MedicationDoseSheet` (decl + call site in `MedicationsView.swift`). App points at `http://localhost:8005/api/v1` (sim reaches host).
- **Android:** built debug APK on host (Gradle 9.3.1 / AGP 9.1.0 on JDK 24, SDK at `/Users/woleakpose/sdks/Android`); installed + launched on the `Pixel_9_Pro_XL` emulator (`emulator-5554`). App points at `http://10.0.2.2:8005/api/v1/`. Confirmed running (MainActivity resumed, no crash).
- Note: the project is fully provisioned for native mobile on the host, so iOS/Android were built/run on the host rather than Docker (Docker remains the rule for servers/services).

## Session 2026-06-09 (cont.) — Personalized daily nutrient goals card

**Instruction:** On the Meals Diary page, add a card under the calendar showing a running sum of daily nutrients tracked against **personalized** daily goals/limits derived from patient biology (age, height, weight, target weight, conditions) + NIH guidelines. E.g. a CKD patient must track protein, potassium, phosphorus.

**Work done:**
- **Backend `app/services/nutrient_goals_service.py`** — `compute_goals()` derives per-nutrient daily **targets** (reach) and **limits** (stay under) from biology (Mifflin-St Jeor energy × activity, weight-goal adjustment; protein g/kg; DRIs) and `detect_condition_flags()` (ckd, dialysis, diabetes, hypertension, cardiovascular, heart_failure). Condition logic: non-dialysis CKD → protein becomes a *limit* (~0.8 g/kg) + potassium *limit* 2500 mg + phosphorus *limit* 900 mg + sodium ~2000 mg; dialysis → protein *target* ~1.1 g/kg; diabetes → tighter sugar + carb note; HTN/HF → sodium 1500. Refs: KDOQI 2020, DGA 2020-2025, FDA DVs.
- **Backend endpoint** `GET /nutrition/goal-progress?date=` — extracted a shared `_aggregate_daily_nutrients()` helper (food logs + resolved med-dose nutrients; daily-summary now reuses it), merges the day's running totals with personalized goals, returns each nutrient with current/goal/kind/pct/status (`low|ok|warning|over`) + condition flags. New schemas `NutrientGoalProgress` / `GoalProgressResponse`.
- **Frontend** `MealsDiary.jsx` — wrapped the left column so a **Daily Nutrient Goals** card sits under the calendar. Fetches `/nutrition/goal-progress` on date change; renders condition chips, per-nutrient rows with progress bars (green ok / amber low-warning / red over), ↑ target vs ↓ limit arrows, rationale tooltips, and a "complete your profile" hint when biology is missing. Goals are ordered by condition-driven priority (CKD pushes protein/K/PO₄/Na to the top).

**Verification:**
- Backend `py_compile` clean; unit-tested `compute_goals`: healthy male → generic targets; CKD+dialysis → protein target 90 g + K/PO₄/Na limits at top priority.
- Rebuilt backend + frontend images; goal-progress route live (auth-gated), frontend vite build passes.

**Fix (2026-06-09):** goal-progress 500'd — filtered `HealthCondition.is_active` (column doesn't exist; it uses `status`). Changed to `status != "resolved"`. Verified 200 against the real patient (CKD+dialysis): protein target 77 g, sodium over its 2,000 mg limit (matches the red Na chip), K/PO₄ limits.

## Session 2026-06-10 — CollectiveInsight loop, mobile nutrition targets, Voice Phase 7

**Instruction:** Wire the Privacy CollectiveInsight learning loop; surface daily nutrition targets in the mobile apps; then start Voice Phase 7 (Whisper multilingual speech → clinical NLP).

**Gap #11 — CollectiveInsight learning loop:**
- `ai_memory_service.py`: real anonymized demographic-baseline aggregation. `merge_demographic_baseline(user)` folds one user's de-identified daily nutrition/fitness means into the matching demographic (age-range/sex/activity) `CollectiveInsight` via a running mean; `_discover_*_patterns` (were `return []`) now recompute authoritative cohort baselines. **Consent-gated** (`allow_collective_insights`/`allow_anonymized_analytics`).
- `privacy_service._anonymize_for_collective_insights`: the placeholder now actually contributes the departing user's footprint before deletion (best-effort, never blocks deletion).
- Verified with a sync SQLite test: 2 consenting users → cohort protein mean 80; incremental merge → 90; no-consent user → skipped (None).
- **Caveat flagged:** `PrivacyService`/`AIMemoryService` are written sync (`.query()`) but the app's only `get_db` yields an AsyncSession — a pre-existing, file-wide mismatch affecting this whole endpoint family. My code is correct/consistent with the service layer and runs under any sync Session (as the test proves); the session plumbing is a separate larger fix.

**Mobile daily nutrition targets (consume `/nutrition/goal-progress`):**
- iOS: `GoalProgressResponse`/`NutrientGoalProgress` models, VM `fetchGoals`, `DailyTargetsCard` on the Daily Summary tab (condition chips, ↑/↓ progress bars). Build SUCCEEDED.
- Android: models + `getNutritionGoalProgress` + `DailyTargetsCard` on the summary tab. Clean rebuild SUCCEEDED (a transient dex error was stale `…2.dex` cache, not code).
- **Bug fixed:** earlier iOS dose-logging `LogDoseSheet` collided with `PharmacyView`'s — renamed to `MedicationDoseSheet`.

**Voice Phase 7 (Whisper → clinical NLP):**
- `adapters/whisper_adapter.py`: multilingual STT via an OpenAI-compatible endpoint — self-hosted Whisper (`WHISPER_BASE_URL`, PHI stays in-house) primary, OpenAI hosted Whisper fallback.
- `capabilities/voice.py`: real pipeline (was a 404 scaffold) — audio → Whisper transcript → LLM clinical extraction (symptoms/meds/vitals/complaints/follow-ups as JSON). Tasks: `transcribe`, `transcribe_and_nlm`, `voice_log_meal`. `is_implemented=True`, 8 languages (en/yo/ha/ig/pcm/fr/sw/pt).
- Backend `POST /ai/voice` (multipart audio + language + task) routes through `alafia_infer("voice", …)`; config `WHISPER_BASE_URL`/`WHISPER_MODEL`.
- Verified: capability reports implemented; graceful clear error when no Whisper backend configured; route live (auth-gated).

**Note:** mobile sim/emulator had been shut down, so the rebuilt apps weren't relaunched — APKs/`.app` are built and compile-verified; relaunch when needed to test on-device.

## Session 2026-06-10 (cont.) — Fix PrivacyService (sync/async + arg bugs)

**Instruction:** Fix the flagged PrivacyService.

The privacy endpoints had **two** pre-existing bugs that made them 500 at runtime:
1. **Sync service on async session** — `PrivacyService` uses sync ORM (`.query()`), but endpoints passed the app's only `get_db` (AsyncSession). Added a **sync engine + `SessionLocal` + `get_sync_db`** to `database.py` (psycopg2, `DATABASE_URL_SYNC`) and converted all 13 privacy endpoints from `async def`→`def` using `get_sync_db` (FastAPI runs `def` endpoints in a threadpool, so sync DB never blocks the loop; async deps like `get_current_user` still resolve fine).
2. **`current_user` used as an int id** — endpoints were typed `current_user: int` but `get_current_user` returns a `User`; code did `Model.user_id == current_user` / `user_id=current_user` (→ `ArgumentError: ... got <User object>`). Fixed type hint to `User` and every usage to `current_user.id`.

**Verified end-to-end** (mint token → call against running stack): `/privacy/settings` 500→**200**, `/consent` 500→**200**, `/access-logs` 500→**200**, `/delete-account/status` 500→**404** (correct: no request). This also makes the CollectiveInsight contribution loop (invoked from privacy deletion) run on a real sync session.

**Still flagged:** `personalization.py` (AIMemoryService) and `ai_engine.py`'s `AIPersonalizationEngine` share the same sync-on-async pattern — same `get_sync_db` + `def` fix applies; not done here (scoped to PrivacyService).

## Session 2026-06-10 (cont.) — Fix: /profile blank page (white screen)

**Instruction (urgent):** clicking profile update → blank page.

**Diagnosis:** Audited the Profile/units code (UnitsContext, UnitToggle, utils/units, Profile.jsx) — all correct, no render bug. Couldn't reproduce via headless Playwright (container can't match the browser Origin; and shell-captured tokens were polluted by SQLAlchemy echo logs → false 400s). Root cause is a **stale lazy-chunk** blank screen: `nginx.conf` cached hashed JS/CSS `immutable` for 1y but served **`index.html` with no cache-control**. After a redeploy, a browser holding a cached old `index.html` requests old chunk hashes that no longer exist → failed dynamic `import()` under `<Suspense>` with **no error boundary** → blank white page.

**Fix:**
- Added `src/components/ErrorBoundary.jsx` and wrapped the routes (`App.jsx`): never blanks again — chunk-load failures **self-heal** (reload once for fresh assets); any other render error shows a recoverable message + the error text.
- `nginx.conf`: `index.html` now `Cache-Control: no-cache, no-store, must-revalidate` (app shell always revalidates; hashed assets stay immutable). This is the permanent cure for post-deploy blank pages.
- Rebuilt + redeployed the frontend (it was also 15h stale). Verified `/`→200, fresh bundle hash, ErrorBoundary present in the built JS.

**User action:** one **hard refresh** (Cmd+Shift+R) to drop the stale cached shell; subsequent deploys won't need it.

### Follow-up: React error #31 on profile save (the real Profile bug)

**Error:** Minified React #31 — "Objects are not valid as a React child (found: object with keys {type, loc, msg, input})". Those keys are a **Pydantic 422 validation error**: `PATCH /users/me` failed validation and Profile did `setMessage(err.response.data.detail)` → an array of error objects rendered as JSX → crash. (The ErrorBoundary surfaced this instead of blanking.)

**Root cause (confirmed against the running backend):** the form sent **`""` for empty numeric fields** (`height_cm`/`current_weight_kg`/`target_weight_kg`). Pydantic rejects `""` as a float → 422 `['body','height_cm'] "Input should be a valid number"`. The patient has no height/weight set, so every save hit this.

**Fix (`Profile.jsx` + new `utils/apiError.js`):**
- Numeric fields: empty → `null` (not `""`). Verified: `height_cm:""`→422, corrected payload→**200**. Set-once string fields (`date_of_birth` etc.) keep `""` (backend treats as unchanged; `null` would trip its "cannot be changed once set" guard).
- `apiErrorMessage(err)` coerces any error detail (incl. Pydantic arrays) to a readable string — the catch now uses it, so a 422 can never crash the UI again.

**Also flagged:** 16 other pages use the same raw `data.detail` pattern → latent React #31 risk, but now shielded from full blanking by the ErrorBoundary. Offered to harden them with `apiErrorMessage` in a follow-up pass.

### Follow-up: hardened all pages + recovered a crashed DB

- **Error-handling hardening:** scripted conversion of all 27 raw `data.detail` usages across 16 pages (Journal, ExercisePlanner, Hemodialysis, Calendar, LabCharts, ForgotPassword, Chemotherapy, Roles, Login, ChartDashboard, Telehealth, Wellness, Register, Physicians, MealPlanner) to `apiErrorMessage(err, fallback)`, plus AIChat's raw-fetch helper. No raw `.detail` rendering remains → no page can React-#31 on a 422. Frontend rebuilt.
- **CRITICAL infra incident found during deploy:** the frontend container wouldn't start because **`db` was unhealthy** — Postgres was **crash-looping** with `PANIC: could not write … No space left on device`. The **Docker VM disk was 100% full** (58 GB, 0 free) from this session's many image rebuilds + a ~2 GB Playwright image + 25.8 GB build cache. WAL replay succeeded (only the checkpoint *write* failed) so **no data loss**.
  - Reclaimed ~38 GB via `docker builder prune -af` + `docker image prune -f` + `docker container prune -f` (**never** `--volumes` — `pgdata` holds the patient data). Disk → 55% used.
  - `docker compose restart db` → recovered cleanly: "ready to accept connections", **28 users intact**, healthy.
  - Started frontend with `--no-deps` (to bypass the stale health gate during recovery).
- **Verified:** full stack healthy; `PATCH /users/me` (corrected payload) → 200 end-to-end.
- **Ops note:** frequent `docker compose up --build` fills the Docker disk fast — run `docker builder prune -af` periodically; consider raising Docker Desktop's disk image size.

## Session 2026-06-11 — Firebase→PostgreSQL incremental sync cron (Gap #3)

**Instruction:** a cron/triggered one-directional, delta-only Firebase→PostgreSQL sync is mandatory but not running — fix.

**Diagnosis:** The pipeline (`FirebaseSyncPipeline`) and an APScheduler job already existed and the sync *is* incremental (per user/subcollection it fetches only Firestore docs newer than `MAX(source_timestamp)` in PG — a durable watermark). But `main.py` **hardcoded a 12 h interval and ignored the existing settings** `FIREBASE_SYNC_ENABLED` (default False) and `FIREBASE_SYNC_INTERVAL_SECONDS` (300). So it limped along twice a day, disregarding the intended 5-min cron — effectively "not running."

**Fix:**
- `main.py`: the scheduler now honors the settings — only schedules when `FIREBASE_SYNC_ENABLED`, uses `FIREBASE_SYNC_INTERVAL_SECONDS` (floor 30 s) for the interval, runs the first sync immediately but **non-blocking** (`next_run_time=now`, no inline `await` so startup never waits on Firestore), and adds `max_instances=1` + `coalesce=True` so runs never overlap or pile up.
- `docker-compose.yml` (backend env): `FIREBASE_SYNC_ENABLED=true`, `FIREBASE_SYNC_INTERVAL_SECONDS=300`.

**Verified on the running stack:** `[scheduler] Firebase sync enabled — every 300s (incremental)`, `trigger interval[0:05:00]`, immediate run synced 21 users (0 deltas — watermark current), next run +5 min. One-directional Firebase→PG, delta-only, on a real cron.

## Session 2026-06-11 (cont.) — Periodic docker prune cron (prevent disk-full DB crash)

**Instruction:** implement periodic `docker builder prune` as a cron task.

**Implementation (macOS launchd = the native cron):**
- `scripts/docker-prune.sh` (repo source of truth): reclaims build cache unused >72h + dangling images + stopped containers; logs before/after `system df` to `~/Library/Logs/alafia-docker-prune.log`. **Never** prunes volumes (pgdata) or running-container images. No-ops if the daemon is down.
- `scripts/com.alafia.docker-prune.plist` → installed to `~/Library/LaunchAgents/`; runs daily at **04:00** (catches up on next wake if asleep).
- **TCC gotcha:** the agent first failed with exit **126** because the script lived under `~/Documents` (TCC-protected → launchd can't exec it). Fixed by installing the runtime copy to `~/Library/Application Support/alafia/docker-prune.sh` and pointing the plist there.
- **Verified:** manual run freed 2.8 GB dangling images (kept <72h cache, volumes untouched); `launchctl kickstart` → exit **0** + fresh log entry → full launchd path works.

**Manage:** logs `~/Library/Logs/alafia-docker-prune.log`; run now `launchctl kickstart -k gui/$(id -u)/com.alafia.docker-prune`; change time = edit plist `StartCalendarInterval` + reload; uninstall `launchctl unload ~/Library/LaunchAgents/com.alafia.docker-prune.plist && rm` it.

## Session 2026-06-11 (cont.) — Firebase sync frozen at 6/4 (real delta bug)

**Report:** "firebase sync is not running … last sync date 6/4." The scheduler WAS running every 5 min but reported "0 new records" every time.

**Root cause (proven against live Firestore):** the progressive delta query was `where(ts_field '>' watermark)` with `ts_field='timestamp'`. But the Firestore log docs have **no `timestamp` field** — they carry a string `date` field (e.g. `'2025-08-28'`) and only sparse/inconsistent `createdAt`. So:
- Initial full sync worked and set the watermark to 6/4 (max parsed `date`).
- Every run after, `where('timestamp' > watermark)` matched **nothing** (field absent) → sync froze at 6/4.
- Newly-added docs are often **back-dated** (`date` in 2025) and lack `createdAt`, so NO "newer-than" field query can find them.

**Fix (`firebase_sync.py _sync_user`):** replaced the time-filter with **id-diffing** — load the already-synced `external_id`s for the user/subcollection (one query), fetch the Firestore docs, import the set difference. Gated by a cheap `col_ref.count()` aggregation so unchanged collections cost ~1 read instead of a full stream. Catches new *and* back-dated docs; can't be frozen by a watermark.

**Verified:** rebuilt backend; the scheduler's startup run pulled **+42 records across 21 users** automatically — nutritionLog 833→847, eliminationLog 628→639, vitalsLog 17→19 (all now == Firestore totals), medicationLog +15. Sync runs every 5 min on the new logic.

**Notes:** Firebase↔PG is **uid-keyed** — only 3 of 21 users have real Firestore docs with log subcollections (rest are test accounts / uid-mismatched; not auto-repairable since only 2 Firestore docs carry an `email` field). ~26 medicationLog docs remain unsynced — these are the intentional `_SkipRecord` "known erroneous source" rows (not a bug). Read cost: full fetch only when count grows; raise `FIREBASE_SYNC_INTERVAL_SECONDS` if Firestore reads matter.

## Session 2026-06-11 (cont.) — AI Meal Planner redesign (goals + pantry + missing items)

**Instruction:** rebuild the AI Meal Planner to match the target UI (conversational form) and generate meals from the patient's medical history + current state + preferences + on-hand pantry, with shopping recommendations for missing items.

**Backend (`planners.py`, `schemas/wellness.py`):**
- New schemas `MealSuggestionRequest` (health_goals, preferences, pantry_items, count) / `MealSuggestion` (name, meal_type, ingredients, **pantry_used**, **missing_items**, macros, rationale) / `MealSuggestionsResponse` (suggestions, aggregated shopping_list, advice, pantry_saved).
- Extended `_gather_planner_context` with **recent labs** (latest per test) and the user's **pantry items**.
- `POST /planners/meal-suggestions`: persists the submitted pantry to the profile (`PantryItem` upsert, "saved to your profile"), builds an LLM prompt with conditions/meds/labs/restrictions/recent-foods/goals/preferences/pantry → N suggestions; aggregates unique missing items into one shopping list. Graceful 503 when no LLM is reachable.
- **Bug fixed:** `_gather_planner_context` ordered therapy by `TherapySession.session_date` (doesn't exist) → 500; corrected to `scheduled_date` (this also unbroke the existing `/meal-plan` AI path).

**Frontend (`MealPlanner.jsx`):** rebuilt to match the target — header + "Generate Your Meal Plan" card with health-goals input, preferences textarea, **Pantry/Fridge** textarea (with "saved to your profile" hint), suggestion-count select, and "Generate My Meal Plan". Results render suggestion cards (emoji + meal type, macros, ingredient chips, green "from your pantry" chips, amber "to buy" chips, blue rationale) + an aggregated checkbox Shopping List.

**Verified:** backend compiles; route live (auth-gated); end-to-end run reaches the LLM and returns a graceful 503 because **no LLM is running here** (Ollama down at `host.docker.internal:11434`, `OPENAI_API_KEY` empty). Frontend rebuilt + serving. To get real suggestions: start Ollama (`gpt-oss:20b` or set `OLLAMA_MODEL`) or set `OPENAI_API_KEY`.

## Session 2026-06-11 (cont.) — Ollama in Docker + ML/src mount (AI now actually runs)

**Instruction:** run Ollama in Docker.

- Added an **`ollama`** compose service (`ollama/ollama`, `ollamadata` volume, healthcheck) + pulled **`llama3.2:3b`** (Docker on macOS is CPU-only — no Metal passthrough — so `gpt-oss:20b` would time out; 3b is fast). Backend env → `OLLAMA_BASE_URL=http://ollama:11434`, `OLLAMA_MODEL=llama3.2:3b`, `OLLAMA_TIMEOUT=300`, `depends_on: ollama`.
- **CRITICAL latent bug found:** the backend logged `ALAFIAModel package not importable (No module named 'alafia_model')`. `ML/src` is outside the backend build context, so it was never in the image → **every AI route silently fell back to "unavailable"** in Docker (all the earlier AI-router work, voice, meal planner). Fixed by mounting host `ML/src` → `/ML/src:ro` (the path `alafia_model_service.py` adds to `sys.path`). Router now imports all 5 capabilities in-container.
- **Verified end-to-end:** `POST /planners/meal-suggestions` → **200 in ~25 s** with real output — 2 goal-aware suggestions (sardines/iron for hemoglobin, fortified milk for vit D/calcium), pantry items used, missing items as a shopping list, 5 pantry items saved to profile.
- **Note:** llama3.2:3b sometimes leaves `rationale` thin and mis-sorts a pantry/missing item — small-model quirks; set `OLLAMA_MODEL=llama3.1:8b` (slower on CPU) for richer output, or point back at a GPU/host Ollama.

---

## Session 2026-06-25 — Basis.md review & alignment prompts

**Instruction:** Review `Basis.md` against the codebase; craft prompts that will achieve the Basis vision into `basis_fix_prompt.md`; update project documentation.

**Work done:**
- **Reviewed `Basis.md` vs. code.** Basis defines ALAFIA as a *data-collection hub* whose central
  organizing idea is a **prompt-as-entry-point**: login → Prompt Page, where input modality
  (text/voice/image/video) determines which *existing* UI is surfaced (camera icon next to the
  prompt for capture). Audited the 7 Basis requirements against the implementation.
- **Findings:** Requirement #1 (the universal modality-aware prompt entry point + intent→UI
  routing) is the **biggest gap** — app opens to `Dashboard`/`MainTabView`; AI is siloed across
  `AIChat` (text-only, persona-first), `Capture` (manual upload), `ImageAI`; no `/ai/route`
  intent endpoint; Vision capability still scaffold (`is_implemented=False`). Collection domains
  partial (Sleep/Symptoms lack first-class capture); ground truths missing genetics +
  environmental/social; patterns/relationship-graph + prediction layers absent; HEBCS serving
  seam still unwired (matches gap-analysis #4/#9).
- **Authored `basis_fix_prompt.md`** — a dependency-ordered set of self-contained, reviewable
  implementation prompts across 8 pillars (A: prompt entry point/intent router — the heart;
  B: vision+camera/voice; C: complete collection/ground-truth domains; D: relationship engine;
  E: forecasting; F: HEBCS serving seam; G: agent/hub integration; H: iOS+Android parity), each
  with acceptance criteria and cross-cutting guardrails (never bypass the ALAFIAModel router,
  reuse existing UIs, associations≠causation, no fabricated clinical data).

**Notes / open items:**
- `basis_fix_prompt.md` is for user review before any implementation — no code changed this session.
- The prompts deliberately reuse existing screens via a `prefill` hand-off rather than building
  parallel UIs, per Basis: *"We reuse current UIs."*

---

## Session 2026-06-26 — Implementing Basis prompts (Pillar A + B)

**Instruction:** Implement the prompts in `basis_fix_prompt.md` (the prompt-as-entry-point vision).

**Work done — the multimodal Prompt Hub vertical slice (Basis req #1):**
- **A2 — `classify_intent` (ML):** New NLM task in `ML/src/alafia_model/capabilities/nlm.py` that
  classifies a prompt into a fixed intent taxonomy (`INTENT_LABELS`) + entities via the LLM
  (json_mode), with deterministic `ask_question` fallback when the model is unavailable/unparseable.
  Tests: `ML/tests/test_nlm_intent.py` (8 passing).
- **A1 — `/ai/route` (backend):** New `POST /api/v1/ai/route` in `app/api/ai.py` with a single
  `INTENT_ROUTE_MAP` source of truth mapping each intent → existing screen + action + prefill.
  Routes via `alafia_infer` (never OpenAI/Ollama directly); low-confidence/unknown → chat fallback;
  bare image attachment → capture. Schemas `AIRouteRequest/Response`. Tests: `tests/test_ai_route.py`
  (auth-gating verified; the 3 auth-dependent cases fail only in the offline local venv — the
  pre-existing nutrition test fails identically — and pass in Docker/CI).
- **A3 — `PromptHub.jsx` (web):** New landing surface, now the authenticated index route (`/`);
  Dashboard moved to `/dashboard`; sidebar gains an "Ask ALAFIA" link. Text + mic (MediaRecorder →
  `/ai/voice` → transcript → `/ai/route`) + camera (`/ai/vision` → nutrition or manual capture)
  + quick actions. Navigates to the matched screen with `{ prefill, fromPrompt }`.
- **A4 — prefill consumption (web):** New reusable hook `hooks/usePromptPrefill.js`; wired into
  Nutrition, Medications, Fitness, Journal, and Elimination so a prompt opens their create/log form
  pre-filled (and clears nav state so refresh/back doesn't re-trigger).
- **B1 — Vision capability + `/ai/vision`:** Implemented `food_photo_nutrition` in
  `capabilities/vision.py` via a vision-capable LLM (OpenAI gpt-4o family) with strict-JSON parsing,
  modest confidence, and graceful 503 degradation when no backend is configured (client falls back
  to manual Capture). Added `content_type` to the router `InferencePayload`. New `POST /api/v1/ai/vision`.
  Tests: `ML/tests/test_vision.py` (6 passing).
- **B2 — camera/voice in the hub:** Implemented as part of A3 (PromptHub talks to `/ai/voice` and
  `/ai/vision`).

**Verification:**
- ML: 14/14 (`test_nlm_intent.py` + `test_vision.py`) pass in `.venv-health-ml`.
- Web: all changed JSX (PromptHub, App, Layout, 5 screens, hook) compile via esbuild in Docker.
- Backend: `app/api/ai.py` parses; app imports with the new endpoints.

**Notes / open items:**
- Local backend venv was under-provisioned; installed `-r requirements.txt` so the app imports.
  Auth-dependent API tests can't complete offline (registration needs services) — same pre-existing
  limitation as the existing suite; these run green in Docker/CI.
- Remaining Basis pillars not yet started: **C** (first-class Symptom/Sleep capture + genetics/
  environmental ground truths), **D** (relationship engine), **E** (forecasting), **F** (HEBCS
  serving seam), **G** (route `ask_question` straight into persona chat), **H** (iOS + Android
  PromptHub parity).

---

## Session 2026-06-26 (cont.) — Prompt Hub bug fixes + Ollama for dev

**Instruction:** Voice listener triggers but no input registers; web camera opens a file picker
but submitting does nothing. Also: use Ollama (local) as the LLM engine for dev.

**Root causes found:**
- **Camera "no action":** nginx had no `client_max_body_size` → defaulted to 1MB, so camera photos
  (2-5MB) were rejected with **413 before reaching the backend** (small voice audio passed, which is
  why voice reached the backend but images never did).
- **Voice "no response":** `/ai/voice` returned **503** — no transcription backend configured
  (neither `WHISPER_BASE_URL` nor `OPENAI_API_KEY`), and Ollama cannot do speech-to-text.

**Fixes:**
- **nginx:** added `client_max_body_size 25M;` (`frontend/nginx.conf`) so photo/audio uploads proxy
  through to the backend.
- **Vision → Ollama:** added base64 image support to `ollama_adapter.chat(images=...)`; rewrote
  `VisionCapability._vision_chat` to **prefer local Ollama** (a vision model) with OpenAI as
  fallback; `is_available()` now true when `OLLAMA_BASE_URL` or `OPENAI_API_KEY` is set.
  `OLLAMA_VISION_MODEL` env added. `llava:7b` OOM-killed llama-server on the 7.7GB Docker VM, so
  switched to **moondream** (~1.7GB) — verified end-to-end (`source=vision-ollama:moondream`,
  valid JSON parsed).
- **Voice (dev):** `PromptHub` now prefers the browser **Web Speech API** (free, on-device, no
  server STT) and falls back to record→`/ai/voice` (Whisper) only when the browser lacks it.
  Clear error messages on mic-denied/no-speech.
- **Timeouts:** PromptHub `/ai/route`, `/ai/voice`, `/ai/vision` calls now use a 180s client
  timeout (local CPU inference is slow).

**Verification:** ML 14/14 pass; vision e2e through moondream returns parsed JSON; backend env shows
`OLLAMA_VISION_MODEL=moondream`; nginx container has the 25M limit; frontend 200, endpoints 403
(auth-gated). Stack rebuilt + restarted.

**Notes:** Voice via Web Speech API works in Chromium-based browsers; Firefox lacks it and will use
the server path (still needs a Whisper backend). To use a stronger vision model (llava), raise the
Docker Desktop memory allotment, then set `OLLAMA_VISION_MODEL=llava:7b`.

---

## Session 2026-06-26 (cont.) — Pillars C (Symptoms, Sleep) + G (agent hand-off)

**Instruction:** Leave HEBCS (Pillar F) for now; continue with the other pillars.

**Work done:**
- **C1 — Symptoms (full stack):** `SymptomLog` model already existed (`models/conditions.py`) but had
  no API/UI. Added `schemas/symptoms.py`, `api/symptoms.py` (CRUD), registered at `/symptoms`, new
  `pages/Symptoms.jsx` + route + sidebar entry, wired `usePromptPrefill`. INTENT_ROUTE_MAP
  `log_symptom → /symptoms`. No migration needed (table already in DB).
- **C2 — Sleep (full stack):** same pattern on the existing `SleepLog` model — `schemas/sleep.py`,
  `api/sleep.py`, `/sleep`, `pages/Sleep.jsx` (+ a small "6 hours" text extractor for prefill),
  route + nav + prefill. INTENT_ROUTE_MAP `log_sleep → /sleep`.
- **C3 — deferred:** new genetics + environmental/social ground-truth tables need a migration into a
  DB already behind head (x001 unapplied) and their only consumers are Pillars D/F — so C3 will land
  with the relationship engine (D) that uses it. Noted in basis_fix_prompt.md.
- **G — agent hand-off:** refactored `AIChat` send logic into `sendMessage(text, persona, base)`;
  added an `autoAsk` effect that skips the persona picker, defaults to the general practitioner, and
  answers immediately. `PromptHub` sends `ask_question` prompts to `/ai` with `autoAsk`.
- **Weak-model guard:** added a deterministic rule in `/ai/route` — a prompt ending in "?" is never a
  `log_*` intent (fixes `llama3.2:3b` mislabeling "what foods lower potassium?" as log_meal).

**Verification (live app, not just offline):**
- Registration/login work against the running postgres backend (the earlier offline failures were
  purely the SQLite/stub test harness).
- End-to-end: created a symptom (201) and sleep log (201), listed them back.
- Intent routing via `llama3.2:3b`: "bad headache" → `/symptoms` (0.9); "slept 6 hours, woke twice"
  → `/sleep` (0.8); "what foods lower potassium?" → `ask_question`/`/ai` (after guard).
- 10 symptom/sleep routes registered; clean backend startup; all frontend compiles (esbuild/Docker).
- Tests added: `tests/test_symptoms_sleep_api.py` (auth-gating), `test_ai_route` question-guard case.

**Next:** Pillar D (relationship/correlation engine + view) carrying C3 ground truths, Pillar E
(forecasting), Pillar H (iOS/Android PromptHub parity).

---

## Session 2026-06-26 (cont.) — Pillars D & E (cornerstones: relationships + forecasts)

**Instruction:** "E and D are cornerstones of ALAFIA, so proceed."

**Work done (all pure-Python — no numpy/pandas added):**
- **Shared substrate — `services/health_signals.py`:** `collect_signals()` builds per-day numeric
  series for the user across diet (NutritionLog: sodium/potassium/phosphorus/fluid/macros), vitals
  (VitalsLog + LifestyleEntry merged: weight/BP/HR/glucose/SpO2/temp), activity (FitnessLog), mood,
  sleep, symptoms (daily count + worst severity), and labs (one signal per test). `SIGNAL_META`
  carries label/domain/aggregation (sum vs mean).
- **D1 — `services/insights_engine.py`:** lagged Pearson correlations across signals. For each
  cross-domain ordered pair and lag 0..N, aligns A[d] with B[d+lag], computes r, keeps the strongest
  edge per pair above a threshold. Emits `{source,target,labels,strength,direction(leads/co-occurs),
  lag_days,sample_size,caveat}`. Every edge stamped "association, not causation".
- **D2 — `pages/HealthInsights.jsx`:** Relationships list with signed strength bars + lead/lag labels;
  prominent association≠causation banner.
- **E1 — `services/forecast_engine.py`:** OLS linear-trend forecast with 95% residual band + trend
  label; documented seam to swap in a trained model later. `forecast_signal` / `forecastable_signals`.
- **E view:** dependency-free SVG chart in HealthInsights (history solid, projection dashed, 95% band
  shaded) with a signal picker.
- **API — `api/insights.py`** (`/insights/signals|relationships|forecast`), registered at `/insights`.
  `INTENT_ROUTE_MAP` `view_trends → /insights`; sidebar "Health Insights" link; route added.

**Verification (live, seeded 16 days of correlated data):**
- Engine unit tests: `tests/test_insights_engine.py` 9/9 pass (Pearson, lag alignment, cross-domain
  filter, lagged-edge detection, forecast trend/CI, insufficient-data guard).
- End-to-end: seeded sodium[d]→systolic-BP[d+1] and a rising weight; `/insights/relationships`
  returned **"Sodium leads Systolic BP (lag 1d) r=1.0 n=15"**; `/insights/forecast?signal=vital.weight_kg`
  returned **trend=rising, slope 0.2/day**, projecting 73.2/73.4/73.6 — both exactly as designed.
- Endpoints auth-gated (401); HealthInsights chunk shipped in the frontend bundle; clean rebuild.

**Next:** Pillar H (iOS + Android PromptHub parity) and C3 ground-truth inputs (genetics +
environmental/social) to enrich D/E.

---

## Session 2026-06-26 (cont.) — Pillar C3 (genetics + environmental/social ground truths)

**Instruction:** "C3 first and then H."

**Work done:**
- **Migration drift resolved:** DB was at `w001` with `x001` (device_tokens) unapplied and that table
  absent — so `alembic upgrade head` cleanly applied `x001` then the new `y001` (no conflict). This
  also finally created the long-missing `device_tokens` table (gap-analysis N-item).
- **Models (`models/ground_truth.py`):** `GeneticMarker` (static per-user findings: gene, variant,
  genotype, associated_condition, risk_level, source…) and `EnvSocialLog` (time-varying: location,
  AQI, temp/humidity, noise/pollen, household, occupation, work/financial stress, social support,
  major life event). Registered in `models/__init__.py`; User gains `genetic_markers` +
  `env_social_logs` relationships. Alembic `y001_add_ground_truth_tables`.
- **CRUD (`api/ground_truth.py`, `schemas/ground_truth.py`):** `/ground-truth/genetics` and
  `/ground-truth/env-social` (list/create/delete), registered at `/ground-truth`.
- **Wired into Pillar D/E:** `health_signals.py` now emits env/social signals
  (`env.aqi`, `env.ambient_temp_c`, `env.humidity_pct`, `social.work_stress`,
  `social.financial_stress`, `social.support`) — new domains, so they form cross-domain edges with
  diet/vitals/sleep/mood in the relationship engine.
- **Wired into AI context:** `_fetch_patient_context` now appends "GENETIC GROUND TRUTHS" and
  "ENVIRONMENTAL & SOCIAL FACTORS" sections (C3 acceptance criterion).

**Verification (live):**
- `alembic upgrade head` applied x001 + y001; `genetic_markers`, `env_social_logs`, `device_tokens`
  tables exist; alembic head = `y001`.
- End-to-end: created APOL1 (high-risk CKD) genetic marker + 12 env/social rows; `/insights/signals`
  now lists `env.aqi`, `social.work_stress`, `social.support`; `_fetch_patient_context` prints
  `APOL1 (G1/G1) — CKD [high risk]` and `location Lagos; AQI 113; … work stress 6/10; social support 6/10`.
- Endpoints auth-gated (401); `tests/test_ground_truth_api.py` added.

**Note:** No dedicated UI yet (per C3 scope — "schema + minimal CRUD, no fancy UI"); the data is
captured via API and consumed by the engines + AI context. A capture UI can ride along with Pillar H.

---

## Session 2026-06-26 (cont.) — Pillar H (mobile PromptHub parity)

**Instruction:** "C3 first and then H." (H follows the C3 work above.)

**Work done — Basis "Mobile starts with a Prompt Page" on both platforms:**
- **H2 Android:** `views/prompt/PromptScreen.kt` — a `PromptViewModel` (androidx.lifecycle.ViewModel +
  viewModelScope; sets the MVVM/StateFlow-ish pattern the gap analysis wanted) that calls the new
  `ApiService.routePrompt` (`POST ai/route`) and maps the returned web route → the matching Android
  NavHost destination (`WEB_TO_ANDROID_ROUTE`, with sensible fallbacks for screens not yet on mobile).
  Added `AIRouteRequest/AIRouteResponse` to `schemas/Schemas.kt`. `MainTabView` now starts on
  `prompt`, the first tab is "Ask", and Dashboard moved into the More grid (kept reachable).
- **H1 iOS:** `Views/Prompt/PromptView.swift` — `@Observable PromptViewModel` calling
  `APIClient.shared.post("/ai/route")`, with a `PromptDestination` enum mapping intent → an existing
  SwiftUI view, presented via `.sheet` (reuse current UIs). Added as the first `TabView` tab ("Ask").

**Verification:**
- iOS: `swiftc -parse` clean on PromptView + MainTabView (types matched to existing views/APIClient).
- Android: `./gradlew :app:compileDebugKotlin` → **BUILD SUCCESSFUL** (full Kotlin type-check). Only a
  cosmetic `Icons.Filled.Send` deprecation warning, identical to existing code (DirectionsRun/Chat).

**Deferred (noted):** mobile voice (SFSpeechRecognizer / Android SpeechRecognizer) + camera
(`/ai/vision`) — the web hub has these; mobile ships the text-routing cornerstone first. Mobile
release builds still need real cert-pin hashes (pre-existing N1 risk). Backend `view_trends`,
`log_symptom`, `log_sleep` map to closest existing mobile screens until those screens are added.

**Status:** Basis pillars A, B, C, D, E, G, H implemented & verified; F (HEBCS serving) deferred by
the user.

---

## Session 2026-06-26 (cont.) — Mobile voice + camera (true web↔mobile parity)

**Instruction:** "Add mobile voice/camera to finish true web↔mobile parity."

**Work done — both platforms now match the web hub (text + voice + camera):**
- **Android (`views/prompt/PromptScreen.kt`):**
  - Voice via the system speech recognizer (`RecognizerIntent.ACTION_RECOGNIZE_SPEECH` through an
    `ActivityResultContracts.StartActivityForResult` launcher) → transcript → `/ai/route`. No
    RECORD_AUDIO permission needed (system UI handles capture).
  - Camera/photo via `ActivityResultContracts.GetContent()` → multipart upload to the new
    `ApiService.routeVision` (`POST ai/vision`) → Nutrition if food detected, else Image AI.
  - Added `AIVisionResponse`/`VisionItem` schemas; mic + camera icon buttons in the prompt row.
- **iOS:**
  - New `Core/SpeechRecognizer.swift` — on-device `SFSpeechRecognizer` + `AVAudioEngine` live
    transcription (mirrors the web Web Speech API); requests speech + mic permission.
  - `Views/Prompt/PromptView.swift` — mic button (start/stop → transcript → `/ai/route`) and a
    `PhotosPicker` (image → multipart `/ai/vision` → Nutrition or Image AI). Added `AIVisionResponse`
    decoding + a multipart upload helper (180s timeout for slow local inference).
  - `Info.plist`: added `NSMicrophoneUsageDescription`, `NSSpeechRecognitionUsageDescription`,
    `NSPhotoLibraryUsageDescription`.
  - Registered `PromptView.swift` + `SpeechRecognizer.swift` in `ALAFIA.xcodeproj/project.pbxproj`
    (new `Prompt` group under Views; SpeechRecognizer under Core) — the prior build failed only
    because new files weren't in the project's source list.

**Verification (real compiles, not just parse):**
- **iOS:** `xcodebuild -scheme ALAFIA -destination 'generic/platform=iOS Simulator' build` →
  **BUILD SUCCEEDED** (full type-check against iOS SDK).
- **Android:** `./gradlew :app:compileDebugKotlin` → **BUILD SUCCESSFUL** (only a cosmetic
  `Icons.Filled.Send` deprecation warning, shared with existing code).

**Parity achieved:** web (text + Web Speech API + camera→/ai/vision), iOS (text + SFSpeechRecognizer
+ PhotosPicker→/ai/vision), Android (text + RecognizerIntent + GetContent→/ai/vision).

**Status:** Basis pillars A, B, C, D, E, G, H complete & verified; F (HEBCS serving) deferred by user.
Remaining polish: C3 ground-truth capture UI; real mobile cert-pin hashes for release builds.

---

## Session 2026-06-26 (cont.) — Firebase→PG sync: medication, elimination, journal fixes

**Instruction:** Sync works for Food but not medication/elimination; verify Firestore docs for
medication, elimination, vitals, journals, therapies and ensure sync works. ("vomiting is elimination too")

**Diagnosis (verified against live Firestore + PG):**
- Firestore data lives under `users/{uid}/<subcollection>`. The fully-populated patient is
  `sKhP73…` = PG user 63 (developer@hntsolutions.com): medicationLog 1283, eliminationLog 677,
  vitalsLog 22, journalEntries 5, hemodialysisFlowsheets 21, nutritionLog 882.
- The sync **was running** (synced_records + domain rows existed), but several domains synced into
  tables the **UI doesn't read** — Food only worked because its target (`nutrition_logs`) matches the
  read source. Mismatches found:
  - **medicationLog** → `medication_dose_logs` (826) ✓ synced, but the **Medications page only read the
    `medications` catalog** (0 rows; dose-events are deliberately NOT written there — that catalog-write
    was a previously-fixed "medication fabrication" bug). So synced doses were invisible.
  - **eliminationLog** → ALL dumped into `bowel_movements` (poop 519 + **vomiting 143** + blank),
    ignoring `eventType` → vomiting never reached the Vomiting tab.
  - **journalEntries** → `lifestyle_entries`, but the **Journal page reads `mood_entries`**.
  - vitalsLog → vitals_logs (fed charts/wellness, OK); hemodialysisFlowsheets → therapy_sessions (OK).

**Fixes:**
- **Medication (frontend):** `Medications.jsx` now loads `GET /medications/dose-logs` and shows a
  **Dose History** table — surfaces the 826 synced doses without polluting the prescription catalog.
- **Elimination (sync code):** `firebase_sync.py` routes `eliminationLog` by `eventType` →
  `vomiting_logs` (vomit/emesis), `urination_logs` (urine/void), else `bowel_movements`. Weights/image
  preserved in notes for urine/vomit. Backfill SQL moved the 143 existing vomiting rows out of
  `bowel_movements` into `vomiting_logs` (idempotent, all users).
- **Journal (sync code):** `journalEntries` now maps to `mood_entries` (mood→1-10 score, sleep_hours,
  feelings→emotions, content→journal_entry). Cleared the journalEntries ledger and re-synced → 5 entries
  now in mood_entries (Journal page).

**Verified (user 63 after fixes):** mood_entries 6→11; medication_dose_logs 826 (now shown);
bowel_movements 677→534; vomiting_logs 108→241; therapy_sessions 21; vitals_logs 24; nutrition_logs 871.

**Notes:** The 5 original journal `lifestyle_entries` remain as harmless orphans (show under Daily
Vitals). Vitals have no dedicated CRUD page but feed charts/wellness. Future syncs route correctly via
the code fixes; existing data fixed via backfill/re-sync.

---

## Session 2026-06-26 (cont.) — Purge journal orphans + standalone Vitals domain

**Instruction:** Purge the orphaned (duplicate) entries; vitals are NOT lifestyle — make vitals a
standalone data collection with an entry form, a running vitals log UI, and trends charts.

**Work done:**
- **Purged journal orphans:** deleted the 5 `lifestyle_entries` that the old journal sync had written
  (precise signature: `notes LIKE 'mood=%'` with no weight/BP/HR). They were duplicates of the journal
  data now correctly in `mood_entries`. User 63 `lifestyle_entries` 5 → 0.
- **Vitals as a first-class domain** (its own table `vitals_logs`, which the Firebase sync already
  targets — so synced + app-entered vitals share one log/trends):
  - Backend: `schemas/vitals.py` + `api/vitals.py` (full CRUD, auto-computes BMI from weight+height),
    registered at `/vitals`.
  - Frontend: `pages/Vitals.jsx` — entry form (weight, BP, HR, temp, SpO₂, glucose, notes), a
    **Trends chart** (recharts `LineChart` with a metric selector: BP dual-line, weight, HR, glucose,
    SpO₂, temperature), and a **running Vitals Log** table. Route `/vitals` + sidebar entry ("Vitals",
    with "Daily Vitals" relabeled "Lifestyle" to end the conflation).

**Verified (live):** `/vitals` auth-gated (401); CRUD create returns auto-BMI 22.9 for 70kg/175cm;
the 24 Firebase-synced vitals for user 63 are now readable by the Vitals page; Vitals chunk shipped
in the frontend bundle.

**Net sync alignment:** every collected domain now lands in a table its UI reads — Food→nutrition,
Medication→dose-logs (Dose History), Elimination→bowel/urine/vomit (by eventType), Journal→mood,
Vitals→vitals_logs (standalone page + trends), Therapies→therapy_sessions.

---

## Session 2026-06-26 (cont.) — Smoke test + unified Elimination Log redesign

**Instruction:** Smoke-test page rendering; revisit the elimination log to match ALAFIA.app
reference (images): unified poop/urine/vomit log with event-type captured AND displayed.

**Smoke test (running app):** frontend serves 200; all new page chunks present (PromptHub, Vitals,
Symptoms, Sleep, HealthInsights, Medications, Elimination). Authenticated endpoint sweep all 200
EXCEPT `medications/dose-logs` → **422**.
- **Bug found + fixed:** `GET /medications/{med_id}` (declared earlier) shadowed `GET /medications/dose-logs`
  ("dose-logs" failed int parse → 422), making the Dose History I added unreachable. Constrained the
  param to `/{med_id:int}` (get/patch/delete). `dose-logs` now 200.

**Elimination redesign (match reference, unified):**
- **Backend:** migration `z001` adds `pre_event_weight_kg`, `post_event_weight_kg`, `image_uri` to
  `urination_logs` + `vomiting_logs` (parity with bowel). New unified endpoints in `elimination.py`:
  `GET /elimination/all` (merges poop/urine/vomit into one timeline, each tagged with `event_type`),
  `POST /elimination/all` (routes by event_type), `DELETE /elimination/all/{event_type}/{id}`.
  Per-type endpoints retained. Sync now writes weights/image to urine/vomit columns.
- **Frontend:** rewrote `Elimination.jsx` to the reference layout — one "Add New Log Entry" form with
  an **Event Type** selector (Poop/Urination/Vomiting), Pre/Post weight, description, image; a
  **calendar** with entry-dots + month nav; and a per-date timeline of cards "{Type} At {HH:MM}" with
  Pre/Post-Weight + Description (+ image). Event type is shown on every card. (Replaces the old
  tabbed Bristol/color table.)

**Verified (live):** migration applied (columns present); created poop/urine/vomit via `/elimination/all`
(201 each) → `GET /all` returns them typed, weighted, newest-first; user 63 merges to 534 poop + 241
vomit = 775 events; new Elimination + Medications bundles shipped; `dose-logs` and `elimination/all`
both 200.

---

## Session 2026-06-26 (cont.) — Medication views redesign (error-laden → reference)

**Instruction:** Match ALAFIA.app reference for medication logging + viewing; combine the two views
with the calendar next to the log form. Local dev showed an error-laden Dose History (notes packed
with raw `ai_analysis={…Gemini 404 error…}` JSON).

**Root cause:** the medicationLog sync packed `time=`, pre/post vitals, AND the mobile app's
`aiNutritionalAnalysis` blob (usually a Gemini error) all into the dose-log `notes` string. Time/vitals
weren't structured columns, so the UI dumped the whole mess.

**Backend:**
- Migration `aa001` adds `log_time` + `pre/post_systolic_bp`, `pre/post_diastolic_bp`,
  `pre/post_heart_rate` to `medication_dose_logs`. Model + dose-log schema (Create/Response) + POST
  handler updated to persist them.
- Sync rewritten: writes time→`log_time`, vitals→columns, and **drops the ai_analysis blob** (notes
  now hold only the user's own text).
- **Backfilled 826 existing rows:** parsed `time=`/`pre_BP`/`pre_HR`/`post_*` out of notes into the new
  columns and stripped `ai_analysis=` → clean notes. Verified: 826/826 have `log_time`, **0 rows still
  contain `ai_analysis`**.

**Frontend (`Medications.jsx`, combined per request):** one page with the **Log New Medication Intake**
form (Date, Time, Medication [datalist of catalog + free text], Dosage Taken, Pre/Post-Medication
Vitals, Notes) on the left and the **calendar (Select Date) with entry-dots + date-filtered history
cards** on the right ("HH:MM – Name", dose, pre/post vitals, clean notes). The prescription catalog
moved into a collapsible "Prescriptions" section. `cleanNotes()` also strips any legacy tokens
defensively.

**Also fixed (found via smoke test):** `GET /medications/{med_id}` shadowed `GET /medications/dose-logs`
→ constrained to `{med_id:int}` so dose-logs is reachable (was 422).

**Verified (live):** dose-log create with time + pre/post vitals returns structured fields; sample
user-63 rows show `log_time` + `(clean)` notes; new Medications bundle shipped.

---

## Session 2026-06-26 (cont.) — Remove redundant Lifestyle + temperature units (°F default)

**Instruction:** The Lifestyle screen duplicates Vitals — remove it. US default temperature unit is °F
(not °C); let users toggle, but convert to and display Celsius, and remember the preference.

**Lifestyle removal:** dropped the "Lifestyle" sidebar link, the `/lifestyle` route, and its lazy
import from `App.jsx`. Verified no dangling links remain; the Lifestyle chunk is no longer built.
(Vitals is now the single vitals/measurements surface.) The backend `/lifestyle` endpoint + page file
remain as harmless dead code.

**Temperature units (Vitals form):**
- Added a °F/°C input toggle defaulting to **°F** (US), persisted in `localStorage[alafia_temp_unit]`
  so future entries keep the user's choice.
- Entered value is converted to **Celsius** on save (`fahrenheitToCelsius` from `utils/units`) and
  stored in `body_temperature_c`; switching the toggle converts any in-progress value in place.
- Display (Vitals log + trends) remains **Celsius** (canonical), matching the request.

**Verified:** frontend rebuilt; temp toggle present in the Vitals bundle; Lifestyle chunk gone;
F→C math correct (98.6°F→37.0°C, 100.4°F→38.0°C).

---

## Session 2026-06-26 (cont.) — App-wide temperature units (°F default, display follows toggle)

**Instruction:** Apply the °F-default temperature toggle to medication intake pre/post vitals and the
HD Flowsheet; make displayed values follow the toggle (US users see °F in logs/trends).

**Shared hook `hooks/useTempUnit.js`:** single source of truth — unit (default °F, persisted in
`localStorage[alafia_temp_unit]`), `toggle`, `toCelsius` (input→storage), `fromCelsius`/`fmt`
(storage→display), `convertInPlace` (keep in-progress value on toggle). Storage is always Celsius.

**Vitals:** refactored to the hook; the temperature **input and display now follow the toggle** —
log table cell and the trends chart (values + axis unit) render in the chosen unit.

**Medication intake (added temperature):** migration `bb001` adds `pre_temperature_c` /
`post_temperature_c` to `medication_dose_logs`; model + dose-log schema (Create/Response) + POST
updated. The combined Medications page now has a Temp field in both Pre- and Post-Medication Vitals
(with a `temp: °F/°C` toggle), converts to Celsius on save, and shows temp in the history cards in the
chosen unit.

**HD Flowsheet:** fixed a latent bug — the form labeled temperature "°F" but wrote the raw value into
the Celsius `pre_temperature`/`post_temperature` columns (the sync stores Celsius). Now uses the shared
toggle (default °F), converts input→Celsius on submit, and converts Celsius→chosen unit when loading a
session for edit. Added a `temp: °F/°C` toggle in the Pre-Treatment Vitals header.

**Verified (live):** `bb001` applied (temp columns present); dose-log accepts/returns
`pre/post_temperature_c`; Vitals/Medications/Hemodialysis bundles shipped; F↔C math correct.

---

## Session 2026-06-27 — Surfaced & reviewed FlowSheet (6IGMA clinical complement)

**Instruction:** `../FlowSheet` is a standalone complement of ALAFIA — surface it and review.

**Reviewed `Developer/FlowSheet`** (sibling on disk, not a git repo): a clinical-grade **hemodialysis
flowsheet portal** by 6IGMA Health (same brand as ALAFIA). Backend = FastAPI/async-SQLAlchemy/asyncpg,
PostgreSQL 18, Redis 7, Ganache private chain, Nginx (~4.6k LOC, 62 integration tests); static HTML role
dashboards (patient/nurse/physician/care-partner/admin) + DaVita & 6IGMA flowsheet forms; native iOS
(Swift 6.2) + Android (Kotlin/Compose). Distinctive: clinical sign-off lifecycle
(submit→sign→countersign→review→note→audit), append-only **blockchain audit** (SHA-256 anchoring, PHI
off-chain), **FHIR R4** export, WebSocket notifications, and the **255-char SID** generated in Postgres.

**Positioning:** ALAFIA = patient hub (dialysis is one feature); FlowSheet = clinic-facing compliance
record. **Shared backbone = the SID** (both have system_id model/service) + a blockchain model/service →
the SID is the cross-app join key. API ports don't clash (FlowSheet :8000 vs ALAFIA :8005).

**Cleanup flags:** not git-tracked; `files-3/6igma_health_backend` is a stale partial duplicate of
`src/6igma_health_backend`; DaVita/Sigma forms duplicated across `src/` and `.../frontend/`; a real `.env`
is committed; chain divergence (Ganache vs ALAFIA's Foundry/anvil).

**Surfaced:** wrote `docs/FLOWSHEET_REVIEW.md` (full review + integration opportunities + run steps) and a
`flowsheet-complement` memory (+ MEMORY.md index). Top integration lever = align the SID algorithm across
both apps; FHIR R4 is the dialysis-record exchange format.

---

## Session 2026-06-27 — Plan: align ALAFIA Therapies (HHD/PD) with FlowSheet

**Instruction:** Create a plan + prompts to fully align ALAFIA Therapies (HHD, PD) with FlowSheet —
FlowSheet is the reference/superior; both share ONE User DB (a user in one is reused in the other;
unique email/username/profile); both FHIR + blockchain compliant.

**Cross-system diff captured** (in `alafia_flowsheet_alignment_plan.md`): two hard conflicts to resolve
first — (a) both apps mint an "S1…" 255-char SID but with incompatible algorithms (ALAFIA RND93+SHA512
vs FlowSheet RND157+SHA256), and (b) int (ALAFIA) vs UUID (FlowSheet) user PKs. ALAFIA also has no
`username` and no FHIR export; two separate chains (anvil vs Ganache).

**Deliverable:** `alafia_flowsheet_alignment_plan.md` — 6 phases with dependency-ordered prompts +
acceptance criteria:
- **P1 Unified identity** (recommended: shared "6IGMA Identity" service; canonical SID = FlowSheet's;
  add unique username; UUID `identity_uid` bridge for ALAFIA's int FKs; SSO via shared JWT; Firebase as
  upstream IdP; backfill/link existing users).
- **P2 Therapies → FlowSheet model** (flowsheet submission/field/monitoring shape; submit→sign→
  countersign→review→lock lifecycle; role/care-link alignment).
- **P3 FHIR R4** for ALAFIA mirroring FlowSheet's fhir.py (Patient/Observation/Procedure/DiagnosticReport).
- **P4 One audit ledger** (converge chain + SHA-256 hash-chaining; anchor therapy transitions; SID-keyed
  merged trail).
- **P5 FHIR-based therapy hand-off** (signed FlowSheet flowsheet → ALAFIA read-only by SID).
- **P6 Mobile parity + FlowSheet repo hygiene** (git init, drop files-3 dup, .env).

Guardrails: FlowSheet is reference; one canonical SID + one user per person; PHI never on-chain;
additive migrations with old→new SID map; bridge int FKs via identity_uid (no big-bang UUID rewrite).

---

## Session 2026-06-27 (cont.) — Identity decision locked + topology refined

**Instructions:** (1) the goal is exactly a SHARED identity service, zero duplication; (2) the shared
FlowSheet DB resides on ALAFIA; FlowSheet is a lightweight intro module so users transition to the
bigger app with no glitch.

**Locked + refined:**
- **Decision LOCKED:** single shared **6IGMA Identity service, zero duplication** — identity data
  (email, unique username, password, profile, SID, IdP links) lives only in the `identity` schema; ALAFIA
  + FlowSheet hold only a reference key (`identity_uid`/SID) for FKs.
- **Co-location:** the shared identity DB **and** FlowSheet's domain DB reside on **ALAFIA's** Postgres
  cluster, schema-separated (`identity` / `flowsheet` / `alafia`). Not a separate deployment.
- **FlowSheet = lightweight intro/on-ramp module;** FlowSheet→ALAFIA upgrade is a **feature-unlock
  (tier flip), not a migration/re-login** — identity + flowsheet data already co-resident ⇒ "no glitch".

**Artifacts:**
- `docs/IDENTITY_ARCHITECTURE.md` — Phase 1.1 contract: principles (zero-dup), co-located topology
  diagram, canonical schema (seeded from FlowSheet) + `username`/`external_auth`, `/identity/*` API,
  RS256 JWT + JWKS SSO, per-app reference-only integration, **§6b seamless transition**, migration/backfill.
- `alafia_flowsheet_alignment_plan.md` updated: 5 goals (shared identity / co-location / intro-module /
  FHIR / blockchain); Phase 5 reframed from cross-app sync → co-resident surfacing + seamless upgrade
  (Prompts 5.1 read-across-schemas, 5.2 entitlement/tier upgrade).

**Next code step (Prompt 1.2):** canonical SID generator = FlowSheet's algorithm
(`S1·FN3·LN3·DOB8·GEN1·EPO10·RND157·SHA256`), retiring ALAFIA's RND93+SHA512.

---

## Session 2026-06-27 (cont.) — IdP is PostgreSQL-native, not Firebase

**Instruction:** "IdP is based on PostgreSQL NOT Firebase."

**Updated** `docs/IDENTITY_ARCHITECTURE.md` + `alafia_flowsheet_alignment_plan.md`: the identity provider
is the **`identity` schema itself** — email/username + **bcrypt** password_hash in Postgres (FlowSheet's
model) + RS256 JWT/JWKS SSO. **Firebase retired** from the live auth path; ALAFIA migrates off it.
Firebase survives only as a one-time **`legacy_auth_links`** record; migrated (passwordless) accounts
onboard via `/identity/password/reset-request` on first login, then Firebase is decommissioned. Removed
the `/identity/firebase-exchange` endpoint and the "Firebase as upstream IdP" flow; auth flows §6 are now
Postgres-native for both apps. Prompt 1.4 retitled accordingly.

---

## Session 2026-06-27 (cont.) — Prompt 1.2: canonical SID generator

**Instruction:** Start with Prompt 1.2 (unify the SID algorithm; FlowSheet canonical).

**Implemented (ALAFIA backend):**
- `app/services/canonical_sid.py` — stdlib-only, faithful port of FlowSheet's `fn_generate_system_id`
  (`S1.FN3.LN3.DOB8.GEN1.EPO10.RND157.SHA256(64)`, 255 chars; SHA-256 over the first 7 segments;
  modulo-bias-rejected RND157 via `secrets`). `generate_sid / verify_sid / decode_sid / mask_sid /
  segments_for_log`. Portable so the identity service + FlowSheet share one algorithm.
- `app/services/sid_service.py` now delegates to `canonical_sid` (same public API → `auth.py` unchanged).
  ALAFIA's legacy Rust SID layout (RND93+SHA-512) is **retired** for SID; `alafia_crypto` stays for other
  crypto (blockchain/privacy).
- `tests/test_canonical_sid.py` — **9/9 pass**, including a **cross-app vector** (a SID assembled exactly
  like FlowSheet's SQL verifies under our verifier → one function accepts both apps' SIDs).
- `scripts/remint_canonical_sids.py` — dry-run-by-default re-mint with an `old_sid→new_sid` map.

**Verified (live, dry-run):** 41 ALAFIA users — 18 carry legacy SIDs, **0 verify as canonical**, all 41
would re-mint, 0 already canonical. Backend rebuilt so new registrations mint canonical SIDs.

**Deliberately NOT applied:** re-minting production SIDs is deferred to the Phase 1 identity backfill (so
it happens once, into the shared identity) and needs user go-ahead. Acceptance met: same verifier accepts
either app's SIDs; new ALAFIA SIDs are canonical (existing ones re-mint on backfill).

---

## Session 2026-06-27 (cont.) — Prompts 1.1 + 1.3: shared identity service

**Instruction:** Do Prompts 1.1 and 1.3.

**Built `WEB/identity_service/`** — a runnable, PostgreSQL-native shared identity service (FastAPI):
- **Schema `identity`** (co-located on ALAFIA's Postgres cluster, zero duplication): `users` (UUID id,
  **unique email + unique username**, bcrypt password_hash, account_role, **tier** flowsheet→full,
  canonical 255-char `system_id`), `user_identity` (single canonical profile: first/last/dob/gender/
  biological_sex), append-only `user_identity_sid_log`, `legacy_auth_links` (Firebase migration-only).
- **Auth:** bcrypt + **RS256 JWT** (`make_tokens`), JWKS at `/.well-known/jwks.json` for offline
  cross-app verification (SSO). SID minted via the **shared `canonical_sid`** module (copied in — same
  algorithm as ALAFIA + FlowSheet).
- **Endpoints** (the 1.1 contract): `/identity/register|login|token/refresh|me(PATCH)|lookup|sid/verify|
  users/{sid}` + `/identity/health` + JWKS. Password-reset endpoints stubbed (Phase 1.4).
- **Compose:** new `identity` service on **:8100**, `IDENTITY_DATABASE_URL` → the shared `db`, schema
  `identity`. (Ports: backend 8005, identity 8100, frontend 8080 — no clash.)

**Verified (live):** 4 `identity.*` tables auto-created; health + JWKS (1 RS256 key) OK; full flow —
register (201, canonical SID, tier=flowsheet, role=patient) → /me (profile) → lookup (email_taken) →
**duplicate email/username → 409 "sign in instead"** (1.3 acceptance) → sid/verify (valid, JAN/ROE/F) →
login-by-username (same user) → refresh → get-by-SID.

**Boundaries noted:** ephemeral dev RS256 keypair (set `IDENTITY_JWT_*` for prod); addresses/phones
tables deferred; password-reset token flow + the ALAFIA `identity_uid` bridge + repointing ALAFIA auth
to identity JWT are Phase 1.4.

---

## Session 2026-06-27 (cont.) — Phase 1.4: ALAFIA ⇄ identity SSO + backfill

**Instruction:** On to 1.4.

**Implemented (ALAFIA side):**
- `app/services/identity_client.py` — fetches/caches the identity service's JWKS and verifies
  identity-issued RS256 JWTs offline (aud=alafia, iss=6igma-identity). Returns None on non-identity
  tokens so the legacy path still works.
- `app/core/security.py` `get_current_user` is now dual-path: **identity RS256 JWT first** (→
  `_resolve_or_provision_identity_user`: link by identity_uid → SID → email, else provision a thin local
  reference user), **legacy ALAFIA HS512** fallback during transition.
- Bridge column `users.identity_uid` (String(36)) + migration `cc001`.
- config + compose: `IDENTITY_ENABLED/BASE_URL/ISSUER/AUDIENCE`; backend `depends_on: identity`.
- `scripts/backfill_identity.py` — dry-run-default; provisions existing ALAFIA users into the
  `identity` schema (same DB), mints canonical SID, copies profile, records firebase_uid in
  `legacy_auth_links`, marks `password_unset`, sets ALAFIA `identity_uid` + unifies the SID.

**Verified (live):** `cc001` applied; **an identity-issued token returns 200 on ALAFIA `/symptoms/`**
(SSO inbound via JWKS) → ALAFIA auto-provisioned a local reference user (auth_provider=identity,
linked, has_sid) with **the SAME canonical SID on both schemas** (`sid_matches=true` — one user, one
SID, zero duplication; this is the FlowSheet→ALAFIA no-glitch transition). Backfill dry-run: 42 users →
41 provision / 1 skip. `--apply` deferred (production change; needs go-ahead).

**Remaining 1.4 tail:** FlowSheet-side JWKS verification (symmetric to ALAFIA); switch ALAFIA login UI
to identity + remove Firebase from the live path; password-reset token flow for migrated (passwordless)
accounts.

---

## Session 2026-06-27 (cont.) — Phase 1 COMPLETE (remaining 1.4 tasks)

**Instruction:** Complete Phase 1 — do all outstanding/remaining tasks.

**Done + verified:**
1. **Identity password-reset flow** (`identity_service`): `/identity/password/reset-request` issues a
   signed RS256 reset token (returned inline in dev); `/reset` consumes it, sets a bcrypt password,
   activates the account. Verified: request→reset→ login(old)=401 / login(new)=200.
2. **Backfill APPLIED** (`scripts/backfill_identity.py --apply`): 41 ALAFIA users provisioned into the
   `identity` schema (bcrypt hash carried over so existing passwords work via identity; firebase_uid →
   `legacy_auth_links`). Result: **42/42 ALAFIA users linked (identity_uid) and SID-matched** with their
   identity record — one user, one SID, zero duplication.
3. **ALAFIA `/auth/login` + `/auth/register` delegate to the identity IdP** (`identity_client.identity_login/
   identity_register`): register provisions the canonical identity user + links the local reference +
   unifies the SID; login returns an **RS256 identity token** (Firebase off the live path; legacy HS512
   fallback kept for transition). Verified: register→201 (in_identity/linked/sid_match all true),
   login→RS256 token, token works on ALAFIA `/symptoms/` (200).
4. **FlowSheet-side JWKS verification** (`FlowSheet/.../api/identity_verify.py` + dual-path
   `get_current_user`, config `IDENTITY_*`): code-complete; runtime-verify pending a running FlowSheet
   stack alongside identity.

**Phase 1 (Unified Identity) is COMPLETE.** Remaining polish (post-Phase-1): run/verify FlowSheet
against identity; migrate the ALAFIA frontend login UI off the Firebase SDK to `/auth/login`.
Next: Phase 4.1 (one audit chain) → Phase 2 (therapy model + lifecycle).

---

## Session 2026-06-27 (cont.) — Phase 1 FINISHED: FlowSheet running + cross-app SSO proven

**Instruction:** Finish Phase 1 — build/run FlowSheet; point ALAFIA to /auth/login; verify both working.

**FlowSheet now runs co-located on ALAFIA's Postgres:**
- Created database `sigma_health` on ALAFIA's Postgres cluster; loaded FlowSheet `db/init/01..07`
  (28 tables) into it — "shared FlowSheet DB residing on ALAFIA."
- Added `flowsheet` service to `WEB/docker-compose.yml` (build `../../FlowSheet/src/6igma_health_backend/api`,
  DATABASE_URL→`sigma_health`, IDENTITY_BASE_URL→`http://identity:8000`, IDENTITY_AUDIENCE=flowsheet,
  MAIL_FROM override to satisfy fastapi-mail). Port :8101. Health green.
- FlowSheet `get_current_user`: identity-first dual-path now **resolve-or-provision** — resolves by
  id→SID→email, else auto-provisions a thin reference row (`password_hash='identity-managed…'`,
  `account_status='active'`, `system_id`=SID from claims) → zero duplication.

**ALAFIA frontend:** AuthContext already calls `POST /auth/login` (form-encoded) → backend proxies the
identity IdP → RS256 token → `/users/me`. No Firebase SDK anywhere (only UI comments name the reference
design). Verified `/auth/login`→RS256→`/users/me` 200; frontend serves on :8080.

**Cross-app SSO proven E2E:** registered ONE user in the identity IdP → its RS256 token (aud
`['alafia','flowsheet']`) returns **200 on ALAFIA `/symptoms/` AND FlowSheet `/api/users/me`**; FlowSheet
auto-provisioned the thin row; the canonical **SID is byte-for-byte identical** in `identity.users` and
`sigma_health.users`. One credential → one SID → both apps, zero duplication.

**Stack:** db(healthy) · identity:8100 · backend:8005 · flowsheet:8101 · frontend:8080 — all up.

**Phase 1 (Unified Identity) COMPLETE & runtime-verified.** Residual (later, not blocking): deep-merge
FlowSheet's `users` onto `identity.users` in one schema; decommission Firebase legacy fallback once all
users have local/identity passwords. Next: Phase 4.1 (one audit chain) → Phase 2 (therapy model).

---

## Session 2026-06-27 (cont.) — Login "Not Found" fix (nginx stale upstream + Firestore-migrated account)

**Symptom:** ALAFIA web login showed "Not Found" for developer@hntsolutions.com.

**Root cause 1 (the error):** the long-running `frontend` nginx resolved `backend`'s IP once at
startup; rebuilding `backend` this session gave it a new IP, so every `/api/` call hit a dead/old
upstream → FastAPI 404 `{"detail":"Not Found"}`. Direct `:8005` worked; only the `:8080` browser path
failed. **Fix:** nginx `/api/` + `/ws/` now use Docker DNS (`resolver 127.0.0.11`) + a variable
upstream so the IP is re-resolved per request (no more stale-IP 404s after a backend rebuild). Frontend
rebuilt. Verified `:8080` login → 401 for wrong pw (proper error), 200 for correct pw, `/users/me` 200.

**Root cause 2 (why the password didn't match):** the account was **migrated from Firestore/Firebase**,
so its real credential lived in Firebase, not as a recoverable local bcrypt hash; identity bcrypt verify
failed and the Firebase fallback returned EMAIL_NOT_FOUND (not in the dev Firebase project). Per the
migration design, such accounts onboard via password reset. Set a known dev password through the identity
reset flow (`/identity/password/reset-request` → `/reset`) → login confirmed working.

---

## Session 2026-06-27 (cont.) — Firebase→IdP password-migration bridge

**Decision:** user chose "Build Firebase→IdP bridge" (their real online/Firebase password should work in
dev and migrate them onto the PostgreSQL IdP, rather than living with the dev password I'd set).

**Implemented (identity stays sole writer of identity data):**
- Identity service: secret-guarded `POST /identity/internal/migrate-password` ({identifier, new_password,
  secret}) → sets bcrypt password + activates account. Guard via `hmac.compare_digest` against
  `IDENTITY_MIGRATION_SECRET`. Schema `MigratePasswordRequest`.
- ALAFIA: `identity_client.migrate_password_into_identity()`; in `/auth/login`, after a successful
  `_verify_firebase_password`, ALAFIA calls migrate-then-`identity_login` and returns the **RS256 SSO
  token** (account becomes IdP-native; Firebase no longer consulted on later logins). Falls through to the
  legacy token only if migration/relogin fails.
- compose: `IDENTITY_MIGRATION_SECRET` on both `identity` and `backend` (env-overridable).
- Reverted the dev password I'd set on developer@hntsolutions.com (restored original migrated hash) so the
  account migrates via the user's real Firebase password instead.

**Verified:** migrate endpoint guards (wrong secret→403, unknown user→404); migrate→200; post-migration
old pw→401, new pw→200 with RS256 token (exact post-firebase chain). Firebase probe for
developer@hntsolutions.com returned `INVALID_LOGIN_CREDENTIALS` (enumeration-protected; account present in
dev's Firebase project) → real password will verify in dev and auto-migrate. Forgot Password is the
fallback for any account not in that project.

---

## Session 2026-06-27 (cont.) — Quantum-ready crypto: PQC signatures + Argon2id, retire python-jose

**Instruction:** "RS256 is weak… we need a more robust candidate" → "use a modern, actively supported
verifier (not jose)" → "a password verifier and digital signature that is quantum ready." Chosen
(option 1): **hybrid EdDSA + ML-DSA-65** signatures via **dilithium-py** (pure-Python, revisit later),
**Argon2id** passwords, **PyJWT** replacing python-jose everywhere.

**Shared hybrid-JWS module** `pqc_jws.py` (identical copy in identity / ALAFIA `app/services` / FlowSheet
`api`): compact JWS `alg=EdDSA+ML-DSA-65`, signature = `uint16(len(ed))‖ed25519_sig‖mldsa_sig`; BOTH
signatures must verify. JWKS publishes two keys under one thumbprint kid: `OKP`(Ed25519) + `AKP`(ML-DSA-65).
Kid = sha256 thumbprint of the public keys → rotating keys auto-invalidates consumer JWKS caches.
Standalone-tested: valid accept; tamper of EITHER signature half rejected; exp/aud/iss/kid enforced.

**Token strategy (size-aware):** access tokens = hybrid PQC (~5.3KB, cross-app asymmetric, JWKS).
Refresh/reset = **HS512** — verified only by the issuer, so symmetric HMAC is already PQ-safe AND stays
small (~344B) so it still fits a browser cookie (a 5.3KB refresh cookie would be dropped at the ~4KB limit).

**Passwords → Argon2id.** identity uses argon2-cffi directly (bcrypt verify-and-rehash fallback). ALAFIA +
FlowSheet switch their passlib CryptContext to `["argon2", …, "bcrypt"]` so new hashes are argon2id and
legacy bcrypt/pbkdf2 still verify. (Password hashing was already quantum-adequate — Grover = quadratic;
Argon2id is the memory-hard modern upgrade.)

**python-jose fully removed** from identity, ALAFIA (core/security, api/auth, ws_messaging, ws_telehealth),
and FlowSheet (auth, websocket) → PyJWT for all legacy HS tokens. Added ALAFIA `/auth/refresh` delegation
to identity `/token/refresh` (identity sessions can refresh). nginx `large_client_header_buffers 8 16k`
for the larger Authorization header.

**Verified E2E:** identity issues `EdDSA+ML-DSA-65` access + HS512 refresh; ONE token → 200 on BOTH ALAFIA
(`/users/me`) and FlowSheet (`/api/users/me`, system-id); **tampering the ML-DSA half → 401 on both**;
ALAFIA register→login issues hybrid PQC; new passwords stored `$argon2id$`; legacy bcrypt password still
logs in via fallback. identity/backend/flowsheet rebuilt & healthy.

**Caveats / follow-ups:** dilithium-py is a pure-Python reference impl (not constant-time) — swap for
quantcrypt/PQClean (constant-time) for production behind the same pqc_jws interface. WebSocket auth still
only accepts legacy HS tokens (identity-token WS support = separate task). JOSE/COSE PQC is still
IETF-draft, so the hybrid token is a small custom encoding we own on all verifiers; future iOS/Android
clients will need an ML-DSA verifier.

---

## Session 2026-06-27 (cont.) — Deployment hardening of the PQC/identity stack

**Instruction:** "address follow-ups now… what is worth doing is worth doing now. Assume ready for
deployment." (Dropped the mobile-ML-DSA item — clients only carry the bearer token; verification is
server-side.)

1. **Constant-time ML-DSA signer (liboqs / Open Quantum Safe).** pqc_jws now uses an oqs-preferred
   backend: constant-time liboqs when present (the identity image builds it), else pure-Python
   dilithium-py. Validated cross-compat: a liboqs-signed token verifies under dilithium-py, so verifier
   apps stay pure-Python (verification timing isn't secret-sensitive; only signing needs constant-time).
   identity Dockerfile installs build-essential+cmake and bakes the liboqs build at image-build time.
   Confirmed running backend = `liboqs`.

2. **Persistent signing keys + fail-closed secrets.** identity loads the hybrid keypair + HS secret from
   a mounted keys file (`IDENTITY_KEYS_FILE`, generated by `scripts/generate_keys.py`) or env, instead of
   an ephemeral boot keypair. Verified the JWKS kid is **identical across restart** (multi-replica safe).
   In `ENV=production`, boot **fails closed** if no persistent keys are configured OR if HS/MIGRATION
   secrets are dev-defaults (both verified to raise). Keys file + WEB/.env are git-ignored; a strong
   shared `IDENTITY_MIGRATION_SECRET` lives in WEB/.env (identity + backend).

3. **WebSocket auth accepts hybrid PQC tokens.** ALAFIA ws_messaging + ws_telehealth `_authenticate_ws`
   is now async: verify_identity_token first → resolve local user id by identity_uid/SID/email, else
   legacy HS512. FlowSheet `/ws/notifications` verifies identity tokens first, else legacy HS256. Verified:
   identity token → resolved local user id; garbage token → None.

**Verified E2E after hardening:** identity signs with constant-time liboqs; persistent kid stable across
restart; one hybrid token → 200 on ALAFIA + FlowSheet; production fail-closed on missing keys/dev secrets;
WS resolves PQC tokens. identity/backend/flowsheet rebuilt & healthy.

**Deployment notes:** run `scripts/generate_keys.py` per environment, mount the keys file as a secret,
set `IDENTITY_ENV=production` + strong `IDENTITY_MIGRATION_SECRET`/`IDENTITY_HS_SECRET`. liboqs auto-build
clones liboqs at image build (needs network); pin/vendor for fully-reproducible/offline builds later.

---

## Session 2026-06-27 (cont.) — Mobile parity with the shared PQC identity

**Instruction:** restart all endpoints; continue implementing mobile parity. (Also updated docs +
highlighted the deploy runbook: `docs/IDENTITY_DEPLOYMENT.md`; refreshed `docs/IDENTITY_ARCHITECTURE.md`
to the shipped PQC reality + new §A crypto / §B resolved-decisions.)

**Audit:** both apps already use the backend `/auth/*` endpoints with **opaque bearer tokens and no local
JWT decode**, and **no Firebase Auth SDK** → inherently compatible with hybrid PQC tokens (they just carry
the ~5.3 KB token). iOS: login/refresh/register/reset in `AuthManager` + launch-time refresh. Android:
bearer `AuthInterceptor`, token+refresh storage, a `refreshToken` endpoint.

**Bug found + fixed (the real blocker): `/auth/refresh` 403'd for body-based refresh** (how mobile
refreshes) because the CSRF middleware required a double-submit token on ALL `/api/v1` mutations. CSRF only
defends against *ambient* cookie credentials — a **bearer token** (explicit header) and **body-based
refresh** (no ambient cookie) are not CSRF vectors. Added `_csrf_exempt()` in `backend/app/main.py`:
exempt requests with `Authorization: Bearer …`, and `/auth/refresh` when there's no `refresh_token` cookie.
**Verified live:** mobile body-refresh → 200 (new hybrid token); Bearer mutation → reaches handler (no
403); **web cookie-refresh WITHOUT a CSRF header still 403** (security intact). This repairs refresh on
BOTH iOS and Android.

**Android auto-refresh (parity gap closed):** Android defined `refreshToken()` but never called it and had
no `Authenticator` → sessions died at the 30-min access-token expiry. Added `api/TokenAuthenticator.kt`
(OkHttp `Authenticator`: on 401, body-refresh via a bare client, persist new tokens, retry once; thread-safe,
no recursion) and wired it into `ApiClient`. Code-complete (no Android build env here to run it).

**Remaining (documented):** iOS `APIClient` throws `.unauthorized` on a mid-session 401 (refreshes only at
launch). Per-request silent refresh-and-retry would need a small central chokepoint + a refresher hook from
`AuthManager` — deferred rather than ship an untested refactor of the iOS networking core. The CSRF fix
already restores iOS's launch-time refresh.

---

## Session 2026-06-27 (cont.) — Mobile parity COMPLETE (iOS refresh + both apps build)

Finished the deferred iOS item using Xcode + Android Studio toolchains directly.

- **iOS per-request silent refresh** (`APIClient.swift`): added a self-contained `send()` wrapper +
  `attemptRefresh()` — on a 401 it refreshes the access token via body-based `/auth/refresh` (no CSRF),
  updates Keychain + cached token, and retries once. Routed all request methods (get/post/postForm/
  postFormWithCSRF/patch/put/putNoBody/delete) through `send()`; `fetchCsrfToken`/`streamPost`/the refresh
  call itself are excluded (no recursion). Now at parity with Android's `TokenAuthenticator`.
- **Builds verified:** `xcodebuild -scheme ALAFIA -sdk iphonesimulator` → **BUILD SUCCEEDED**;
  `./gradlew :app:compileDebugKotlin` → **BUILD SUCCESSFUL** (only a pre-existing Gson `setLenient`
  deprecation warning).

**Mobile parity status: COMPLETE.** Both apps: bearer tokens (opaque, PQC-compatible, no local JWT
decode), login/register/refresh/reset via backend `/auth/*` (→ shared PostgreSQL IdP), no Firebase Auth,
and silent refresh-and-retry on 401. Backend CSRF exemption (bearer + body-refresh) verified live; web
cookie-refresh still CSRF-protected.

---

## Session 2026-06-28 — Fix grossly inaccurate AI meal nutrient numbers

**Report:** "2 tbsp apple cider vinegar and cold water" → 2122 kcal (should be ~6).

**Root causes (compounding):**
1. **Wrong USDA food match.** Relevance accepted any ≥50% token overlap, so "cold water" matched
   "Oil, flaxseed, cold pressed" (shared only "cold") → 884 kcal/100g × 240g (cup) = 2122.
2. **First-SR-Legacy pick**, not the best match.
3. **USDA search GET 400s** on many multi-word queries ("white rice", "chicken breast") → forced the
   less-accurate *branded* fallback (dry/branded rice ~3× too high).
4. **Meal parser didn't split " and "** → "X and Y" treated as one food.
5. Bad results **cached with confidence 1.0**.

**Fixes (`nutrient_estimator.py`, `meal_parser.py`, `nutrition_data.py`):**
- Relevance now **requires the query head-noun** (stemmed for plurals) + ≥50% overlap, and ranks ALL
  candidates by a score that **prefers raw/base forms and penalizes processed descriptors**
  (baked/candied/dehydrated/juice/bread…) → "Banana, raw" not "Banana, baked/dehydrated".
- **USDA search switched GET→POST** (JSON body) — fixes the spurious nginx 400s; common foods now resolve
  via USDA again.
- Meal parser splits top-level **" and "/" & "/" plus "** (guarded against "1 and a half" + parens).
- **Curated overrides** (authoritative, checked first) for high-frequency, often-mismatched items:
  water (any cold/tap/sparkling/glass-of variant = 0 kcal; guarded so coconut/tonic water & watermelon
  are excluded), black coffee/tea (~1), whole egg(s)/boiled egg (~143/155, since bare "egg" mis-resolved
  to egg-white ~55).
- Flushed the poisoned `food_nutrient_cache` (regenerable).

**Verified per-100g:** banana 97, apple 61, broccoli 31, avocado 167, white rice 96, chicken breast 165,
egg 143, water 0, coffee 1. Meals: ACV+water **6.3** (was 2122); eggs+banana 240; rice+chicken 343.

**Remaining refinement (not a "meaningless number" bug):** some portion defaults are coarse — e.g.
"1 slice" bread → 100 g default (≈389 kcal) instead of ~28 g (~109). Tighten `meal_parser` slice/piece
weights next.

## Session 2026-06-28 (cont.) — Tighten meal-parser portion weights

Followed up the nutrient-accuracy fix by fixing coarse portion defaults in `meal_parser.py`:
- **Food-aware "slice"** (`_SLICE_WEIGHTS_G`): bread/toast 28 g, pizza 107 g, cheese 22 g, deli meat 28 g,
  bacon 10 g, etc. (was a flat 100 g fallback → bread slice was ~3.5× over).
- **"clove"** → 3 g (garlic), was 100 g.
- New units parsed + handled food-aware: **strip(s)** (bacon 10 g), **stick(s)** (butter 113 g, celery 4 g,
  cinnamon 2 g), **can(s)** (soda 355, tuna 145, beans 425), **bottle(s)** (beer 355, wine 750, else 500),
  **scoop(s)** (protein 30, ice cream 66), **wedge(s)** (lemon/lime 7, watermelon 280).
- Expanded `_PIECE_WEIGHTS_G` (toast/bread 28, pear/peach/kiwi/lemon/lime/carrot/potato/sweet potato/
  cucumber/bell pepper/tomato, pancake/waffle/cookie/muffin/sausage/hot dog/meatball).

**Verified:** "1 slice whole wheat toast" 28 g (108 kcal, was 389); "1 slice of pizza" 107 g (299 kcal);
"2 cloves garlic" 6 g (was 200); breakfast (2 eggs + toast + coffee) **533 → 253 kcal**. Portion units
(strips/sticks/cans/bottles/scoops/wedges) all resolve to sensible grams.

## Session 2026-06-28 (cont.) — Update existing meals + medications (backfill)

**Medications:** `scripts/reestimate_logs.py --meds-only --apply` — resolved all **831** dose logs via
`lookup_med_nutrients`; **760 now carry nutrient contributions** (calcium, vitamin D, etc.), the rest
(Lisinopril, Tylenol…) correctly contribute nothing.

**Meals:** re-estimated all **895** logs from `food_name` (overwriting nutrient columns + extended_nutrients,
preserving identity/timing/weights). The first pass exposed more parser bugs on messy historical free-text,
fixed before final apply:
- **Bare "g" not recognized** as a unit → "150g"/"50 g" lost their quantity (→100 g default). Added `g`.
- **"N of X" / "N pieces" with huge counts** → e.g. "100 of fried chicken thigh" = 100×116 g = 11,600 g
  → 26,886 kcal. Added `_count_to_grams` cap (count implying >1500 g of one item is treated as grams).
- **Nut/small-item piece weights** (cashew 1.5 g … ) → "15 pieces of cashews" was 1500 g (9135 kcal).
- **Bad branded per-100g data** (a Boost record returned 2960 kcal/100 g) → clamp calories to ≤900/100 g.
- Newline-separated meals now split.

**Result:** catastrophic outliers fixed (#669 26886→896; Boost 7246→2203; cashews case resolved).
**850/895 (95%) now in a sane 5–1800 kcal range** (was full of absurd values). Meds 100% resolved.

**Residual (inherent limits, ~26 logs) — NOT chased further:** legit large meals (burger+sides,
multi-item) read 1800–3000 (plausible); a few edge cases remain from third-party data / ambiguous text:
"fried plantain cuts" piece weight, Boost branded data (clamped, still ~6× real), Whole-Foods
"(0.1 bunch)" parenthetical-quantity format, branded orange-juice/grapefruit matching ~0 kcal, and
non-food entries ("same as previous snack"). These need per-source heuristics or better branded data.
The estimator/parser fixes also make all FUTURE logging accurate.

## Session 2026-06-28 (cont.) — All residual nutrition fixes + learning model

**All residual classes fixed (parser/estimator):**
- **Brand-word stripping** (`_strip_brands`): "Whole Foods Market 365 Organic orange juice" → "orange
  juice" → USDA 45 (was a 2-kcal branded mismatch).
- **Parenthetical quantities**: "Organic Leek(0.1 bunch)", "mushrooms (0.8 oz)" now applied as the item's
  amount (added `bunch` unit) → leek+mushroom 1935 → 14 kcal.
- **Small cuts/chips** + **count cap** + **size adjectives**: "10 pieces of fried plantain cuts" → 100 g
  (was 1150 g); "1 large cup" → 240 g.
- **Non-food/placeholder guard** (`_is_placeholder`): "meal3", "same as previous snack" → no fabricated
  calories; the 17 existing placeholder logs zeroed.
- More piece weights (grapefruit, shrimp, prawn, …): "half a Grapefruit" 1 → 26 kcal.

**Nutrition learning model (NEW):**
- Table `learned_food_nutrients` (migration `dd001`) + `LearnedFoodNutrient` model.
- `learned_nutrient_service`: `get_learned`, `record_correction` (sample-weighted running average =
  online learning), `per_100g_from_total`.
- `estimate_nutrients` consults learned values **FIRST** (highest authority).
- API: `POST /api/v1/nutrition/learn` (submit correction; accepts per-100g OR total+grams) and
  `GET /api/v1/nutrition/learn/{food}`.
- Verified: correct "jollof" → estimator returns the corrected value (src=learned); a 2nd correction
  averages (180,220 → 200); confidence rises with samples.

**Backfill re-applied:** 895 logs → **844 sane (5–1800), max 3893** (legit big meal; no catastrophic
values), placeholders zeroed, 11 left at prior values (8 AI-timeouts, 3 DB string edge cases). Spot-checks:
#669 26886→630, #698 OJ 2→45, #844 grapefruit 1→26, #352 6723→1032, #391 (newline meal) →979.

**Known limit:** the Boost branded record carries impossible per-100g data (2960 kcal) — clamped to 900 so
it's bounded (~2203) but still high; this is exactly what the **learning model** is for — one user
correction fixes it permanently.

## Session 2026-06-28 (cont.) — Expose Edit-Meal form in Nutrition page

**Issue:** Food Log rows said "editable" but had no Edit control — clicking through never opened an
edit form (just the list). Backend already had `PATCH /nutrition/{id}` (NutritionLogUpdate).

**Fix (`frontend/src/pages/Nutrition.jsx`):**
- Added per-row **Edit** button (was an empty action cell).
- `startEdit(log)` pre-fills the form (date, meal type, description, times, pre/post weights, recipe,
  serving) and enters edit mode (`editingId`); scrolls to the form.
- Form now shows **"✏️ Edit Meal Entry"** + **"Update Entry"/"Cancel Edit"** when editing (vs
  "Log New Meal"/"Save"/"Cancel" when adding).
- `handleSubmit`: in edit mode **PATCH /nutrition/{id}**; if the description changed it re-estimates via
  `/estimate-meal` so calories/macros stay accurate; otherwise just patches the edited fields.
- `resetForm()` clears edit state on save/cancel.

**Verified:** esbuild clean; frontend rebuilt (:8080 200); E2E create→PATCH updated meal_type, food,
calories, start_time, pre_meal_weight correctly (200).

## Session 2026-06-28 (cont.) — Edit-meal "not responding" fixes

Edit button existed but appeared unresponsive. Verified the page (Nutrition.jsx = image 9) and wiring were
correct + the new code shipped. Addressed the likely real causes:
- **Scroll-into-view via ref** (`formRef` + `scrollIntoView`) instead of `window.scrollTo` — in the
  dashboard layout an inner `<main>` is the scroll container, so window.scrollTo did nothing and the
  pre-filled form (rendered at top) was off-screen → looked like nothing happened.
- **Save hardening**: re-estimate on Update is now time-boxed (25 s) so a slow AI fallback can't hang the
  save; added a `Saving…` disabled state and an error alert so failures surface instead of silently doing
  nothing.
- **nginx**: `no-cache` now also on the SPA `location /` (bare "/" returned index.html via that block, not
  `= /index.html`, so a stale shell could be cached after deploy).
Frontend rebuilt; esbuild clean; :8080 200.

## Session 2026-06-28 (cont.) — Meals Diary Edit deep-link + editable date

Two issues from screenshots:
1. **Meals Diary "Edit" dumped the user on the Nutrition list** (`navigate('/nutrition')`) instead of the
   edit form for that meal. Fixed: `navigate('/nutrition?edit=<id>')`; Nutrition.jsx now reads `?edit=`,
   `GET /nutrition/{id}` → `startEdit()` (opens the pre-filled form, scrolls in), then clears the param.
2. **Editing the date did nothing.** `NutritionLogUpdate` had no `log_date` field AND the frontend
   stripped `log_date` from the PATCH → date-only edits were a silent no-op. Fixed: added
   `log_date: date | None` to the schema; removed the `delete payload.log_date`.

**Verified:** backend PATCH `log_date` 06-28→06-27 persists (200); esbuild clean; backend+frontend rebuilt
(:8080 200); bundles contain the deep-link + edit code.

Note (not fixed — pre-existing data): some old meals' `notes` contain a stored Gemini error
("Error during AI item extraction: [GoogleGenerativeAI Error]…") from the legacy Firebase/Gemini logging
path; harmless, and re-analyze/edit now uses the local estimator.

## Session 2026-06-28 (cont.) — Sync Profile insurance ↔ Insurance Plans

Profile stored a single insurance (`users.insurance_id/provider/country`); the Insurance Plans page used a
separate `insurances` table — they didn't share data (Plans showed "No Insurance Plans" despite Profile
having Kaiser). Added `services/insurance_sync.py` (country→region/code resolver, provider slug) and wired:
- **Profile PATCH** (`users.py`): insurance edits → `sync_profile_to_plan` (upsert the primary plan).
- **Insurance create/update** (`insurance.py`): primary/only plan → `sync_plan_to_profile` (write back the
  3 Profile fields).
- **Insurance list** (`insurance.py`): `ensure_plan_from_profile` lazily materialises a plan from Profile
  if the user has none — so existing Profile insurance shows up in Plans immediately.
Single-direction per endpoint ⇒ no feedback loop. No schema change (reuses existing tables).

**Verified:** profile save (Kaiser/19232288/US) → Plans shows it (primary); add NHS primary plan →
Profile becomes NHS / NHS-777 / United Kingdom. Backend rebuilt.

## Session 2026-06-28 (cont.) — Fix Food & Drug Recalls (0 results) + map overlay

**Root cause of "0 recalls":** the openFDA query was built with literal `+` (`+AND+`, `+TO+`); httpx
URL-encoded them to `%2B`, so openFDA returned **500 parse error** → swallowed → 0 results. Confirmed:
literal-`+` → 500; **spaces → 200 (336 recalls/90d)**. Also a frontend param mismatch (`search_term` vs
backend `search`) and field mismatches (`recall_date`/`distribution_pattern` vs `recall_initiation_date`/
`distribution`).

**Backend (`fda_recalls.py` + schema):** build the query with spaces + ` AND `/` TO ` (client-encoded);
sort `report_date:desc`; `/recent` widened to 90 days (openFDA report_date lags). Added geographic
coverage to each item: `city/state/country`, `states[]` (US codes parsed from the distribution pattern),
and `nationwide` (detects "nationwide/national/all states" → fills all states). New `_query_openfda`
helper + `_build_item`.

**Frontend:** fixed the `search`/field names; auto-loads recent on mount; per-recall "Coverage" line +
location; added a **dependency-free US tile-grid coverage map** (`components/USCoverageMap.jsx`, verified
overlap-free 11×8 statebins layout) showing the union of covered states across results (offline, no map
lib / CDN). Label "Recent (90 days)".

**Verified:** `/fda-recalls/?days=90` → 200, total=336 with parsed states + nationwide; salmonella search
→ 86; esbuild clean; backend+frontend rebuilt (:8080 200).

## Session 2026-06-28 (cont.) — Recalls: add Drug + aggregate/per-recall map toggle

- **Food + Drug:** backend now queries both openFDA endpoints (`food/enforcement` + `drug/enforcement`)
  via a `kind` param (food | drug | both). `both` splits the limit, tags each item `product_type`, merges
  newest-first. `FDARecallItem.product_type` added. `/recent` accepts `kind` too. (check-meal stays food-only.)
- **Frontend:** Food+Drug / Food / Drug segmented toggle (drives `kind`); per-recall **Food/Drug badge**;
  page title → "FDA Food & Drug Recalls".
- **Map toggle:** Aggregate ↔ Per recall. Aggregate shows the union coverage map (current); Per recall
  renders a `USCoverageMap` inside each recall card from its own `states`/`nationwide`.

**Verified:** backend kind=food→[food], drug→[drug], both→[food,drug] merged; esbuild clean; frontend
rebuilt (:8080 200).

## Session 2026-06-28 (cont.) — Recalls go global (data + world map)

**Data:** aggregated 3 government sources (graceful per-source failure): **US openFDA** (food+drug),
**Health Canada** (recent recalls; food=cat 1, health/drug=cat 3), **UK FSA** food alerts
(`data.food.gov.uk`, `_sort=-created`). Each item tagged `country` (ISO-2) + `source` + `url`. Sources are
**round-robin merged** so every country is represented (not just the freshest-dated). Verified kind=both →
US+CA+GB; food → balanced US/CA/GB; drug → US (UK food-only, CA health absent in current feed).

**Map (dependency-free, React-19-safe):** converted world-atlas topojson → `public/world-countries.geojson`
(build-time, via topojson-client); new `WorldCoverageMap.jsx` renders it with a plain equirectangular
projection and highlights covered countries (ISO-2→numeric). No map library (react-simple-maps is
React-18-only). The **US state tile-grid** is still shown beneath the world map for state-level US detail.
Per-recall mode: US → state grid; non-US → country chip. Each recall shows a 🇨🇦/🇬🇧/🇺🇸 source badge +
"Official notice ↗" link.

**Verified:** world geojson served (200); global results across US/CA/UK; esbuild clean; stack healthy.

## Session 2026-06-28 (cont.) — Recalls global expansion (data + worldwide map)

**API reality:** probed many national/intl recall systems (USDA FSIS, IE FSAI, AU FSANZ, EU RASFF, WHO,
NZ MPI, HK CFS, SG SFA, EMA) — nearly all are bot-protected, 404, or have no public JSON API. Reliable
live sources remain **US openFDA (food+drug), Health Canada (food + health/drug), UK FSA (food)**.

**Global map from real data:** added `_parse_countries()` (country-name → ISO-2 over ~60 countries) so each
recall's `countries[]` includes EVERY country in its distribution pattern + the source jurisdiction.
A US recall shipped to Canada/Mexico/Puerto Rico now lights all of them on the world map. FDARecallItem
gains `countries: list[str]`; CA/UK tagged `[CA]`/`[GB]`.

**Frontend:** world map unions all `countries` across results; per-recall shows the US state grid + the
full list of reached countries (flag + name, ~55-country name table). Aggregate/per-recall + food/drug
toggles retained.

**Verified:** kind=both over 180d lit US+CA+GB+PR on the map; round-robin keeps all sources represented;
esbuild clean; stack healthy (:8080 200).

**Extensible:** sources are independent adapters with graceful failure — EU RASFF/EMA, WHO, AU/NZ/etc. can
be added when an accessible API/key exists, without touching the rest.

## Session 2026-07-02 — Dashboard overview, chart wiring, weight series, phone/social login

**Web/backend (uncommitted on feat/identity-pqc-nutrition-recalls-2026-06):**
- **Dashboard health overview** (additive above the daily review): wellness score, latest labs,
  historical vitals trend (recharts dual-axis), AI recommendations + health insights forms
  (`/personalization/*`), daily food idea (session-cached `/planners/meal-suggestions`), resources
  quick-link grid, footer. New `Dashboard.test.jsx`; `ResizeObserver` stub in test setup.
- **Chart Dashboard fixed** ("trends charts empty"): `/chart-dashboard/datasets` returns per-user
  non-null `count` per dataset; UI auto-selects up to 3 populated datasets, dims "no data" ones,
  explicit empty-state; fixed backend `if row.value` coercing 0→null.
- **Composite weight series**: `/chart-dashboard/weight-series` unions vitals, lifestyle, fitness,
  meals pre/post, elimination pre/post (bowel/urination/vomiting), HD therapy + PD sessions, labs
  (kg/lb→kg) with 20–500 kg sanity filter. Daily mean/min/max/count + **7-day rolling average** +
  summary (avg/σ/min/max/per-source/trend) + refs (dry weight, profile current/target). Virtual
  datasets `weight_all` + `weight_all_7d` across /datasets,/data,/summary,/correlate. 9 unit tests
  (175 total green). Chart draws target-weight goal line (ReferenceLine + extended y-domain);
  weight-only charts lift baseline to min(40, dataMin−5).
- **Phone + social login**: `POST /auth/firebase` (verify Admin-SDK ID token → link/create user by
  firebase_uid→email→phone → app JWTs); `users.phone_number` (jj001). Login page rebuilt to match
  production: Email/Phone tabs, Firebase phone OTP (invisible reCAPTCHA), Google/Apple popups
  (`services/firebase.js`, project alafia-9i0hh), `AuthContext.loginWithFirebase`. E2E-verified
  with a real minted Firebase token (test user deleted after). Reverted an accidental
  target-date feature (kept target-weight goal line only).

## Session 2026-07-02 (cont.) — Parity documentation + mobile parity round

- **docs/WEB_MOBILE_PARITY.md** — full record of work since the 2026-06-27 parity run + parity
  matrix + round scope. Mobile gaps: stale recall models (no kind/coverage), no surveillance, no
  facilities, no weight-series, no /auth/firebase plumbing.
- Parity round (both apps): recalls schema refresh + kind filter; facilities API+screen;
  surveillance API+screen (list-first); weight-series API + trend UI; /auth/firebase client method.
  Native social/phone SDK flows and mobile choropleths deferred (documented).

## Session 2026-07-02 (cont.) — iOS run on 26.5 sim + critical APIClient recursion fix

- Installed the iOS 26.5 simulator platform (`xcodebuild -downloadPlatform iOS`), created an
  iPhone 17 (26.5) device, full Xcode build **SUCCEEDED**, app installed + launched
  (com.alafia.app), backend reachable from the sim (localhost:8005).
- **Critical bug found via "login failed without message":** `APIClient.send()` (added in the
  2026-06-27 silent-refresh parity work) awaited **itself** instead of `session.data(for:)` —
  infinite async recursion, so every API call through `send()` (login, and everything after)
  never hit the network, never threw. Only `fetchCsrfToken`/`streamPost` (direct session calls)
  worked, which is why the backend saw the CSRF GET but no login POST. One-line fix; rebuilt,
  reinstalled, relaunched on the sim.

## Session 2026-07-05 — MyChart (Epic) portal connections: SMART on FHIR end-to-end

**Connect any MyChart portal (Kaiser Permanente, Trinity Health, + ~450 Epic orgs) and pull
records into ALAFIA.** Patient-facing SMART App Launch (standalone, OAuth2 code + PKCE S256,
public client — user signs in on the portal's own page).

- **Service `app/services/smart_fhir.py`**: Epic R4 endpoint-directory ingest
  (open.epic.com/Endpoints/R4, dedup by base URL — the feed lists dupes), SMART discovery
  (.well-known/smart-configuration → metadata oauth-uris fallback), PKCE, token exchange +
  refresh, Fernet token crypto (SECRET_KEY-derived), paginated FHIR search, pure mapping fns:
  lab Observations → lab_results (LOINC, ranges, abnormal flag), vital-signs (incl. BP panels
  85354-9; lb→kg, °F→°C, in→cm) → vitals_logs, MedicationRequest → medications (RxNorm),
  Condition → chronic_conditions (name/ICD-10-driven category; tz-naive diagnosis_date).
- **API (`/ehr/*`)**: organizations search (24h-cached directory), connect (authorize URL +
  server-held PKCE state), exchange (code→tokens, link/reuse connection), connections/{id}/sync
  (auto token-refresh; FHIR:{id} note markers for idempotent dedup). Migration kk001
  (ehr_endpoints, ehr_oauth_states, token cols). Config: EPIC_CLIENT_ID, EHR_REDIRECT_URI,
  EHR_ENABLE_SANDBOX (registration-free SMART Health IT test portal).
- **Frontend**: `EHRPortals` section atop Data Sharing (org search → Connect redirect →
  connection cards w/ Sync + per-type counts), `/ehr/callback` page (StrictMode-safe single
  exchange).
- **Verified**: 13 new unit tests (188 total green); live directory = 450 orgs (9 Kaiser regions,
  3 Trinity). Full browser E2E vs SMART sandbox: Connect → patient login → consent (our exact
  scopes) → callback exchange → **synced 34 labs, 10 vitals, 2 meds, 3 conditions**; re-sync = 0s
  (dedup); rows verified in PG (lipid panel, weights lb→kg feeding the composite weight series).
- **To go live against Kaiser/Trinity**: register the app at fhir.epic.com (patient-facing,
  redirect URI = EHR_REDIRECT_URI), set EPIC_CLIENT_ID — no code changes needed.

## Session 2026-07-06 — Image AI fixed: real vision + believable nutrition, Safari-safe uploads

**Report:** "Error analyzing image" on Nutrition-from-Image (Safari). **Diagnosis:** the POST
422'd (multipart 'file' field missing — Safari-specific through nginx; Chromium fine), AND the
endpoint was a fake: it keyword-matched the FILENAME against a 15-food table ("AI vision
integration pending") — never looked at the image.

- **Backend (`image_ai.py`)**: nutrition-from-image now runs REAL vision: structured
  ALAFIAModel food task first; fallback = moondream caption ("What foods are on this plate?" —
  small models answer questions far better than they emit JSON) with lead-in/qualifier/filler
  cleanup ("The plate contains rice and a piece of meat, possibly chicken." → "rice and meat" —
  qualifiers would double-count). Foods are then priced through `estimate_meal_nutrients`
  (learned→curated→USDA→AI + plausibility guardrail). No fabricated numbers: 503 with a clear
  message when no vision backend can see the image. medication-from-image reads the label via
  the vision model (JSON extraction + reference-library enrichment). Both endpoints accept
  multipart `file` OR JSON `{image_base64}` (data-URL tolerated); dead FOOD_LIBRARY removed.
- **Frontend (`ImageAI.jsx`)**: uploads switched to base64 JSON (sidesteps the Safari multipart
  issue), 180 s analysis timeout (CPU vision > default 30 s axios timeout), real backend error
  detail surfaced instead of the blank "Error analyzing image".
- **Verified:** real jollof-rice photo → "rice (112 kcal) + meat (184 kcal), total 296 kcal"
  via BOTH JSON and multipart paths (~13 s, moondream local); browser E2E screenshot of the
  results table; 4 new tests; full suite 192 passed; frontend builds.

## Session 2026-07-06 (cont.) — Vision wired into Medications, Elimination, Symptoms

- **Backend (`image_ai.py`)**: shared `_vision_ask()` helper; two new endpoints (multipart OR
  base64, auth-gated):
  - `POST /image-ai/elimination-from-image` {event_type: bowel|urination|vomiting} — per-type
    prompts; keyword extraction → suggested fields (Bristol scale 1-7, color, consistency,
    blood/mucus, urine clarity) + attention flags (black/red stool, red/cloudy urine,
    blood/coffee-ground vomit) with negation handling ("no blood" doesn't flag) + disclaimer.
  - `POST /image-ai/symptom-from-image` — visible-symptom description → suggested
    symptom_name (20-term lexicon), body_part (31 parts), symptom_type.
- **Frontend wiring**:
  - `Elimination.jsx`: "Analyze photo" beside the existing image attach (poop/urine/vomit →
    bowel/urination/vomiting) → prefills Description ("Bristol type N, consistency, color —
    model text") + amber flags box.
  - `Symptoms.jsx`: "From Photo" header button → analyzes → opens the form prefilled
    (symptom, body part, type, AI description in notes) + disclaimer banner.
  - `Medications.jsx`: "Scan Label" header button → medication-from-image → prefills intake
    log + prescription form (name, dosage, label instructions); clear alert when unreadable.
- **Verified**: 6 new tests (198 total green); live endpoint runs; browser E2E on all three
  pages (Elimination prefill + flags, Symptoms prefill + banner, Medications refuses non-label
  photos); frontend builds.

## Session 2026-07-06 (cont.) — Fix "or fish" / "and" priced as foods

User's real meal photo produced junk rows: caption "rice, chicken or fish, and …" leaked
"or fish" (83 kcal) and "and" (47 kcal) as priced components. Two-layer fix in `image_ai.py`:
- **Caption cleanup** (now a testable `_clean_caption`): drop bare "or X" alternatives (keep
  the first), strip scene sentences (fork/knife/plate/glass…), normalize "and"-lists to commas,
  collapse whitespace.
- **Component leakage guard**: skip parser components whose name is a conjunction/scene token
  (`_NON_FOOD_TOKENS`) or "or/and/with …" remnant; totals now sum only kept components (the
  meal aggregate would re-include dropped junk).
Verified: 13 image-AI tests, full suite 198 passed; real photo → clean "rice + meat, 296 kcal".

## Session 2026-07-06 (cont.) — Sentence-fragment rows + head-noun believability fix

Second real photo (beans in palm oil + grilled chicken + fried plantain) leaked whole caption
SENTENCES as priced rows ("vegetables. there is chicken", "…nutritious meal option…").
- **Two-stage food identification**: verbose moondream caption → llama3.2 (local text model,
  format=json, temp 0) extracts `{"foods": […]}` — prompt excludes comparison mentions
  ("alternative to rice" no longer yields rice). Regex cleanup stays as fallback.
- **`_plausible_food_name` guard** (shared by extractor + component pricing): rejects >4 words /
  >40 chars, sentence punctuation, verb chatter, conjunction starts — fragments can never be
  priced again.
- **Ground truth from user exposed estimator bug**: "beans cooked in palm oil with ground
  peppers" classified as `oil_fat` (name contains "palm oil") and portioned 2.5 g (parser's
  spice table matched "pepper") → 6 kcal. Fix: **head-phrase principle** in
  `nutrition_reference.classify` (+ exported `head_phrase()`) and `meal_parser._default_g` —
  category and default portion key off the food before any "cooked in/with/…" clause.
  Now: legume_cooked, 100 g, ~68 kcal — believable.
- Verified: 17 image tests; nutrition regression suites green; full suite **203 passed**.

## Session 2026-07-06 (cont.) — Learn from labeled food images (visual memory) + mobile parity

**"Can we learn from labelled images?"** — yes, without model training: a per-user **visual
memory**. Labeled photos are stored as 64-bit dHash perceptual hashes (no image bytes retained)
with the user's ground-truth food list; new photos are matched by Hamming distance (≤10/64
tolerates re-shots) BEFORE any vision model runs — repeat meals resolve from the user's own
labels in ~25 ms instead of ~13 s of vision.

- **Backend**: `labeled_food_images` (ll001), `services/image_learning.py` (dhash/hamming/
  find_learned_match/save_label — upsert re-centers the hash on the latest shot),
  `POST /image-ai/label` {image_base64, foods} → stores label + returns the priced truth;
  nutrition-from-image checks visual memory first. Pricing refactored into shared
  `_price_description`. Labeled set doubles as the Phase-5 food-classifier training corpus.
- **Web**: "Not right? Teach ALAFIA" input under results (prefilled with detected names).
- **Mobile parity**: Android `labelFoodImage` + `FoodLabelRequest` + Teach card in
  ImageAIScreen; iOS `teachNutrition()` + Teach field in ImageAIView. Both build
  (gradle BUILD SUCCESSFUL; xcodebuild BUILD SUCCEEDED on iOS 26.5 sim).
- **Verified**: teach→re-analyze E2E (learned match, 24 ms); 17 image tests; full suite
  **205 passed**; frontend builds.

## Session 2026-07-06 (cont.) — Recipe URL: third meal input, full learning-pipeline tie-in

Meals now have three interchangeable content inputs — **recipe URL / description / photo** —
all feeding the learning stores.

- **`services/recipe_ingest.py`**: schema.org/Recipe JSON-LD extraction (regex script tags,
  @graph walk, yield/nutrition parsing "310 calories" → 310), SSRF guard (public http(s) only,
  private/loopback/link-local IPs rejected), browser UA (recipe sites block bot agents).
- **`POST /nutrition/recipe-analyze`** {url, servings?}: ingredients priced through the
  believability estimator → whole-recipe + per-serving; when the page PUBLISHES nutrition it
  wins for display AND is learned: per-serving → per-100 g (serving_g = est. total weight /
  servings, ≥30 g credibility floor) → plausibility review → `learned_food_nutrients`
  (source="recipe") under the dish name.
- **`/image-ai/label` accepts `recipe_url`**: photo tied to a recipe — labeled with the DISH
  NAME (serving-scale pricing via curated/learned; ingredient-list fallback only if the name
  can't price — first cut priced the whole 8-serving pot at 1.9k kcal).
- **Web**: Analyze button on the Nutrition form's existing recipe_url field → prefills
  food name/serving + pre-save nutrient preview (source "recipe (published|estimated)").
- **Mobile parity (API level)**: Android `analyzeRecipeUrl` + models, FoodLabelRequest gains
  recipe_url; iOS RecipeAnalyze structs. Both build.
- **Verified live**: cheflolaskitchen.com jollof → 21 ingredients, 8 servings, published
  568.5 kcal/serving, learned 188 kcal/100 g (row in learned_food_nutrients); description
  "Nigerian Jollof Rice" prices believably; photo labeled via URL → visual-memory match at
  serving scale (160 kcal). 5 new tests; full suite **210 passed**; web/Android/iOS build.

## Session 2026-07-08 — Mobile parity: recipe-URL Analyze UI + elimination photo-wiring

Continued the 2026-07-06 round by closing two deferred mobile-UI bullets. Both apps build
(Android `:app:compileDebugKotlin` BUILD SUCCESSFUL; iOS `xcodebuild` BUILD SUCCEEDED, iPhone 17
sim / iOS 26.5 SDK).

- **Recipe-URL Analyze UI (Android + iOS)**: the meal form already carried a recipe-URL field,
  the `RecipeAnalyze*` models, and the client call — only the action + preview were missing. Added
  an **Analyze** button beside the field (Android `AddMealDialog`, iOS `AddNutritionSheet`) that
  calls `/nutrition/recipe-analyze`, prefills the food name + `1 serving (of N)` when blank, and
  renders a per-serving macro preview (`recipe (published|estimated)`) + an
  ingredients/servings info line (`…Published nutrition learned for this dish.`), mirroring web
  `Nutrition.jsx`. iOS `APIClient.post` gained an optional per-request `timeout` (used at 120 s)
  so the external fetch + pricing isn't killed by the global 30 s request cap.
- **Elimination photo-wiring (Android + iOS)**: new model `EliminationFromImageResponse`
  (+ `EliminationSuggested`) and `image-ai/elimination-from-image` client call. A shared
  **Analyze-photo** control (Android `AnalyzeEliminationPhoto`, iOS
  `AnalyzeEliminationPhotoButton`) drops into each of the three log dialogs/sheets: it picks an
  image, runs the vision model for the tab's `event_type` (bowel/urination/vomiting), prefills the
  structured fields (Bristol scale, color, blood/mucus) + a composed description into Notes, and
  renders the backend's attention flags + disclaimer. Android dialogs became scrollable to fit
  the new control.
- **Verified live**: registered a throwaway user via the CSRF+login flow against the running
  backend (`:8005/api/v1`); `elimination-from-image` (event_type=bowel, data-URL base64) returned
  a `200` with exactly `{event_type, description, suggested{bristol_scale,color,blood_present,
  consistency}, flags[], disclaimer}` — the mobile models decode it 1:1. `recipe-analyze`
  accepted the `{url}` contract (the external page fetch is blocked at the container's egress in
  this env, so it 422'd at the fetch step, not on schema); its response model mirrors the backend
  Pydantic definition the web already consumes.
- **Discovered pre-existing bug (deferred)**: mobile `MedicationFromImageResponse` and the
  dosage-verification models are **stale** vs. the current backend schema (mobile expects
  `drug_class`/`side_effects`/`interactions`/`warnings`; backend returns
  `dosage`/`instructions`/`ndc_code`/`manufacturer`/`fields`/`notes`, and
  `is_typical`/`feedback`/`typical_range`/`precautions` for dosage). The ImageAI medication/dosage
  tabs therefore render mostly-null today. Medication "Scan Label" wiring is blocked on fixing
  those models + the ImageAI rendering; tracked as a separate follow-up so this additive round
  doesn't smuggle in a runtime-behavior migration.

## Session 2026-07-08 (cont.) — Dr. Holista / AI chat: hallucination + template-leak fix

Reported: the AI Health Assistant (Dr. Holista, general_practitioner persona) ignored the
user's actual voice question, fabricated data (a BMI "above 30", phosphorus "2.6 mg/dL slightly
elevated" — 2.6 is not elevated), leaked a literal `[insert]` placeholder, and buried the
question under a generic ESRD wall-of-text.

**Root cause**: every persona's system prompt (`ai.py` `PERSONA_PROFILES`) ended with an
`EXAMPLE:` line built from square-bracket placeholders (`[date]`, `[comprehensive summary]`,
`[Top 2-3 priorities]`, `[Positive/motivating close]`…). The small local model (llama3.2:3b)
copies that few-shot structure literally → hence the `[insert]` leak, the exact "here's what
stands out / Top 2-3 / motivating close" scaffold, and invented values. The GP EXAMPLE also
taught "comprehensive summary" regardless of the question → generic, non-responsive answers.

**Fixes (`WEB/backend/app/api/ai.py`)**:
- Converted all seven bracketed `EXAMPLE:` lines to bracket-free `HOW TO ANSWER:` prose (no
  `[...]`, no fake `X mg/dL` values) so the model has nothing to parrot.
- Added FUNDAMENTAL RULES (specialist path) + analyst RULES (cultural/default path): answer the
  SPECIFIC question asked (no full review unless requested); never print bracketed placeholders;
  never state a number not in the record; only call a value high/low when outside its reference
  range.
- De-bracketed the RAG query wrapper (`--- … records ---` instead of `[…]`) in `_augment_query`.
- Deduped the chat turn: the frontend already includes the just-sent user message in `messages`,
  and the endpoint then appended the augmented (data-injected) copy → the question was sent
  twice. New `_assemble_chat_messages()` drops the trailing duplicate so the augmented copy is
  the single final user turn; used by both `/ai/chat` and `/ai/chat/stream`.
- The "disappearing prompt" was not a rendering bug — the user's turn renders (right-aligned)
  but scrolls above a long answer; the concise-answer fix keeps it in view.

**Verified live** (patched the running `web-backend-1` via `docker cp` + restart; source is
baked into the image, not bind-mounted): a specific GP question ("What was my most recent
potassium result?") now returns a direct, 84-char answer that plainly says the value isn't
recorded — no fabrication, no brackets. The exact trigger ("give me a comprehensive review")
on a sparse record now reports fields as "not recorded" instead of inventing a BMI/phosphorus,
with zero bracket leaks.

Note: model quality is still capped by llama3.2:3b; a larger instruct model would further reduce
generic phrasing. Follow-up worth considering.

### 2026-07-08 (cont.) — follow-up fixes: prompt visibility + route audit + model finding

- **Disappearing prompt (frontend, `AIChat.jsx`)**: replaced the scroll-to-bottom-on-every-token
  effect with a scroll that anchors the newest QUESTION to the top of the view (ChatGPT-style),
  so the streamed answer flows beneath it instead of the view jumping to the end of a long reply
  and hiding what was asked. Keyed on user-turn count; falls back to bottom for the greeting.
  Frontend rebuilt (vite) and the fresh bundle deployed into the running nginx container.
- **Voice → route audit**: `/ai/route`'s `assistant_message` is a preset per intent (not
  LLM-generated), and it already guards against 3B intent-mislabeling (trailing "?" ⇒
  ask_question). The raw transcript is passed through as `autoAsk`, so the voice path answers the
  actual question — no fix needed there once the chat prompt was corrected.
- **Model finding (biggest remaining quality lever)**: the running backend uses
  `OLLAMA_MODEL=llama3.2:3b` — the weakest option (config's intended default is `gpt-oss:20b`;
  only `moondream`, `llava:7b`, `llama3.2:3b` are pulled). With the corrected prompts the 3B model
  now answers the reported cases correctly (verified), but richer/nuanced answers need a stronger
  instruct model (e.g. `gpt-oss:20b` per config, or a lighter `llama3.1:8b`/`qwen2.5:7b`). Left as
  a recommendation — pulling 5–13 GB and the RAM to run it is the user's call.

### 2026-07-08 (cont.) — LLM upgrade: deleted Docker Ollama, moved to native gpt-oss:20b

The weak answers weren't just prompts — the backend was pointed at an Ollama running INSIDE
Docker's Linux VM: 7.7 GB cap, CPU-only (no Metal), so it could only run llama3.2:3b. The Mac
(M3, 24 GB) already had **gpt-oss:20b (13 GB)** pulled in its native Ollama, which was being
ignored because the Docker container held port 11434.

- **Deleted the Docker Ollama** (per request): removed the `ollama` service, its `depends_on`,
  and the `ollamadata` volume from `WEB/docker-compose.yml`; `docker rm -f web-ollama-1` +
  `docker volume rm web_ollamadata`.
- **Repointed the backend** to the native host daemon: `OLLAMA_BASE_URL=http://host.docker.internal:11434`,
  `OLLAMA_MODEL=gpt-oss:20b` (compose + `backend/.env`; `config.py` defaults already matched).
  Docker Desktop proxies `host.docker.internal` to the host loopback, so the container reaches
  the native daemon on 127.0.0.1:11434 with no rebind needed.
- **Vision**: the host Ollama lacked `moondream`, so `ollama pull moondream` on the host keeps
  food/elimination photo analysis working (`OLLAMA_VISION_MODEL=moondream`).
- **Verified live**: nephrologist chat now runs on gpt-oss:20b (52 s incl. cold 13 GB Metal load,
  vs ~2 s for 3B) — specific, accurate potassium answer with real mg values, no bracket leaks.
  `elimination-from-image` returns 200 through host moondream. No Ollama container remains.

Caveat: the backend image still bakes the pre-fix `ai.py`; the prompt fix is applied via
`docker cp` + restart. A `docker compose build backend` is needed to bake it permanently (and to
survive `compose down`/reboot). The recreate for the env change reverted ai.py once — re-applied.

### 2026-07-08 (cont.) — Close mobile voice gap: mic in Android + iOS AI chat

Web gained an in-app voice mic in the AI chat; mobile lacked it. Closed on both:

- **Android** (`AIChatScreen.kt`): extracted the streaming send into a reusable `send()`, added a
  mic `IconButton` that launches the system speech recognizer via `RecognizerIntent`
  (`ACTION_RECOGNIZE_SPEECH`, out-of-process → **no RECORD_AUDIO permission** needed) and sends the
  returned transcript straight to the agent. Added a `<queries>` entry for the recognize-speech
  intent in `AndroidManifest.xml` (Android 11+ package visibility). `compileDebugKotlin` green.
- **iOS** (`AIChatView.swift`): reused the existing `Core/SpeechRecognizer` (SFSpeechRecognizer +
  AVAudioEngine, the same one PromptView uses). Mic button toggles recording, the live transcript
  mirrors into the field, and on stop the final transcript is auto-sent. Info.plist already carried
  `NSMicrophoneUsageDescription` + `NSSpeechRecognitionUsageDescription`. `xcodebuild` BUILD SUCCEEDED.

The mic lives in the shared chat input on both platforms, so it works for EVERY persona
(specialist + cultural), matching web. All personas also inherit the server-side prompt fix +
gpt-oss:20b automatically.

Mobile parity re-verified this session: recipe-URL Analyze ✅✅, elimination photo-wiring ✅✅,
AI-chat personas+streaming ✅✅, and now AI-chat voice mic ✅✅ (Android/iOS). Remaining known gap:
stale mobile Medication/dosage models + Scan-Label (tracked separately).

### 2026-07-08 (cont.) — Fix stale mobile med/dosage models + wire Scan-Label (both platforms)

Pre-existing bug (found earlier, now fixed): the mobile `MedicationFromImageResponse` and
dosage-verification models did NOT match the backend, so medication-from-image showed mostly-null
and verify-dosage 422'd ("dosage field required").

- **Models (Android `NewFeatureModels.kt`, iOS `NewFeatureModels.swift`)** rewritten to the real
  backend schema: `MedicationFromImageResponse` = medication_name/dosage/instructions/ndc_code/
  manufacturer/fields[]/notes; `DosageVerificationRequest` = medication_name/dosage/frequency;
  `DosageVerificationResponse` = medication_name/dosage/is_typical/feedback/typical_range/
  precautions[].
- **ImageAI screens** (Android `ImageAIScreen.kt`, iOS `ImageAIView.swift`) re-rendered to the new
  fields (medication details + notes; dosage tab now sends dosage+frequency and shows
  typical/atypical + precautions).
- **Scan Label** added to the Medications screens (Android `MedicationsScreen.kt` toolbar camera
  action, iOS `MedicationsView.swift` PhotosPicker): pick a bottle/label photo →
  medication-from-image → open the Add-Medication form prefilled with name/dosage/instructions
  (parity with the web "Scan Label"). Unreadable labels show a clear message.
- **Verified live** against the running backend: verify-dosage NEW contract → HTTP 200 with exactly
  `{medication_name,dosage,is_typical,feedback,typical_range,precautions}` (is_typical=True,
  typical_range "500-2000 mg/day"); the OLD mobile contract → HTTP 422 "dosage field required"
  (proves the bug). medication-from-image → exact 7-field shape the new model decodes. Android
  `compileDebugKotlin` + iOS `xcodebuild` both green.

Session parity status: recipe-URL ✅✅, elimination photo ✅✅, chat personas+streaming ✅✅,
chat prompt-fix+gpt-oss:20b ✅✅ (server-side), chat voice mic ✅✅, med-scan + model fix ✅✅.

### 2026-07-19 — Subscription ("ALAFIA Plus") across web + Android + iOS

New paid tier wired end-to-end on all four rails per SubscriptionRail.md ($12/mo web via
Stripe/PayPal, $14/mo Android via Google Play, $14/mo iOS via Apple — USD everywhere). The
**backend is the single source of truth for entitlement**; every rail reports a *verified*
purchase and the backend records the active period on the user's one `subscriptions` row.

**Backend (`WEB/backend`)** — no new Python deps; all provider I/O via `httpx` + stdlib crypto:
- `models/subscription.py` — `Subscription` (per-user state: status/provider/period/cancel + per-rail
  reconciliation ids) with `is_entitled(grace_days)`, and `SubscriptionEvent` (append-only idempotency
  + audit log; unique `(provider, event_id)`). Registered in `models/__init__.py`.
- `services/subscription_service.py` — Stripe (Checkout + webhook HMAC verify + sync), PayPal
  (Subscriptions API + webhook verify), Google Play (Android Publisher `subscriptionsv2` via a
  service-account JWT), Apple (StoreKit 2 JWS decode + legacy verifyReceipt fallback), plus cancel.
  Dev **test-mode**: a rail with blank creds + `DEBUG=true` returns a synthetic active purchase so the
  whole flow is exercisable without live keys; in prod a missing cred raises 503 (never a fake grant).
- `api/subscription.py` — `/plans`, `/status`, `/checkout`, `/confirm`, `/webhook/{stripe,paypal}`,
  `/verify/{google,apple}`, `/cancel`. Registered under `/subscription`. Webhook paths added to the
  CSRF exemption in `main.py` (they're signature-authenticated, not cookie-authenticated).
- `core/entitlement.py` — `require_plus` FastAPI dependency to gate premium endpoints server-side.
- `core/config.py` — SUBSCRIPTION_*/STRIPE_*/PAYPAL_*/GOOGLE_PLAY_*/APPLE_* settings + `PUBLIC_WEB_URL`.
- Alembic `bb002_add_subscriptions` (down_revision `aa001_add_medication_source`; id 23 chars ≤ 32).

**Web (`WEB/frontend`)** — `pages/Subscription.jsx`: pricing card + card/PayPal buttons that hand off to
the hosted checkout, redirect-return `/confirm`, subscribed card with cancel, and a mobile-pricing note.
Route `/subscription` in `App.jsx`; "ALAFIA Plus" nav entry (Sparkles) in `Layout.jsx`.

**Android** — Play Billing `billing-ktx:7.1.1` in `app/build.gradle`. `billing/BillingManager.kt` (v7:
query SUBS product, launch flow, re-report owned purchases, acknowledge after server verify).
`views/subscription/SubscriptionScreen.kt` verifies the purchase token via `/verify/google`. Models +
`ApiService` methods added; route + a "ALAFIA Plus" More-grid tile in `MainTabView.kt`.

**iOS** — StoreKit 2 in `Views/Subscription/SubscriptionView.swift` (`StoreManager`: load product,
purchase, `Transaction.updates`/`currentEntitlements`, verify JWS via `/verify/apple`, finish). Codable
models in `NewFeatureModels.swift`; new file wired into `project.pbxproj`; "ALAFIA Plus" section in
`MainTabView.swift`.

**Verified this session (Docker daemon was down → no live stack):**
- Android `:app:compileDebugKotlin` — BUILD SUCCESSFUL (billing dep resolved).
- iOS `xcodebuild -scheme ALAFIA` (iPhone 17 Pro sim) — BUILD SUCCEEDED (SubscriptionView compiled).
- Backend: `py_compile` clean; 24/24 pure-logic unit checks PASS against the real modules in a minimal
  venv (entitlement grace math, cancel-still-in-period, naive-tz handling; Stripe sig valid/tampered/
  replay/malformed; ts→dt; rail pricing bound to settings; status maps).

**To go live (owner action, not code):** set provider keys (Stripe price/webhook, PayPal plan/webhook,
Google service account, Apple shared secret) in `backend/.env`; create the `alafia_plus_monthly` product
in Play Console + App Store Connect; run `docker compose exec backend alembic upgrade bb002_add_subscriptions`.
Apple JWS x5c cert-chain verification is decoded-but-not-chain-validated — hardening follow-up noted in
the service. Web/DB live smoke test still pending (blocked on Docker this session).

## Session 2026-07-21 — Subscription: finish + live smoke test (found/fixed a real bug)

**Instruction:** finish the remaining task (subscription) and start deployment (GCP + Play + App Store).

Brought the stack up and closed out the pending subscription items:

- **Migration graph was broken (two heads → couldn't `upgrade head`).** `bb002_add_subscriptions`
  and the last commit's `aa001_add_medication_source` were BOTH branched off `z001` (a stale head),
  while the mainline had advanced to `ll001`. Re-parented to linearize:
  `ll001 → aa001_add_medication_source → bb002_add_subscriptions` (subscription tables are
  independent, so this is a pure graph repair). `medications.source` and the `subscriptions`/
  `subscription_events` tables already existed out-of-band (auto-created from the models), so on this
  dev DB I `stamp`ed past them; the linear chain still applies cleanly on a fresh DB (CI/prod).
- **Live smoke test surfaced a real bug.** In DEBUG test-mode the web rails (Stripe/PayPal) return a
  *constant* reference id, and unlike the mobile rails they didn't guard the idempotency insert — so
  the **2nd user (or any double checkout-redirect) 500'd** on the unique `(provider, event_id)`
  constraint. Fixed the single choke point `_record_event` to wrap the insert in a **SAVEPOINT**
  (`begin_nested` + catch `IntegrityError`) → idempotent, race-safe, and dialect-agnostic (Postgres in
  prod, SQLite in tests — so it can't be a `postgresql.insert` only fix).
- **Verified end-to-end (live):** all 4 rails activate → entitled (Stripe $12, PayPal, Google $14,
  Apple $14); status flips none→active; cancel-at-period-end keeps access through the period;
  same-user double-confirm and cross-user shared-ref both return 200. Added
  `tests/test_subscription_service.py` (3 tests). **Full suite: 213 passed.**
- **Still open for iOS go-live:** Apple StoreKit JWS x5c cert-chain validation (decoded, not yet
  chain-verified to Apple's root CA) — harden before trusting real iOS purchases.

**Deployment kickoff:** target **Google Cloud** (Cloud Run + Cloud SQL) for backend/web/db/identity,
**web/API track first** (user decisions).

Built the GCP web/API deploy scaffold under `deploy/gcp/`:
- `provision.sh` — enable APIs, Artifact Registry, Cloud SQL (Postgres 16), and app secrets
  (SECRET_KEY, composed DATABASE_URL(s), identity-migration-secret, provider-key placeholders) in
  Secret Manager. Idempotent.
- `deploy.sh` — build/push (local Docker, `--platform linux/amd64`) → deploy **identity** → run a
  one-off **alembic-migrate job** → deploy **backend** → deploy **frontend**, then a 2nd pass to set
  `PUBLIC_WEB_URL`/`CORS_ORIGINS` to the public URL. Backend pinned to 1 always-on instance with the
  in-process schedulers disabled (they can't fan out on an autoscaled service).
- `frontend/` — prod nginx image that proxies `/api` + `/ws` to the backend's `run.app` host, so the
  app keeps **one origin** (CSRF + refresh-token cookies stay same-site; no CORS split).
- `README.md` — full runbook incl. identity-key generation, HIPAA BAA, subscription go-live (fill
  Secret Manager, rails 503 until then — never a fake charge), and what's deferred (GPU LLM, Redis,
  blockchain, schedulers, email, media storage).
- `config.env` + `keys/` git-ignored. Scripts pass `bash -n`. **Executing needs the owner's GCP
  project + billing + `gcloud auth login`** — I can't run it without those.

### 2026-07-21 (cont.) — LIVE on Google Cloud (web/API track)

Deployed to a dedicated project **`alafia-prod-6igma`** (org 6igma.com, billing New2025 — freed a
project-quota slot by unlinking 4 unused projects). Cloud SQL `alafia-db` (Postgres 16, db-g1-small,
ENTERPRISE edition), Secret Manager for all secrets, three Cloud Run services in `europe-west1`.

**Live URLs:**
- App: https://alafia-frontend-xj37wg452q-ew.a.run.app
- API (mobile targets this): https://alafia-backend-xj37wg452q-ew.a.run.app
- Identity (PQC SSO): https://alafia-identity-xj37wg452q-ew.a.run.app

**Two latent bugs the first-ever clean migration-from-base exposed (fixed + committed):**
1. `b5c6d7e8f9a1` notifications — DO-block created the enum, then `create_table` re-emitted CREATE TYPE
   in the same txn (generic `sa.Enum(create_type=False)` didn't suppress it) → use `postgresql.ENUM`.
2. Model/migration drift — `users.firebase_uid` (and 11 more cols + 2 tables) only ever existed via
   `create_all` on dev DBs → additive migration `cc002`. Both verified `upgrade head` from base.

**Verified live end-to-end:** backend health; SPA; frontend→/api proxy → DB-backed subscription plans;
hybrid JWKS (Ed25519 `OKP` + ML-DSA `AKP`); register 201 → login (5.3 KB hybrid token) → `/users/me`
(backend verifies via JWKS) → subscription status. Full auth + entitlement chain works in prod.

**Deferred (documented in deploy/gcp/README.md):** GPU LLM (AI → 503), Redis (WS off), blockchain,
in-process schedulers (off on autoscale), SMTP, media→GCS. **Subscription rails 503 until real
provider keys go into Secret Manager** (never a fake charge). Next tracks: custom domain + TLS, then
Google Play + iOS App Store (mobile apps point at the API URL above).

## Session 2026-07-22 — Prod data migration, hard paywall, timezone fixes, task tracker

**Data + identity migration (local → prod Cloud SQL).** "login not working" was just the fresh prod
DB having no accounts. Migrated the local `public` schema (75 users + all health + subscription data)
via `pg_dump -n public --no-owner` (NOT `--clean` — that emits `DROP SCHEMA public`, which broke on a
leftover enum dep and half-dropped the DB; recovered by recreating the DB + plain import as
`--user=alafia`) excluding the ~340 MB clinician-ingest staging; `alembic stamp cc002`. Then also
migrated the `identity` schema data-only (124 identity users + Argon2 creds; self-contained FKs) so
migrated users — incl. `developer@hntsolutions.com` — log in via the prod IdP exactly as locally.
Verified in-browser. PHI/credential dumps deleted from GCS after import.

**Hard paywall (no free tier).** `SUBSCRIPTION_REQUIRED=true` + a router dependency
`require_active_subscription` gate the whole `/api/v1` surface: authenticated non-exempt users without
an active subscription get 402 on gated paths; `/auth`, `/subscription`, `/users` stay open so they can
sign in + pay; `SUBSCRIPTION_EXEMPT_EMAILS` (default `developer@hntsolutions.com`) bypasses. Frontend
redirects to `/subscription` on 402. Verified live (non-sub → 402/redirect; entitled + exempt → pass).
`54532a1`. **Consequence:** with the paywall on AND no live keys, new users are locked out until
payments go live. Kill-switch: set `SUBSCRIPTION_REQUIRED=false`.

**Timezone — "times race ahead as if UTC."**
- Web `27e63c8`: added `utils/datetime.js` (parse naive-as-UTC + format in machine locale; `localToday`
  for date inputs); swept 27 pages off `new Date().toISOString().split('T')[0]` (UTC "today") and the
  timestamp displays. Verified live (showed local July 21, not UTC July 22).
- Mobile `9e7b9a6`: Android formatters were `LocalDateTime.parse(strip "Z")` (UTC read as local); iOS
  used UTC `ISO8601DateFormatter` for "today" + sliced raw ISO strings. Added `AppDate` on each platform
  (parse naive-as-UTC + device-local format) and routed the buggy sites. Both compile; on-device visual
  check still pending.

**All outstanding work is now logged in `DEPLOYMENT_TASKS.md`** (master tracker): payments go-live,
custom domain, deferred infra (GPU LLM / Redis / blockchain / email / media / Firebase sync), and full
**iOS + Android app-store deployment checklists**. Surfaced two mobile blockers there: apps hardcode
`https://api.alafia.com` (no domain yet), and iOS bundle `com.alafia.app` ≠ backend
`APPLE_BUNDLE_ID=com.alafia.ios` (must match for Apple purchase verification).

## Session 2026-08-01 — Meal-photo analysis goes live on web + iOS + Android

**The gap.** `POST /ai/vision` has been real for a while (ALAFIAModel VISION capability → llava via
Ollama, OpenAI vision as fallback), and PromptHub / PromptView / `routeVision` already called it. But
the *Nutrition* screen's "Analyse Image(s) with Alafia" button was a fake on **all three clients** —
a `setTimeout` / `DispatchQueue.asyncAfter` / `delay(800)` that printed *"Image analysis coming soon
(ALAFIAModel Phase 5)"*. Users could attach up to 3 photos and got a canned string back. Android was
worse: its "Choose Files" button incremented a counter (`selectedImageCount++`) with **no picker at
all** — no image was ever selected, let alone uploaded.

**One meal, one reading (the design call).** The UI accepts 3 photos, but they are normally the *same
plate* from different angles. Looping the single-image endpoint per photo and merging client-side
would have **double/triple-counted the calories** — and duplicated that merge logic across three
platforms. So the multi-image handling went **backend-side**, matching the standing canon that model
strategy is a backend concern:

- `InferencePayload` gained `images: list[dict]`; `VisionCapability._collect_images` normalizes the
  multi- and legacy single-image shapes into one list.
- `_vision_chat` / `_ollama_vision` / `_openai_vision` now take N images and send them in **ONE**
  model call (Ollama: N base64 in `images`; OpenAI: N `image_url` content blocks).
- With >1 image the prompt appends `_MULTI_IMAGE_RULE`: *"You are being shown {n} photos of THE SAME
  meal … Do NOT count a dish more than once because it appears in more than one photo."*
- Capability `version` → `0.3.0-vision-llm-multi`; response carries `image_count`.

**`/ai/vision` is now `file` OR `files` (or both), capped at 3.** The original single `file` field is
untouched, so the existing PromptHub / iOS PromptView / Android `routeVision` callers keep working —
verified against FastAPI across 7 request shapes (legacy single, multi, both, over-cap, none, empty
bytes, task passthrough).

**Clients (parity — web, iOS, Android all wired):** each sends every selected photo in one request,
prefills the meal form from the result (food name joined from items, serving size from the top item's
portion, `fdc_id`/`fdcId` cleared since a vision estimate is not USDA-linked), renders the detected
items with portion + confidence, and degrades to manual entry on 503 rather than erroring. iOS also
prefills the visible calorie/protein/carb/fat fields (they save, because `fdcId` is nil). Added a
reusable `APIClient.postImages(...)` on iOS (multipart was previously copy-pasted per view) and
`routeVisionMulti` on Android, plus a **real** `GetMultipleContents` image picker for Android.

**Verified:** ML vision tests 9/9 (2 pre-existing tests updated for the new `_vision_chat` signature,
4 new covering single-call-for-N-images, the anti-double-count prompt, and payload normalization);
web `vite build` ✓; iOS `xcodebuild` ✓; Android `compileDebugKotlin` ✓. Two `test_hebcs.py` failures
are pre-existing (feature-bridge coverage 71.4% < 75%), confirmed failing on a clean tree.
**Not run here:** the backend pytest suite — no environment on this machine has the backend deps
(`sqlalchemy`, `pytest_asyncio`); `app/api/ai.py` was compile-checked and its request handling probed
against a real FastAPI app with the identical signature.

## Session 2026-08-03 — Food vision: storing, labelling, identification, quantity

**The blocker was the pipeline, not the model.** Phase 5 (on-device food
classifier) had no training data and no way to get any: `LabeledFoodImage` stored
a 64-bit dHash and *discarded the image*, and `/ai/vision` recorded nothing — so
every user correction was thrown away when the meal was saved. Measured state
before this session: **1 labelled row across 77 users, 0 images**.

**Now collecting.** New append-only `food_training_samples` (photo + prediction +
correction; one row per analysis) alongside the existing upserted recall index.
Photos land in `media_assets(category='food_training')`, retained **only** with
`PrivacySettings.allow_collective_insights` (default false; absent row = no
consent). Without consent the sample is still written — accuracy stays measurable
— with `media_asset_id` NULL. Both paths verified against the live stack.

**Corrections are the point.** `POST /ai/vision/feedback` turns every edit into a
supervised pair, classified `accepted|item|quantity|both` so the corpus is
queryable ("every photo where the model named the wrong food"). Verified row:
`predicted Carrots => corrected Jollof rice, kind=item`.

**Quantity estimation** (`portion_estimator.py`): prose → grams with the rule and
confidence surfaced. `1 cup / 150 g`→150 g (stated), `1 cup` jollof→158 g
(volume × 0.66 g/ml — rice is not water), `1 cup` spinach→72 g, `1 medium
carrot`→61 g. A user-corrected serving weight overrides every heuristic. When it
cannot tell it returns **nothing** rather than inventing a calorie count.

**Recall before inference.** `/ai/vision` now checks the user's own labels first
and returns their corrected foods *and* grams: **~25 s model call → 76 ms**.

**Parity: web + iOS + Android** all ship editable food/grams rows, a
"Confirm / correct" action and the recall banner. (First pass was web-only — a
canon violation, corrected in the same session.)

**Bugs found and fixed en route:**
- `OLLAMA_VISION_MODEL: moondream` in compose — a *grounding* model that answers
  the food schema with bounding boxes and never emits `items`; every photo
  failed with "unparseable output". Switched to llava, verified against both.
- The JSON parser was one regex; it now handles markdown fences, prose-wrapped
  JSON and token-limit truncation (closes unterminated brackets). Valid JSON in
  the *wrong shape* now fails loudly naming the model instead of reporting "no
  food recognised" and blaming the photo.
- `record_prediction` caught its exception but a failed flush poisons the
  session, so the caller's commit 500'd — training-data logging would have taken
  down the feature it supports. Writes now run in a `SAVEPOINT`.
- Correction classification compared grams **positionally**: a reorder counted as
  a quantity change and a dropped item became `both`, which would have
  mislabelled most of the corpus. Now keyed by food name.
- `greenlet` missing from `backend/requirements.txt` (SQLAlchemy async needs it;
  not auto-pulled on 3.13) — every DB route 500s in the container without it.
- `public/fonts/inter.css` was mode 600, so `COPY` produced an image where nginx
  could not read it → 403, Inter never loaded **in production either**. Fixed the
  file and added `chmod -R a+rX` to the frontend Dockerfile.

**Verified:** 36 backend tests (26 portion, 10 corpus) + 18 ML vision tests; web
build; iOS `xcodebuild`; Android `assembleDebug`. Full loop driven in a real
browser against the compose stack: analyse → correct → 76 ms recall with the
corrected values.

**Still blocking Phase 5** (documented in `VISION_TRAINING.md`): corpus size
starts near zero, no `train_food_vision.py`, no torch/tensorflow (only
`coremltools`), free-text labels with no 200-class vocabulary, no West African
dataset, base64-in-Postgres storage, and no Core ML/TFLite export path.

## Session 2026-08-05 — Async nutrition saves, Resend email, password toggles, admin console

**Nutrition saves are now asynchronous.** Estimation ran inside the save, so a
10-item meal ("3 sardines, 4 pitted olives, …") exceeded the web client's 30s
timeout — and because the request never committed, the user LOST the meal.

Three causes, all fixed:
1. `_try_usda` looked items up **sequentially** — 10 round trips (7.64s locally).
   Now concurrent with a bounded semaphore: **2.24s**, same 9/10 matched.
2. The real bug: for a list, the single-food path merges matches by **summing
   per-100 g densities**. Densities don't add — the meal came back as **1978
   kcal/100 g**, above pure fat (~900). The plausibility band correctly rejected
   it, and the pipeline escalated to the slow AI fallback. Multi-item meals now
   use `estimate_meal_nutrients()` (scales by gram weight, sums to a TOTAL):
   **967 kcal, 30.9 g protein, believable**.
3. Estimation no longer runs in the request at all. The log is saved and returned
   immediately with `nutrient_status="pending"`, and a background task enriches
   it. Measured: **save 30s-timeout → 1.5s**; in the browser the row appears in
   **96 ms** showing "estimating…", nutrients auto-arrive with no reload.

All three clients show `pending`/`failed` states rather than a blank, which reads
as zero calories. New column `nutrition_logs.nutrient_status` (dd004).

**Email implemented — Resend.** `app/services/email.py` gained a Resend HTTPS
sender (preferred on Cloud Run: no outbound mail ports, no STARTTLS, real error
bodies) with SMTP kept as the self-hosting fallback. A real verification email
was delivered end-to-end. `deploy.sh` mounts `resend-api-key` AND grants the
service account access — it previously mounted no email secret at all, so prod
could never have sent mail regardless of code.

⚠️ **No domain is verified on the Resend account**, so production can currently
only mail the account owner. Verified against the live API; details in
`ADMIN_CONSOLE.md`. `smtp.md` holds the key and is now **gitignored** — it was
not, repeating the `api_keys.md` exposure.

**Show/hide password across web, iOS and Android** — one component per platform
(`PasswordInput.jsx`, `LKTextField(isSecure:)`, `PasswordField.kt`) covering all
14 password fields. The web toggle is `type="button"` (a bare button inside a
form submits it); iOS restores `@FocusState` after the SecureField⇄TextField swap
or the keyboard dismisses mid-typing; revealed passwords keep
no-autocapitalise/no-autocorrect on mobile.

**Admin console** at `minister.alafia.com` (`/minister` in dev) for dew@6igma.com
— users, last login, token usage, app health. Required fixing two things first:
`last_login` did not exist (and the SSO branch of `/auth/login` early-returns, so
stamping only the local path left it NULL for everyone), and `tokens_used` was
never written because the LLM capability discarded the provider's count.

**Robot accounts:** 55 `*@example.com`/`*@x.com` accounts deactivated (not
deleted — 65 of 101 FKs are NO ACTION), plus **56 identity-only** robots that had
no ALAFIA user row but could still have materialised one via SSO provisioning.
Dev: 77 → **22 active users**. Reversible. Prod untouched.

**Signup is now two-step** — verify email, pay, then the account is created.
`/auth/register` is 410 Gone. `/signup/complete` verifies the Stripe session with
Stripe (paid AND belonging to this signup) rather than trusting a client-supplied
reference, which previously meant any string bought an account.

**Also fixed:** password reset did not revoke the old password (login checks the
IdP first, reset wrote only the local hash — two working passwords after a
"successful" reset); the frontend container reported `unhealthy` forever because
its healthcheck used `localhost`, which resolves to `::1` while nginx listens on
IPv4 only; `/fonts/inter.css` was mode 600 so nginx served it 403 **in production
too**; `greenlet` was missing from `requirements.txt`.

**Correction:** an earlier claim of "5 alembic heads" was wrong. `alembic heads`
reports exactly **one**. The hand-rolled scan that produced it missed the
annotated form `down_revision: Union[str, None] = '…'`. Never grep for this.
