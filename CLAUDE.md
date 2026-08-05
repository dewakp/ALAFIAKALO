# ALAFIA — working canon

Read this before touching anything. It exists because context was being
re-derived from scratch each session, and each re-derivation drifted.

---

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

## 3b. Admin console

Single-operator console for dew@6igma.com at **minister.alafia.com**, and at
**`/minister`** in dev (`/admin` redirects there; the API namespace stays
`/api/v1/admin/*`). Full detail in **`ADMIN_CONSOLE.md`**.

- Authorization is `require_admin` (`app/core/admin_auth.py`) on every
  `/api/v1/admin/*` route. **The hostname is routing, not security** — never add
  an nginx rule and assume it protects anything.
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
- ⚠️ **No domain is verified on the Resend account yet**, so production email
  cannot send to arbitrary recipients. See `ADMIN_CONSOLE.md`.

## 4. Running things locally

```bash
# Python env (backend, ML, tooling) — NOT a repo venv
/Users/woleakpose/Developer/dev_env/bin/python

# Backend (needs the dev DB up: cd WEB && docker compose up -d db)
cd WEB/backend && PYTHONPATH=$PWD/../../ML/src \
  /Users/woleakpose/Developer/dev_env/bin/python -m uvicorn app.main:app --port 8005

# Web
cd WEB/frontend && npm run dev          # needs node on PATH: ~/.nvm/versions/node/v24.12.0/bin
```

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

## 6. Reporting

State what was actually run and what wasn't. "Builds" ≠ "works". If a suite
couldn't run, say so and why — don't imply coverage that doesn't exist.
