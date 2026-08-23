# ALAFIA — working canon

Read this before touching anything. It exists because context was being
re-derived from scratch each session, and each re-derivation drifted.

---

## 0. NEVER GUESS

**Observe, then act.** Do not infer a cause from plausibility, from a similar
bug you just fixed, or from reading code that looks like it explains the
symptom. Capture the actual value — the request body, the row, the served
asset, the log line — and let it name the cause.

A guess that happens to be right still teaches the wrong habit, and a guess that
is wrong costs a deploy cycle and lands the next failure on the user. On this
codebase, three production save failures in a row were each "fixed" by reasoning
about the code path rather than looking at what was actually sent:

- `condition_id: 14` — a hardcoded literal. Verified by querying the table.
- `clinical_notes` as an array — verified by reading the API response shape.
- `reading_time` — an em-dash theory that the DATA disproved: zero NULL times,
  every value a valid `HH:MM:SS`. The theory was tidy and false.

If reproducing takes a browser, a container and a network capture, that is the
cheap option. The expensive option is shipping and finding out.

## 1. The database canon (non-negotiable)

> **Deployed (Cloud SQL) is the GOSPEL. Dev must be an exact copy of it.**

- Sync is **one direction only: prod → dev.** There is deliberately no
  `push_prod.sh`. Prod changes only through *migration + deploy*, never by
  pushing local data up.
- **Verify before you trust anything you see in the app.** A screenshot of the
  web or simulator proves nothing if dev is stale:

  ```bash
  scripts/db/verify_parity.sh     # exit 0 = dev is identical to prod
  scripts/db/pull_prod.sh         # replace dev with an exact copy of prod
  ```

- `verify_parity.sh` compares **every table's row count and content hash**, the
  column shape of every table, and the alembic revision, across schemas
  `public` **and** `identity`. Any difference exits non-zero and names it.
- **Never** "fix" a parity failure by editing dev data by hand. Re-pull.

Full procedure, setup and PHI handling: **`scripts/db/README.md`**.
(Note `/docs/` is gitignored in this repo — anything that must survive a fresh
clone or a new session belongs outside it.)

### Topology

| | Where | Notes |
|---|---|---|
| **Prod DB** | Cloud SQL `alafia-prod-6igma:us-east4:alafia-db-va` | Postgres 16. Authoritative. |
| **Dev DB** | `127.0.0.1:5435` (`WEB/docker-compose.yml` service `db`) | Postgres 16. **Port 5435, not 5432.** |
| **Schemas** | `public` (app) + `identity` (PQC SSO) | Both must match. Syncing only `public` is a silent drift bug. |

> ⚠️ A `postgres` on **5432** belongs to a *different project* on this machine
> (`sigma_db`). Connecting to it will look like it works and give wrong data.

All postgres tooling runs through pinned Docker images (`postgres:16-alpine`,
`cloud-sql-proxy:2.14.3`) — nothing is installed on the host, so client versions
can't drift between machines. Prod access needs ADC once per machine:
`gcloud auth application-default login`, plus `PROD_DB_PASS` in the environment.

## 2. Clients never touch a database

iOS, Android and web read data **only** through the backend API. If a client
shows stale data, the DB or the API it points at is stale — do not add
client-side data paths.

**Mobile points at PRODUCTION by default — simulator and emulator included.**
There is no second database for mobile to drift from.

| Client | API base | |
|---|---|---|
| iOS — simulator *and* device | `https://api.alafia.app/api/v1` | `IOS/ALAFIA/App/AppConfig.swift` |
| Android — debug *and* release | `https://api.alafia.app/api/v1/` | `Android/app/build.gradle` |
| Web (dev) | `/api` → `http://localhost:8005` | `vite.config.js` — **still local** |

> ⚠️ A simulator/emulator run on the default **writes to production**. Logging a
> meal or deleting an entry changes real patient data.

To run mobile against a local backend *on purpose*:

```bash
# iOS — simctl requires the SIMCTL_CHILD_ prefix; --setenv is silently ignored
SIMCTL_CHILD_ALAFIA_API_URL=http://localhost:8005/api/v1 \
  xcrun simctl launch <sim-id> com.alafia.app

# Android — 10.0.2.2 is the emulator's route to the host
./gradlew :app:assembleDebug -PapiBase=http://10.0.2.2:8005/api/v1/
```

`-PapiBase` is ignored by the release build on purpose: a shipped build can never
carry a local URL.

**The web dev server is still local** (`vite` proxies `/api` → `localhost:8005`),
so it remains subject to dev-DB staleness. Run `verify_parity.sh` before trusting
what the web app shows, or point it at prod in `vite.config.js`.

## 3. Mobile means iOS **and** Android, always

A feature is not done until web, iOS, and Android all have it. Same for the AI
router: clients call `/ai/*` and never name a model provider — provider strategy
is a backend concern so it can change without shipping a new app.

**This rule is not satisfied by disclosing that you broke it.** Shipping web-only
and then listing "iOS and Android not wired" under *what I did not do* is still
shipping a parity gap. Narrowing agreed scope is the user's call, not yours: if
mobile is genuinely blocked, say what blocks it and stop — otherwise finish it.
Verify each platform by building it, not by reasoning that the change should
compile.

## 3a. Food vision / training corpus

Meal photos, model predictions and user corrections are retained as the Phase 5
training corpus. Full detail — data model, consent, the portion→grams rules, the
API, and what still blocks Phase 5 — is in **`VISION_TRAINING.md`**.

Non-obvious points that have already caused bugs:

- Use `OLLAMA_VISION_MODEL=llava`. **Not moondream** — it is a grounding model
  and answers the food schema with bounding boxes, so every photo fails.
- Images are retained **only** with `PrivacySettings.allow_collective_insights`
  (default false; absent row = no consent). Without it the sample is still
  recorded, minus the photo.
- `correction_kind` is compared **by food name, not by list position**. Positional
  comparison marks a reorder as a quantity change and a dropped item as `both`.
- Writing training data must never break the user's analysis: the writes run in a
  `SAVEPOINT`, because a failed flush poisons the session and the later commit
  500s even when the exception was caught.

## 3aa. Clinical domains split across TWO tables — medications across THREE

Board mechanics, the four ways this surface showed "empty" when data existed, and
how to verify it: **`CLINICIAN_BOARD.md`**.

> **Reading one table and calling it the answer silently hides clinical facts.**
> Go through **`app/services/clinical_sources.py`** — never query these models
> directly.

| Domain | Live table | The other one |
|---|---|---|
| **Conditions** | `chronic_conditions` — Conditions screen, EHR import, dialysis/chemo flowsheets | `health_conditions` — **LEGACY: zero writers anywhere in the app.** Any query against it alone returns nothing, forever. |
| **Medications** | `medication_dose_logs` — what the patient actually TOOK, written by the Medications screen | `medications` — prescriptions/profile, written by the **EHR/FHIR import** (`api/ehr.py`) and manual entry |

> ⚠️ **Medications have a THIRD source: `therapy_sessions.drugs_administered`.**
> Drugs given *during dialysis* — free text, and for a long time unread by
> anything. On the production record it holds **Epogene ×1,962, Venofer ×1,248,
> Doxercalciferol ×788**, and **zero** of them appear in `medication_dose_logs`.
> They are administered by the unit, so they can never appear in a dose log the
> patient fills in. Checking the two tables above and calling it complete is how
> a review of that record concluded "no ESA prescribed or taken" while the
> patient had been on one for years. Read it through
> `clinical_sources.medications_administered()`; parsing lives in
> `services/flowsheet_drugs.py` (the `;` also occurs *inside* a dose, so a naive
> split invents drugs).

This is not theoretical. On one production record:

- `health_conditions` 0 rows vs `chronic_conditions` 4 — including **End-Stage
  Renal Disease, severe, active**, on a patient with 730 dialysis sessions. The
  clinician board said *"No active conditions."*
- `medications` 2 rows, both **stopped in 2017** (SMART-sandbox EHR test data)
  vs **921 dose logs**. The physician saw two stopped drugs while the patient's
  own screen showed Calcitriol and Calcium Carbonate taken that morning.
- `ai_engine` read only the legacy table, so the **AI coach believed every
  patient had zero conditions**.

Non-obvious points:

- **The EHR import writes `medications` and `chronic_conditions`** (`api/ehr.py`),
  so a connected sandbox seeds decade-old prescriptions that look current in a
  naive query. Prescribed ≠ taken; show both, labelled.
- Group dose logs **case-insensitively** — the same drug arrives as both
  "Calcium Carbonate" and "Calcium carbonate", and two rows misstate the regimen.
- Never let a query `LIMIT` become a count. The Therapies card reported "200
  sessions" on a patient with 730 because `len()` counted the limit.
- `tests/test_clinical_sources.py` **fails the build** if anyone queries these
  models outside the canonical module. To add a legitimate direct reader, put the
  file in its `ALLOWED` set with a comment saying why.


### Naive vs. aware datetimes at the API boundary

Some clinical columns are `DateTime` **without** timezone — notably
`therapy_sessions.scheduled_date` and `condition_metrics.measured_date`. Browsers
send an instant: `new Date().toISOString()` ends in `Z`, and FastAPI parses that
into a tz-**aware** datetime. Comparing aware to naive makes asyncpg raise
`DataError`, the endpoint 500s, and — because the page catches the error into an
empty list — it renders as **"No hemodialysis sessions found for this period"**
on a patient with 730 sessions.

`_naive_utc()` in `api/chronic_conditions.py` normalises on the way in. If you add
a datetime query parameter, check the column: `psql \d <table>` shows
`timestamp without time zone` vs `with time zone`.

### An error is not an empty state

This is the recurring failure of this whole surface, in four different disguises:

| Symptom shown | Actual cause |
|---|---|
| "No active medications" | reading `medications` instead of `medication_dose_logs` |
| "No active conditions" | reading `health_conditions`, which has no writer |
| "No hemodialysis sessions" | a 500 swallowed by `catch (e) { console.error(e) }` |
| "Nothing logged in the last 7 days" | a hard window on a patient who logs monthly |

**Never let a failed fetch fall through to the empty-state copy.** Keep a separate
`loadError` and say so. Where a card is windowed, report *when* the patient last
logged instead of showing a blank — "last logged 60 days ago" is a clinical
finding; a blank card is a dead end.

### Verify against the population, not one record

`scripts/board_sweep.py` runs every board category against **every user holding
data** and prints which paths never executed:

```bash
# NOTE: backend-test's env_file points DATABASE_URL at the *test* database, so
# the bare command reports "users holding data: 0" and proves nothing. Override
# it to sweep the dev copy of prod:
docker compose --profile test run --rm \
  -e DATABASE_URL="postgresql+asyncpg://alafia:alafia@db:5432/alafia" \
  backend-test python scripts/board_sweep.py
```

Checking a single well-populated patient proved almost nothing: on this database
it left `fitness` (no rows for ANY user), `lifestyle` (data belongs to a
different user) and `pd_sessions` (empty everywhere) unexercised, and hid that
six of the seven users with nutrition data fell outside the 7-day summary window.

## 3ab. Document import (any clinical PDF)

Upload → parse → **staged for review** → import. Full detail:
**`DOCUMENT_IMPORT.md`**.

- Parsing works from **word coordinates**, never `extract_text()`. A reference
  range printed beside a row reflows onto a different line, which cost the old
  extractor 489 of 853 ranges (3 of 13 documents lost every one). Now 510/510.
- **`pdfplumber` must stay in `WEB/backend/requirements.txt`.** Without it the
  upload endpoint falls through to decoding PDF bytes as UTF-8 and reads nothing.
- Nothing reaches a clinical table until the patient confirms. Duplicates arrive
  unticked; §3aa routing applies (documents state *prescriptions* → `medications`;
  conditions → `chronic_conditions`, never `health_conditions`).
- After touching `layout.py` / `normalize.py`, run the corpus harness — it reads
  the real PHI corpus and is deliberately not in CI:
  `ML/.venv-health-ml/bin/python WEB/backend/scripts/docparse_corpus_check.py`

> **A parser fix does not repair what it already imported — and re-importing
> makes it worse.** Dedupe is keyed on `(test_date, lower(test_name))`, and
> `existing_row_id` is recorded on the staging row but **never read back**: the
> commit path only ever constructs `LabResult(...)`, an insert. So even a
> `DEDUPE_CONFLICT` (same name and date, different value) adds a second row
> rather than correcting the first. Worse, a fix that changes the NAME —
> `WEIGHT - PRE DAY` → `WEIGHT - PRE DAY 1` — no longer matches the key at all,
> so the corrected row arrives as `DEDUPE_NEW` and lands *beside* the wrong one.
> The patient then has two contradictory weights on one date. **Delete first,
> then re-import:** `scripts/db/cleanup_docparse_artifacts.sh` (dry-run by
> default).

> **`docker run` without `-i` does not forward stdin, and psql calls that a
> success.** `db_lib.sh`'s `prod_psql`/`dev_psql` omitted it, so the one caller
> that pipes SQL in (`... | prod_psql -f -`, the docparse cleanup) handed psql an
> immediate EOF: it executed NOTHING and exited 0. The dry run printed no rows,
> which reads as "nothing to clean" — and `--apply` would have printed
> `applied.` plus its "NEXT: re-import" instruction while deleting nothing, so
> the re-import would have produced exactly the duplicate contradictory weights
> the paragraph above warns about. §3aa's "an error is not an empty state", now
> in a shell pipeline. Every other call site passes `-f /sql/<file>` or `-c`,
> which is why it survived unnoticed. **A destructive script that reports
> success is worse than one that fails.**

> **A lab report is a clinical document wrapped in legal boilerplate, and the
> boilerplate parses just as well as the results.** The DaVita reports carry
> "disciplinary action, up to and including termination of employment with
> DaVita.", which became a test name and a value and was shown to a clinician
> among real labs — **30 rows across 5 dates** on one record. `looks_like_prose()`
> in `normalize.py` rejects it by shape (word count, leading case, density of
> connective words) rather than by a phrase list, so the next document's footer
> is caught too.

> **A test name wider than its header label steals the value.** Column
> boundaries come from the header, so on
> `1715 WEIGHT - PRE DAY 1   57.5 kg` the "1" of "DAY 1" fell past the
> name/value boundary (x_mid 165.5 vs 162.0), won the value column, and the true
> 57.5 was discarded — a clinician saw **1 kg for a 57 kg dialysis patient**, and
> the pre/post pair that should differ by ~1 kg both read as 1.
> `_reclaim_name_overflow()` splits on the geometry: a gap *inside* a name is a
> word space (2.0 pt here), the gap to the real value is a column gap (29.0 pt).
> The same PDF family parses correctly or not depending on layout, so **a
> passing corpus run does not mean every document is fine.**

> **The corpus harness measures recall, not precision.** It scores reference-range
> recovery, so a parser can emit a hundred prose rows and still report 100%. That
> is how boilerplate-as-a-lab-result shipped past a green gate. When you change
> extraction, check what it *added* as well as what it recovered.

## 3ac. Dialysis changes the day's totals, not the limits

A session clears potassium and phosphorus in gram quantities and *adds* calcium
from the bath. Full detail: **`DIALYSIS_BALANCE.md`**.

> **A treatment changes the day's TOTALS. It never changes the LIMIT.**
> KDOQI's 2,000-3,000 mg/day of potassium is already the figure for a patient on
> dialysis. Raising it on a treatment day counts that clearance twice — and a
> typical session clears ~3,900 mg against a 3,000 mg limit.

- `therapy_sessions.blood_flow_rate` is the **prescribed** rate — a flat 350 on
  every row. The delivered rate is the per-session mean of
  `intradialytic_readings.blood_flow_rate` (median 397, SD 61, range ~150-480).
  Use the session column and blood flow silently becomes a constant.
- **Post-dialysis potassium exists but is never named "POST".** It is identified
  by facility and day: the provider draws the pre panel, an outside lab on a
  treatment day is the post. Same-day only — a next-morning K has re-equilibrated.
- `nutrition_backfilled.csv` needs deduping on `row_hash`: 26,400 rows,
  1,600 unique. Read raw it reports 26,600 mg of dietary potassium a day.
- Only **removals** are gated (completed session, serum below threshold, a draw
  within **30 days** — full credit ≤14, tapering to zero at 30 — and
  calibration). Gains are always applied — a guard that only relaxes is not a
  guard.
- Coefficients are per-patient and only adopted if they beat
  predict-the-previous-value on a **chronological** hold-out.

## 3ad. Conditions are ICD-11 coded, and the web screen was never wired

The patient's problem list. Full detail: **`CONDITIONS.md`**.

- **The web page existed but had no route** — 602 lines of working CRUD with no
  import in `App.jsx` and no link, since the initial commit. It did not regress;
  it was never wired. iOS and Android had it all along. Now at
  `/chronic-conditions`, linked from **Profile → Health Conditions**.
- **`icd11_code` is the patient-facing code; `icd10_code` stays.** They are
  different facts, not duplicates: ICD-10 is what the FHIR import and the PDF
  parser read off a source document. Label which system a code came from — the
  same disease is `N18.6` in ICD-10 and `GB61.5` in ICD-11.
- **Never type an ICD code from memory.** The catalog is *generated* from WHO's
  published MMS linearization into `app/data/icd11_mms.tsv.gz` (35,339 codes,
  370 KB) by `scripts/build_icd11_catalog.py`. G6PD deficiency is `3A10.00`,
  which is not what anyone guesses. `tests/test_icd11_catalog.py` fails the
  build if a hand-written alias points at a code that is not in the file.
- Search must survive what patients actually type. Each of these returned
  **zero** results before it was handled: word order ("diabetes mellitus type
  2" vs WHO's "Type 2 diabetes mellitus"), lay terms ("ESRD", "G6PD"), and US
  spelling — WHO writes "haemodialysis" and "tumour", and **867 titles** carry a
  spelling a US patient will not type.
- **The client never decides what a code means.** The API verifies the code
  against the catalog (a 4-character stem code typo is usually still
  code-*shaped*, so format checks alone pass `ZZ99.9`) and fills `icd11_title`
  server-side, discarding any title the client sent.
- A patient holds **many** conditions, one row each. All three clients ask for
  `limit=1000`; the endpoint defaults to 100, and a truncated page hides
  conditions exactly the way a `LIMIT` reported as a count does.

## 3ae. AI endpoints: never gate on a provider-specific key

Three dashboard AI surfaces were dead in production for 27 days. Two causes,
told apart by latency in the Cloud Run logs — 80ms vs 99s. Always look at
latency first: it separates a hard gate from a timeout.

- **Do not ask "is `OPENAI_API_KEY` set?"** `AIPersonalizationEngine` defaulted
  to `provider="openai"` and `/personalization/*` gated on
  `if not ai_engine.api_key` → 503 "AI service is not configured". Prod's LLM is
  **Ollama, which needs no key**, so that check could never pass there. Every
  call already routed through `alafia_chat`; the field was vestigial. §3 already
  says provider strategy is a backend concern — that applies to the backend's
  own readiness checks, not just to clients.
- **"Unavailable" usually means "slower than the client".** Nothing was down:
  Ollama answered `POST /api/chat` with **200 in 1m38s** at ~51 tok/s for ~2,600
  tokens. The browser aborted at the 30s axios default. Keep the ladder ordered,
  longest last, and never let two rungs be equal:

      client AI_TIMEOUT_MS 285s < OLLAMA_TIMEOUT 290s < Cloud Run 300s < Ollama 600s

  **And check the rung is actually read.** `OllamaAdapter` took
  `timeout: float = 120.0` and never looked at `OLLAMA_TIMEOUT`, while
  `base_url` and `model` both read theirs — every call site is
  `OllamaAdapter()` with no argument, so production's configured 300 was
  silently discarded and the real limit was 120s. These prompts take 98-121s,
  so requests died just past the boundary and reported `ReadTimeout` on a model
  that was still working. **That looked like an outage three separate times in
  one day.** A setting that is configured, documented in `deploy.sh`, and
  ignored is worse than one never offered.

  Use `AI_TIMEOUT_MS` from `services/api.js` for any LLM-backed call; the 30s
  default is for CRUD. MealPlanner had 300000 — *equal* to Cloud Run's ceiling,
  so client and server could abort together.
- **Distinguish 503 from 502.** Upstream unreachable ≠ upstream returned junk.
  Both used to collapse into one message that sent us hunting a healthy service.
- **An error message must never be blank.** The provider chain formatted its
  failure as `last: {exc}` — and `str(httpx.ReadTimeout(''))` is `''`, so the
  most likely failure of all rendered as `all providers failed (last: )`. Name
  the exception *type*. §3aa's "an error is not an empty state", applied to the
  error text itself.
- Where a **template fallback exists** (meal-plan, exercise-plan) returning
  `None` is correct — the user still gets a plan — but **log why**, or a
  month-long outage is indistinguishable from "the template was fine".
- `/personalization` and `/planners` had **zero tests**. That is how this
  survived 696 passing ones. `tests/test_ai_endpoints_availability.py` pins the
  boundary; the deploy smoke test in DEPLOY.md still does not touch `/ai/*`.
- ⚠️ `alafia-ollama` runs **`minScale` unset, `maxScale=1`** — every cold request
  pays a GPU model load and concurrent users queue. Warming it is a standing
  cost decision (1 GPU + 8 CPU + 32Gi), not a code change.

## 3af. Mobile web had no navigation at all

The sidebar was `display: none` below 768px and **nothing replaced it** — that
was the whole "Responsive" section, and `Layout.jsx` had no hamburger, drawer or
media query. An authenticated phone user could reach no route except by typing a
URL. For a product whose patients are mostly on phones, that was the app.

- Off-canvas via `transform`, **not** `display: none` — the links stay in the
  DOM for assistive tech instead of vanishing.
- The drawer closes on navigate (or it covers the page just opened), on backdrop
  tap and on Escape; body scroll is locked while open.
- **Unit tests cannot catch this class of bug.** jsdom has no viewport and does
  not apply media queries, so 132 passing frontend tests were blind to it by
  construction. `e2e/mobile-nav.spec.js` runs a real browser at Pixel 7 width.
  Any layout rule behind a media query needs an e2e test at that width or it is
  untested.

## 3ag. ai_engine was written against a schema that never existed

`/personalization/*` had **five** faults stacked on top of each other, each
hidden by the one above, each found only after fixing its predecessor:

1. `if not ai_engine.api_key` → 503 (§3ae) — asked for an OpenAI key prod never has
2. `db.query()` on an `AsyncSession` — the router is sync throughout, so it takes
   `get_sync_db`; a `db: Session` annotation converts nothing
3. **eleven wrong column names** — `NutritionLog.consumed_at`, `carbohydrates_g`,
   `FitnessLog.performed_at`, `SleepLog.bedtime`, `MoodEntry.recorded_at`,
   `SymptomLog.started_at`/`severity_level`, `VitalsLog.recorded_at`/`systolic_bp`,
   `Medication.status`
4. `json.loads(user.allergies)` — those fields are **comma-separated text**
   ("Penicilin, Latex, Heparine"); the Profile screen's own placeholder says so
5. a 120s timeout ignoring `OLLAMA_TIMEOUT` (§3ae)

Two lessons worth more than the fixes:

- **Do not debug a never-executed path one deploy at a time.** Drive it locally
  against the dev copy of prod until it completes. That found faults 3 and 4 in
  minutes after two production round-trips found one each.
- **A static check beats behavioural tests for this.** Every `Model.attribute`
  in a module must exist on that model — see
  `tests/test_ai_endpoints_availability.py`. It catches all eleven for free;
  stubbing the engine skips right past `_build_user_context`, which is where the
  queries live.

## 3b. Admin console

Single-operator console for dew@6igma.com at **`/minister`** on the app host
(`/admin` redirects there; the API namespace stays `/api/v1/admin/*`). Full
detail in **`ADMIN_CONSOLE.md`**.

- Authorization is `require_admin` (`app/core/admin_auth.py`) on every
  `/api/v1/admin/*` route. **Neither the path nor a hostname is security** —
  never add a routing rule and assume it protects anything. A dedicated host was
  built and removed: it needed DNS + a domain mapping and protected nothing.
- `is_superuser` alone does NOT grant access; the gate is the `ADMIN_EMAILS`
  allowlist plus an active account. A leftover test account in this database has
  `is_superuser=true`.
- Non-admins get 404 (not 403) so the console's existence is not confirmed.
- `/auth/login` early-returns on the shared-identity branch before the local
  password path. Anything that must happen on every login (like the `last_login`
  stamp) has to be wired into BOTH branches.

## 3c. Nutrition saves are asynchronous

A meal is persisted and returned **immediately**; nutrients are filled in
afterwards by a background task. Estimation costs seconds (USDA per item,
branded lookup, LLM fallback) and used to run inside the save — a 10-item meal
exceeded the web client's 30s timeout and, because the request never committed,
**the user lost the meal they had typed**.

- `nutrition_logs.nutrient_status`: `pending | done | failed | skipped`. All
  three clients show "estimating…" for `pending` rather than a blank, which
  reads as zero calories. Web polls only while something is pending.
- Multi-item meals MUST go through `estimate_meal_nutrients()`, not
  `estimate_nutrients()`. The single-food path merges matches by **summing
  per-100 g densities**; for a list that yields an impossible number (1978
  kcal/100 g, above pure fat) which the plausibility band then rejects, sending
  the request to the slow AI fallback.
- The background worker gets its **own DB session** — the request's session is
  closed by the time it runs — and never raises: a failed lookup becomes
  `nutrient_status="failed"`, never a broken save.

## 3d. Email

**Resend** (HTTPS API) is the provider; SMTP is the fallback for self-hosting.
Credentials live in `smtp.md`, which is **gitignored** — like `api_keys.md`, it
was one `git add .` from being committed.

- `RESEND_API_KEY` set → Resend. Else SMTP. Else `smtp_configured()` is False and
  **signup refuses in production** rather than issuing an account nobody can
  verify.
- The HTTPS API is preferred over SMTP on Cloud Run: no outbound mail ports, no
  STARTTLS negotiation, and a real error body. That body is how we learned the
  sending domain was unverified — SMTP would have given an opaque failure.
- ✅ **`alafia.app` is verified in Resend** — DKIM and SPF are published in Cloud
  DNS zone `alafia-app`, and delivery to an external inbox is confirmed.
  Production sends as `noreply@alafia.app`.
- ⚠️ Check that from **DNS**, not the API: the production key is send-only, so
  `GET /domains` returns `401 restricted_api_key` — an error that reads exactly
  like "no domains verified" if you do not look at the status code.
  `dig +short TXT resend._domainkey.alafia.app`

## 3e. Finding people is not browsing people

`GET /messaging/recipients` backs the compose form. It exists because the form
used to ask for **"Member IDs (comma-separated)"** — an internal handle nobody
knows about their own nephrologist.

> **A complete identifier resolves anyone. A partial name resolves only a shared
> contact.** Relaxing the second half turns a compose box into a browsable
> directory of every patient on the platform.

- **Shared contact** means an active `DataGrant` in either direction, a
  conversation you are both still in, or a follow edge. Sharing labs with
  someone is the strongest form of it and is the reason the rule is not just
  "people you already message".
- Contact details come back **masked** (`d•••@6igma.com`) unless the caller
  typed the identifier — so scraping your own contact list yields no addresses.
  The mask is fixed-width on purpose; padding to the real length leaks it.
- The route is rate limited (`RATE_LIMIT_LOOKUP`) because exact-email matching
  is inherently an account-existence oracle. That is true of every "invite by
  email" feature; the limit is what keeps it from being a bulk one.
- Phone matching compares against a small set of stored forms rather than
  `regexp_replace`, so it does not silently become Postgres-only.
- `tests/test_messaging_recipients.py` pins the boundary — a stranger's name
  returns nothing, a near-miss email returns nothing.
- **Not indexed yet, deliberately.** `lower(email)` cannot use `ix_users_email`,
  and `conversation_members.user_id` has no index of its own (the unique
  constraint indexes `conversation_id` first). At 81 users and 2 member rows
  that is a sub-millisecond scan. If `users` reaches the low thousands, add
  `lower(email)` as a functional index — `ws_messaging.py` and
  `ws_telehealth.py` already filter the same way and would benefit too.

`member_ids` are resolved to active users before any `conversation_members` row
is written. Without that a typo produced a conversation with a member pointing
at nobody: it looked created, and the recipient never heard about it.

## 4. Running things locally — **in Docker**

> **All dev runs in containers.** Not host `npm`, not host `python`. The DB
> tooling already worked this way (pinned images, nothing installed on the host);
> the app and its test runners now do too, so the toolchain cannot drift between
> machines or between you and CI.

```bash
cd WEB

# App (backend :8005, identity :8100, db :5435, prod-build frontend :8080)
docker compose up -d

# Frontend dev server with HMR — THIS is the one for frontend work
docker compose --profile dev up frontend-dev        # → http://localhost:5173

# Tests
docker compose --profile test run --rm frontend-test   # vitest      → 105
docker compose --profile test run --rm e2e             # playwright  → 18
docker compose --profile test run --rm backend-test    # pytest      → 571
```

- **`frontend` on :8080 is not a dev server.** It is nginx serving a `dist/`
  baked at image-build time. Use `frontend-dev` on :5173 for frontend work.

  Refreshing it takes **two** steps, and the build alone is the trap:

  ```bash
  docker compose build frontend     # bakes a new dist/ into the image
  docker compose up -d frontend     # recreates the container from that image
  ```

  A running container keeps serving the image it started with, so after only the
  build, `docker compose ps` says `Up`, the build says it succeeded, and :8080
  still serves the old bundle — for days. Verify by asking the served asset, not
  the build log: `curl -s localhost:8080/ | grep -oE '/assets/index-[^"]+\.js'`
  and grep that chunk for a string your change added.
- `frontend-dev` proxies `/api` → `http://backend:8000` via
  `VITE_API_PROXY_TARGET`. Inside a container `localhost` is that container, so
  the service name is required.
- Vite's host check rejects unknown `Host` headers with a 403 "Blocked request",
  which renders as a blank page and an empty `<title>`. Service names reached
  across the compose network must be in `server.allowedHosts` /
  `preview.allowedHosts` (`vite.config.js`).
- macOS bind mounts deliver no inotify events, so HMR needs polling —
  `VITE_POLL=1` in the compose service.
- The e2e suite runs against `frontend-preview` (a real build), never the dev
  server: vite compiles lazy route chunks on first request, and with parallel
  workers that compile lands inside whichever spec got there first, failing a
  different one each cold run.

  **`frontend-preview` builds at container START.** A long-running one serves a
  stale `dist/` exactly like `:8080` does, so a green suite can be testing code
  you never wrote. `docker compose --profile test up -d --force-recreate
  frontend-preview` before trusting a pass, and confirm the served bundle
  contains your change rather than reading the build log.
- **An e2e spec that does not mock the chrome endpoints is racing a logout.**
  `notifications/unread-count`, `subscription/status`, `ehr/connections` and
  `auth/refresh` 401 when unmocked; the axios interceptor reads that as a dead
  session and redirects to `/login` mid-test. Specs that assert before the
  redirect lands pass by luck — adding one lazy route chunk was enough to lose
  the race and fail three *unrelated* Nutrition/Labs specs, which looks exactly
  like a regression somewhere else. Use `mockAppChrome()` from
  `e2e/helpers.js`. Confirm a fix is not masking anything by running the
  hardened spec at HEAD too.
- **The Playwright image tag must equal the `@playwright/test` version**
  (`1.59.1` in both `package.json` and `docker-compose.yml`), or the runner looks
  for a browser build the image does not contain.
- iOS builds cannot be containerised (Xcode is macOS-only) and Android/gradle is
  still on the host — those two are the only sanctioned exceptions.

Other notes:

- `greenlet` is required by SQLAlchemy's async engine and is **not** pulled in
  automatically on Python 3.13. Without it every DB route 500s.
- Backend docs are at `/api/docs` (only when `DEBUG`), routes under `/api/v1`.
- `ML/src/alafia_model` is the canonical ALAFIAModel source; `deploy.sh` vendors
  it into the backend image at build time. Edit it there, not in a copy.

## 5. Known drift to fix (as of 2026-08-22)

- **Head is `nn001_condition_icd11`**, applied to dev and to prod
  (2026-08-22, `mm001_dialysis_coefficients -> nn001_condition_icd11`).
  This line is dated because it goes stale: **ask `alembic heads`, never a doc
  and never a grep.** DEPLOY.md claimed prod sat at `cc002_reconcile_drift`
  while it was actually on `mm001` — four weeks out of date, and only the
  migration job's own output settled it.
- ⚠️ **Dev parity is unverified since the ICD-11 work.** Reads were run against
  the dev copy while debugging, and a handful of test conditions were created
  and deleted through the API. Run `scripts/db/verify_parity.sh` before trusting
  dev for anything, and re-pull rather than hand-editing a difference.
- **The migration graph has exactly ONE head** — verified with `alembic heads`,
  which is the only trustworthy way to ask. A hand-rolled scan reported five
  because many revisions use the annotated form
  `down_revision: Union[str, None] = '…'`, which a naive `^down_revision\s*=`
  regex misses, making real parents look like heads. Never grep for this; run
  `alembic heads`.
- `WORKLOG.md` has one stale line (~1797) describing three Cloud Run services in
  `europe-west1`; `deploy/gcp/config.env` (authoritative) says **`us-east4`** /
  `alafia-db-va`. The europe-west1 *images* still exist in Artifact Registry and
  were deliberately kept — do not treat their presence as evidence of the region.
- ✅ **`alafia-ollama` scales to ZERO, deliberately** (`minScale` unset,
  `maxScale=1`). Decided 2026-08-22: **cost over latency.** Keeping 1 GPU +
  8 CPU + 32 Gi warm would cost roughly $500/month to remove a cold start.
  Do not "fix" the cold start by setting `minScale` — that is the trade, not an
  oversight.

  What the choice costs, measured: a cold call pays a model load (~77 s) on top
  of generation (up to 172 s) — about 249 s. The timeout ladder is sized for
  that path, so **every rung must clear ~250 s and none may equal another**:

      client AI_TIMEOUT_MS 285s  <  OLLAMA_TIMEOUT 290s  <  Cloud Run 300s

  The client used to sit at 240s and cut off a cold request the server would
  have completed, and `OLLAMA_TIMEOUT` used to be 300 — equal to Cloud Run, so
  the backend's own limit could never fire first.

## 5a. Deploying

Runbook: **`DEPLOY.md`**. Two things that will bite:

- **Two-step signup is gated OFF in production** (`TWO_STEP_SIGNUP_REQUIRED=false`
  in `deploy.sh`). Turning it on closes registration until email works — see the
  checklist in DEPLOY.md. Do not flip it because the code "looks ready".
- **The sending domain is verified** (`alafia.app`, DKIM+SPF in Cloud DNS), so
  production mail reaches arbitrary recipients. Two-step signup is still gated
  off for the separate reasons in DEPLOY.md.

`deploy.sh` mounts a secret only if it exists AND grants the runtime service
account access from a second list — both must name it, or the deploy fails at
mount time.

## 6. Reporting

State what was actually run and what wasn't. "Builds" ≠ "works". If a suite
couldn't run, say so and why — don't imply coverage that doesn't exist.
