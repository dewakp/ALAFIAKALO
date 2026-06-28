# LAFIAKALO / ALAFIA — Gap Analysis (Stock-Take #2)

**Audit Date:** 2026-06-11
**Prior baseline:** `06062026_GapAnalysis.md` (32 gaps)
**Repository:** `/Users/woleakpose/Documents/Developer/LAFIAKALO` → `git@github.com:dewakp/ALAFIAKALO.git`
**Evidence:** `WORKLOG.md` (sessions 2026-06-07 → 2026-06-10) + code verification on 2026-06-11.

---

## Executive Summary

In the 5 days since the 6/6 baseline, **4 work sessions** closed **9 of the 32 gaps** plus shipped a net-new personalized nutrient-goals feature (web + iOS + Android). The "immediate" infrastructure-wiring tier from the 6/6 plan is largely done **except that the production env vars were never set** — so Sentry/S3/Redis remain inactive in practice despite the code being ready.

**The hard architectural core has not moved:** the ML/HEBCS serving spine (#4, #5, #9), bidirectional sync (#3), fine-tuned models (#7), and the unbuilt ML layers (#8) are all untouched. Three **new risks** surfaced during the work, the most serious being placeholder cert-pinning that will break mobile release builds.

| | 6/6 Baseline | 6/11 Now |
|---|---|---|
| Closed | 0 | **9** (+1 bonus feature) |
| Partial | — | 2 |
| Open (orig. 32) | 32 | **21** |
| New risks | — | **3** |

---

## ✅ CLOSED (9 gaps + 1 bonus feature)

| # | Gap | Resolution | Verified |
|---|-----|-----------|----------|
| 2 | Backend bypassed ALAFIAModel | All AI call sites route through `alafia_chat()`/`alafia_complete()`; router gained `json_mode`+`model`, Ollama→OpenAI fallback. Converted: `ai_engine`, `diagnostics_engine`, `nutrient_estimator`, `planners`, `ai_learning`, `ai.py` non-stream chat. | py_compile clean; router smoke-tested |
| 6 | CI/CD inactive | `workflow_dispatch` added to all 4 workflows; root `.gitignore` protects secrets + excludes HEBCS/docs; initial commit `be9f4a5` pushed; workflows triggered & active. | All 4 active on `main` |
| 11 | CollectiveInsight placeholder | `ai_memory_service.merge_demographic_baseline()` does real consent-gated running-mean cohort aggregation; `privacy_service` contributes departing user's footprint before deletion. | SQLite test: 2 users→mean 80→90; no-consent skipped |
| 12 | MCP server not exposed | Runs as own container (`Dockerfile.mcp` + `requirements-mcp.txt` + `mcp` compose service, port 8003); supports sse/http/streamable-http. | Container probed: `/sse`→200 |
| 13 | Med→nutrient frontend missing | Shared `_aggregate_daily_nutrients()` folds resolved med-dose nutrients into daily summary; surfaced in goal-progress card. | goal-progress 200 against real patient |
| 18 | Metric/Imperial toggle | `utils/units.js` + `UnitsContext` + `UnitToggle`; wired into `App.jsx`; Profile inputs unit-aware (store canonical metric, edit in active system); persists to `PATCH /users/me`. | Frontend Docker build passes |
| 19 | iOS APNS token not sent | `DeviceToken` model + migration `x001`; `POST /notifications/apns-token` + `/fcm-token` + `DELETE`; iOS registers + re-sends post-login. | Single migration head verified |
| 21 | Mobile dose logging | iOS `MedicationDoseSheet` swipe-action + Android "Log Dose" dialog → `POST /medications/dose-logs`. | iOS + Android builds succeeded |
| 1 (Voice) | Voice was 404 stub | `whisper_adapter.py` (self-hosted Whisper primary, OpenAI fallback); `voice.py` real pipeline (audio→transcript→LLM clinical extraction); `POST /ai/voice`; 8 languages. | Capability reports implemented; route live |
| 🆕 | — | **Personalized daily nutrient goals** — `nutrient_goals_service.compute_goals()` (Mifflin-St Jeor + DRIs + condition flags: ckd/dialysis/diabetes/htn/hf); `GET /nutrition/goal-progress`; cards on web MealsDiary + iOS + Android. CKD→protein/K/PO₄/Na limits. | Unit-tested; 200 against CKD+dialysis patient |

---

## 🟡 PARTIALLY CLOSED (2)

- **#1 — ALAFIAModel capability stubs:** Voice now ✅ implemented. **Vision** still `is_implemented=False` (`capabilities/vision.py:39`, Phase 5). **Video** still `0.1.0-scaffold` (`capabilities/video.py:38`, Phase 8). Progress: 1/5 → **3/5** working (NLM, LLM, Voice).
- **#2 — Router consolidation:** Complete except `api/ai.py` `/chat/stream`, which **still streams directly from Ollama** (router has no streaming capability — Phase 3 TODO).

---

## 🔴 STILL OPEN — unchanged since 6/6 (21)

### High severity — untouched architectural core
| # | Gap | Evidence |
|---|-----|----------|
| 3 | Firebase sync still one-way | `firebase_sync.py` unchanged |
| 4 | HEBCS feature-extraction → inference seam broken | `hebcs_engine.py` untouched since 2026-04-20; `/api/v1/wellness/score` still needs 284 features only the ML pipeline produces |
| 5 | ML model serving/deployment undefined | No serving layer/container/versioning added |
| 7 | No fine-tuned domain models | All AI still generic OpenAI/Ollama |
| 8 | ML layers 2/4/5 (BioBERT NLP, vision, recommender) not built | Unchanged |
| 9 | HEBCS trained on single patient only | Unchanged |

### Medium / Low — untouched
| # | Gap |
|---|-----|
| 10 | Pantry grocer API (Instacart/Kroger/Walmart) — still TODO |
| 17 | Mobile not wired to `/media/upload` (still base64) |
| 20 | Android Vision stub — **confirmed** `TODO(alafia-model)… Phase 5` at `NutritionScreen.kt:414` (blocked by #1 Vision) |
| 24 | Android uses Compose state, not ViewModel/StateFlow MVVM |
| 25 | Dark-mode toggle missing (units toggle ≠ dark mode) |
| 26 | 8 of 11 i18n languages have no translation files |
| 27 | West African food alias map still static |

### ⚠️ "Activated?" check — code ready, env NOT set (so effectively still open)
`.env` contains **no** `SENTRY_DSN`, `S3_*`, or `REDIS_URL` keys. Config defaults exist but nothing populates them.
- **#14 Sentry** — `SENTRY_DSN: str = ""` default; never set → not initializing.
- **#15 Redis** — `REDIS_URL` defaults to `redis://localhost:6379/0`; not in `.env`, untested in compose path.
- **#16 S3** — `S3_BUCKET: str = ""`; not in `.env` → still falling back to base64.

---

## 🆕 NEW RISKS surfaced during the work (not in original 32)

| # | Risk | Severity | Detail |
|---|------|----------|--------|
| N1 | **Mobile cert-pinning is placeholder** | HIGH | `AAAA…`/`BBBB…` pins in both mobile `APIClient`s → **release builds will reject all traffic** until real SHA-512 pins are added. Debug/sim unaffected. |
| N2 | **Sync-on-async pattern persists** | MEDIUM | `personalization.py` (AIMemoryService) and `ai_engine.py` (`AIPersonalizationEngine`) still use sync `.query()` against the async `get_db` → will 500 like PrivacyService did. Fix = `get_sync_db` + `def` endpoints (same pattern already applied to PrivacyService). |
| N3 | **Docker disk hygiene** | LOW/OPS | VM hit 100% mid-session, crash-looped Postgres (recovered, no data loss). Rebuild churn fills disk fast → run `docker builder prune -af` periodically; consider larger Docker Desktop disk image. |

---

## Recommended Next Focus

### Tier 1 — config-only activations (~30 min, high leverage)
- Add `SENTRY_DSN`, `S3_BUCKET`/`S3_REGION`/keys, `REDIS_URL` to `.env` (#14/#15/#16).
- Replace placeholder mobile cert pins with real SHA-512 hashes (N1) — **blocks any mobile release.**

### Tier 2 — pre-empt the latent 500 (small, same known fix)
- Apply `get_sync_db` + `def` conversion to `personalization.py` / `ai_engine.py` AIPersonalizationEngine (N2).

### Tier 3 — the untouched architectural core (the real remaining work)
- **HEBCS production path (#4/#5/#9):** feature-extraction microservice → wire `wellness.py` → standalone, versioned inference service → generalize beyond Patient-001.
- **Bidirectional Firebase ↔ PostgreSQL sync (#3).**
- **Router streaming capability (#2 remainder)** so `/chat/stream` leaves the abstraction intact.

### Tier 4 — vision phases & polish
- Vision Phase 5 (unblocks #1 Vision + #20 Android) → Video Phase 8.
- Fine-tuned models (#7), ML layers 2/4/5 (#8), pantry API (#10), `/media/upload` mobile wiring (#17), dark-mode toggle (#25), i18n (#26), alias map (#27).

---

## Scorecard

| Severity | 6/6 Open | Closed | Partial | 6/11 Open | New |
|----------|---------|--------|---------|-----------|-----|
| Critical | 2 | 1 (#2) | 1 (#1→3/5) | ~1 | — |
| High | 7 | 1 (#6) | — | 6 | 1 (N1) |
| Medium | 15 | 6 | 1 | 8* | 1 (N2) |
| Low | 8 | 1 (bonus area) | — | 7 | 1 (N3) |

\* incl. #14/#15/#16 which are code-ready but env-inactive.

**Bottom line:** Strong execution on the wiring/UX tier — 9 closed + a real new feature. The platform's defining ambition (the ML/HEBCS engine, multi-patient scoring, offline-first bidirectional sync) is still the untouched 20% that carries 80% of the strategic value. Next dollar is best spent on the config activations + cert pins (cheap, unblock release/observability) and then committing to the HEBCS serving spine.

---

*Generated 2026-06-11. Companion to `06062026_GapAnalysis.md` and `04142026Audit.md`. Source of truth for per-session detail: `WORKLOG.md`.*
