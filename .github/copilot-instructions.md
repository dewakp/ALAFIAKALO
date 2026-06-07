# ALAFIA Copilot Instructions

> **Anti-drift anchor** — This file is the single source of truth for agent behavior
> in the ALAFIA / LAFIAKALO workspace. Read it at the start of every session.
> Last updated: 2026-06-04

---

## 1. Project Identity

**Product:** ALAFIA — a multi-platform precision health and wellness application.
**Owner:** 6igmaHealthBook / Wole Akpose
**Workspace root:** `/Users/woleakpose/Documents/Developer/LAFIAKALO`

### Platforms

| Platform | Root |
|----------|------|
| iOS (SwiftUI) | `IOS/` |
| Android (Kotlin/Compose) | `Android/` |
| Web (React + FastAPI) | `WEB/` |
| ML / AI engine | `ML/` |
| Research (HEBCS) | `HEBCS/`, `HEBCSL_MATLAB/`, `Book/` |

---

## 2. Mandatory Session Start Protocol

At the beginning of **every** session the agent MUST:

1. Read `docs/ALAFIA_CONVERSATIONS.md` — the rolling conversation log
2. Read `docs/AI_ENGINE_ARCHITECTURE.md` — the AI engine design
3. Check `docs/AI_ENGINE_NUTRITION_NLM.md` if the task involves nutrition
4. Check `WEB/backend/AI_MEMORY_INTELLIGENCE.md` if the task involves AI personalization
5. Announce the last conversation date and its summary headline before proceeding

If any of these files are missing, create them using the templates in this file.

---

## 3. Architecture Constraints (Never Violate)

### 3.1 ALAFIAModel First
All new AI/ML capabilities MUST be routed through or scaffolded for the
`ALAFIAModel` in `ML/src/alafia_model/`. External APIs (OpenAI, Anthropic,
Google) are **temporary fallbacks only**. Every new LLM call must have a
`TODO(alafia-model): replace with ALAFIAModel.{capability}` comment.

### 3.2 Data Sovereignty
- All PHI/PII stays on ALAFIA infrastructure — never in third-party AI logs
- User health data must NOT be sent to OpenAI/Anthropic as part of prompts
  unless the user has explicitly consented and data is de-identified
- Anonymize before any external API call

### 3.3 No Vendor Lock-in
- External AI API calls must live in a single adapter layer
  (`ML/src/alafia_model/adapters/`) so they can be swapped
- Never hard-code OpenAI/Anthropic models anywhere outside the adapter layer

### 3.4 Security (OWASP Top 10 always)
- Input validation at every system boundary
- No secrets in code — use environment variables only
- SQL via SQLAlchemy ORM — no raw queries with user input
- File uploads must be scanned and type-validated before processing

### 3.5 Nutrition Pipeline (NLM Engine)
- All food text parsing goes through `meal_parser.py` → `nutrient_estimator.py`
- Per-100 g profiles are looked up via Cache → USDA FDC → AI fallback
- Quantities are scaled by the meal parser's gram weights before aggregation
- West African food aliases live in `nlm_food_extractor.py`

---

## 4. Coding Standards

### 4.1 Backend (Python / FastAPI)
- Python 3.11+, async/await throughout
- Pydantic v2 for all schemas
- SQLAlchemy 2.x async ORM; no raw SQL with user input
- Type annotations on all public functions
- `logger = logging.getLogger(__name__)` — no print() in production paths
- Tests in `WEB/backend/tests/` matching module structure

### 4.2 iOS (Swift / SwiftUI)
- Swift 5.9+, SwiftUI for all new views
- MVVM: `ViewModels/` own all business logic
- `APIService.swift` is the sole network layer — no direct URLSession in views
- Combine/async-await for reactive data

### 4.3 Android (Kotlin / Compose)
- Kotlin 1.9+, Jetpack Compose for all new screens
- MVVM with `ViewModel` + `StateFlow`
- Retrofit + OkHttp for networking
- Hilt for dependency injection

### 4.4 ML / AI (Python)
- Models saved as `.joblib` (sklearn) or `.safetensors` (transformers)
- Every model version logged in `ML/models/` with `schema.json`
- Feature names must match `ML/feature_bridge.py` mappings
- Notebooks in `ML/notebooks/` — no production logic in notebooks

---

## 5. Key Service Map

| Service | File | Purpose |
|---------|------|---------|
| Meal Parser (NLM) | `WEB/backend/app/services/meal_parser.py` | Free-text → (food, qty_g) components |
| Nutrient Estimator | `WEB/backend/app/services/nutrient_estimator.py` | Cache→USDA→AI per-100g lookup + meal aggregation |
| NLM Food Extractor | `WEB/backend/app/services/nlm_food_extractor.py` | Token normalization + alias expansion |
| AI Engine | `WEB/backend/app/services/ai_engine.py` | Health coaching LLM orchestration |
| AI Memory | `WEB/backend/app/services/ai_memory_service.py` | Pattern learning across sessions |
| HEBCS Engine | `WEB/backend/app/services/hebcs_engine.py` | Composite wellness scoring |
| ALAFIAModel | `ML/src/alafia_model/` | **Future** unified multimodal model |

---

## 6. ALAFIAModel — Capability Roadmap

The ALAFIAModel is ALAFIA's proprietary multimodal health AI that will
progressively replace all external API dependencies.

| Phase | Capability | Status |
|-------|-----------|--------|
| 1 | NLM: food text → structured parse | ✅ scaffolded (`meal_parser.py`) |
| 2 | NLM: clinical text → ICD-10 / symptoms | 🔲 planned |
| 3 | LLM: health coaching chat (fine-tuned BioMistral 7B) | 🔲 planned |
| 4 | LLM: nutrition guidance with RAG over USDA/WAFCT | 🔲 planned |
| 5 | Vision: food photo → nutrition (MobileNet fine-tune) | 🔲 planned |
| 6 | Vision: lab report OCR → structured data | 🔲 planned |
| 7 | Voice: speech → clinical NLP | 🔲 planned |
| 8 | Video: exercise form analysis | 🔲 planned |
| 9 | Unified API: single `ALAFIAModel.infer(modality, input)` | 🔲 planned |

---

## 7. Conversation Logging Rule

**Every session that makes code changes MUST:**
1. Append a new entry to `docs/ALAFIA_CONVERSATIONS.md` in this format:

```markdown
## Session YYYY-MM-DD — <short headline>

**Context:** <what was the stated goal>
**Changes:**
- <file changed>: <what was done>
**Key decisions:** <any architecture or design choices made>
**Next steps:** <what remains or what was deferred>
```

2. Update the "Last updated" date at the top of this file.

---

## 8. Anti-Drift Checklist

Before completing any session, verify:
- [ ] `docs/ALAFIA_CONVERSATIONS.md` has a new entry
- [ ] No secrets or API keys committed to code
- [ ] All new AI calls have `TODO(alafia-model)` comments
- [ ] No circular imports introduced
- [ ] `get_errors()` clean on all modified files
- [ ] New endpoints have schemas in `app/schemas/`
- [ ] New services are imported in their API routers
