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

## 3aa. Clinical domains split across TWO tables

Board mechanics, the four ways this surface showed "empty" when data existed, and
how to verify it: **`CLINICIAN_BOARD.md`**.

> **Reading one table and calling it the answer silently hides clinical facts.**
> Go through **`app/services/clinical_sources.py`** — never query these models
> directly.

| Domain | Live table | The other one |
|---|---|---|
| **Conditions** | `chronic_conditions` — Conditions screen, EHR import, dialysis/chemo flowsheets | `health_conditions` — **LEGACY: zero writers anywhere in the app.** Any query against it alone returns nothing, forever. |
| **Medications** | `medication_dose_logs` — what the patient actually TOOK, written by the Medications screen | `medications` — prescriptions/profile, written by the **EHR/FHIR import** (`api/ehr.py`) and manual entry |

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
docker compose --profile test run --rm backend-test python scripts/board_sweep.py
```

Checking a single well-populated patient proved almost nothing: on this database
it left `fitness` (no rows for ANY user), `lifestyle` (data belongs to a
different user) and `pd_sessions` (empty everywhere) unexercised, and hid that
six of the seven users with nutrition data fell outside the 7-day summary window.

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
docker compose --profile test run --rm frontend-test   # vitest      → 30
docker compose --profile test run --rm e2e             # playwright  → 18
docker compose --profile test run --rm backend-test    # pytest      → 292
```

- **`frontend` on :8080 is not a dev server.** It is nginx serving a `dist/`
  baked at image-build time, so it shows stale code until
  `docker compose build frontend`. Use `frontend-dev` on :5173.
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

## 5. Known drift to fix (as of 2026-08-02)

- **Dev DB is behind prod.** Dev is stamped `bb002_add_subscriptions`; the single
  head is `dd004_nutrient_status`. Symptom seen in practice:
  `media_assets.storage_url` exists in the model but not in the dev DB, because
  migration `u001_media_s3_storage` was never applied there.
- **The migration graph has exactly ONE head** — verified with `alembic heads`,
  which is the only trustworthy way to ask. A hand-rolled scan reported five
  because many revisions use the annotated form
  `down_revision: Union[str, None] = '…'`, which a naive `^down_revision\s*=`
  regex misses, making real parents look like heads. Never grep for this; run
  `alembic heads`.
- `WORKLOG.md` still describes the DB as `europe-west1` / `alafia-db`;
  `deploy/gcp/config.env` (authoritative) says `us-east4` / `alafia-db-va`.

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
