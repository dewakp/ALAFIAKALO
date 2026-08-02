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

- **Dev DB is behind prod.** Dev is stamped `bb002_add_subscriptions`; prod was
  stamped `cc002_reconcile_drift` and `cc003_med_dose_logtime` exists.
- **The alembic graph has 5 heads** (`9c5e7b8c3d2a`, `c6d7e8f9a0b1`,
  `cc003_med_dose_logtime`, `b2c3d4e5f6a8`, `a3b4c5d6e7f8`). `alembic upgrade
  head` is ambiguous until these are merged with `alembic merge`.
- `WORKLOG.md` still describes the DB as `europe-west1` / `alafia-db`;
  `deploy/gcp/config.env` (authoritative) says `us-east4` / `alafia-db-va`.

## 6. Reporting

State what was actually run and what wasn't. "Builds" ≠ "works". If a suite
couldn't run, say so and why — don't imply coverage that doesn't exist.
