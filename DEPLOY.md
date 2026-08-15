# Deploying ALAFIA

Runbook for shipping the web/API stack to Cloud Run. Written 2026-08-05 for the
release covering commits `ef068d8..e4f9aa9` (16 commits, prod was at `f9f7143`).

---

## ⚠️ Read this before you run anything

**Two-step signup is gated OFF for this release, deliberately.**

The code is finished and tested, but turning it on closes registration in
production until email actually works:

| | With `TWO_STEP_SIGNUP_REQUIRED=true` |
|---|---|
| `POST /auth/register` | **410 Gone** |
| `POST /auth/signup/start` | 503 if no email provider is configured. With Resend + the now-verified `alafia.app`, mail does send — so this row is no longer the blocker it was. |

`deploy.sh` therefore sets
`TWO_STEP_SIGNUP_REQUIRED=false`, so `/auth/register` keeps working exactly as it
does today. Turn it on only after the checklist in *Enabling two-step signup*.

**The sending domain IS verified.** `alafia.app` is verified in Resend, its
DKIM and SPF records are published in Cloud DNS zone `alafia-app`, and delivery
to an external inbox has been confirmed. `SMTP_FROM_EMAIL=noreply@alafia.app`.

Verify it yourself from DNS rather than from the API — the production Resend key
is **send-only**, so `GET /domains` returns `401 restricted_api_key`, which is
easy to misread as "no domains":

```bash
dig +short TXT resend._domainkey.alafia.app   # DKIM
dig +short TXT send.alafia.app                # SPF
```

---

## 0. What exists, and where

```bash
./scripts/gcp/inventory.sh      # read-only; prints everything with console links
```

| | |
|---|---|
| Project | `alafia-prod-6igma` (number `1087818475199`) — one of 22 this account can see |
| Region | `us-east4` |
| Cloud Run | `alafia-backend`, `alafia-frontend`, `alafia-identity` |
| Cloud SQL | `alafia-db-va` — Postgres 16 |
| Artifact Registry | `alafia`, `alafia-ml` |
| Domain mappings | `alafia.app` + `www` → frontend · `api.alafia.app` → backend |

**DNS lives in two different places — this is the thing that wastes an afternoon:**

| Domain | Registrar | Records edited at |
|---|---|---|
| `alafia.app` | GoDaddy | **Cloud DNS zone `alafia-app`** in `alafia-prod-6igma` — *not GoDaddy* |
| `alafia.app` | Namecheap | **Namecheap dashboard** |

GoDaddy holds only the registration and the delegation to
`ns-cloud-c1–c4.googledomains.com`. Adding an `alafia.app` subdomain is one
record in that zone plus one Cloud Run domain mapping:

<https://console.cloud.google.com/net-services/dns/zones?project=alafia-prod-6igma>

## 1. Preflight

```bash
gcloud auth login                       # not installed on the dev Mac — install first
gcloud config set project alafia-prod-6igma
cd deploy/gcp
```

Confirm the things that are easy to get wrong:

```bash
gcloud secrets list --filter="name~stripe OR name~resend OR name~smtp" --format='value(name)'
gcloud run services list --region us-east4
```

`deploy.sh` mounts a secret **only if it exists**, so a missing one is silent.
It also grants the runtime service account access — both lists must contain the
secret name or the deploy fails at mount time.

## 2. Create the email secret (once)

```bash
printf 're_xxxxxxxx' | gcloud secrets create resend-api-key --data-file=-
```

The key is in `smtp.md` (gitignored — it holds a live credential, do not commit
it). Without this, signup refuses in production rather than issuing accounts to
unverified addresses.

## 3. Deploy

```bash
./deploy.sh
```

The script, in order: builds identity + backend on Cloud Build and the frontend
locally, runs `alembic upgrade head` as a Cloud Run job, deploys backend, then
frontend, then re-points the backend at the public URL.

### What the migration job will apply

Production is at `cc002_reconcile_drift`. The chain to head is linear and every
`upgrade()` is **additive — no drops, no deletes**:

```
cc002_reconcile_drift
  → cc003_med_dose_logtime
  → dd001_food_training_samples     new table (vision corpus)
  → dd002_user_last_login           users.last_login + index
  → dd003_pending_registrations     new table (two-step signup)
  → dd004_nutrient_status           nutrition_logs.nutrient_status + index
```

`alembic heads` reports exactly one head. Verify with `alembic heads`, never by
grepping `down_revision` — many revisions use the annotated form
`down_revision: Union[str, None] = '…'`, which a naive regex misses.

## 4. Smoke test

```bash
API=https://api.alafia.app
curl -s $API/api/v1/subscription/plans | head -c 120        # 200
curl -s -o /dev/null -w '%{http_code}\n' $API/api/v1/auth/csrf-cookie   # 204
```

Then, signed in as `dew@6igma.com`:

```bash
curl -s $API/api/v1/admin/health -H "Authorization: Bearer <token>"
```

The health panel reports the DB, the **migration revision actually applied**, the
vision-corpus size, the configured AI backends and the email provider. If
`migration_revision` is not `dd004_nutrient_status`, the migration job did not
run — do not proceed.

Then open `https://alafia.app/minister` and sign in as `dew@6igma.com`.

## 5. Rollback

Cloud Run keeps revisions; traffic can be moved back in seconds:

```bash
gcloud run revisions list --service alafia-backend --region us-east4
gcloud run services update-traffic alafia-backend --region us-east4 \
  --to-revisions <previous-revision>=100
```

**The database does not roll back with it.** All migrations in this release are
additive, so an older image runs fine against the newer schema — it simply
ignores the new columns and tables. Do not run `alembic downgrade` to recover
from an app problem.

## 6. Post-deploy, still outstanding

Done since the last revision of this doc:

- ✅ **Sending domain verified.** `alafia.app` is verified in Resend, its DKIM/SPF
  records are published in Cloud DNS zone `alafia-app`, and real delivery to an
  external inbox was confirmed. `SMTP_FROM_EMAIL=noreply@alafia.app`.
- ✅ **Robot accounts deactivated in production** (78 → 23 active). Reversible via
  `deactivate_test_accounts_rollback.sql` — original emails are preserved.

These need your access and are **not done**:

1. **Replace the Android App Links fingerprint after the first Play upload.**
   `WEB/frontend/public/.well-known/assetlinks.json` currently carries the
   **upload key** SHA-256 (`B0:6D:6E:58…`, from `Android/alafia-upload.jks`). If
   Play App Signing is enabled — it is the default — Google re-signs the app with
   a *different* key, and App Links will silently fail to verify until the **app
   signing** SHA-256 from Play Console → Setup → App signing is added here. The
   file takes a list; add the new fingerprint rather than replacing, so builds
   signed with either key keep working.
2. **Pull prod down to dev** once deployed, so the two match again:
   ```bash
   scripts/db/verify_parity.sh    # expect drift until this is done
   scripts/db/pull_prod.sh
   ```

## Enabling two-step signup

Do these in order; each is checkable:

1. Verify the sending domain in Resend (§6.1).
2. Set `SMTP_FROM_EMAIL` to an address on that domain.
3. Send a test: `POST /api/v1/auth/signup/start` for an address you control, and
   confirm the mail **arrives**.
4. Redeploy with `TWO_STEP_SIGNUP_REQUIRED=true ./deploy.sh`.
5. Confirm `/auth/register` returns 410 and a full signup completes.

Step 3 is the one that matters. Everything before it can look healthy while mail
silently fails.

## What is in this release

| Area | Change |
|---|---|
| Nutrition | Saves return in ~1.5s instead of timing out; nutrients enrich in the background (`nutrient_status`) |
| Nutrition | Multi-item meals no longer sum per-100 g densities (was 1978 kcal/100 g → now 967 kcal total) |
| Vision | Meal-photo analysis on web/iOS/Android, correction capture, portion→grams, Phase 5 training corpus |
| Admin | Console at `/minister` — users, last login, token usage, app health |
| Auth | Password reset now revokes the old password (it did not); `last_login` recorded; show/hide password on all frontends |
| Email | Resend HTTPS provider with SMTP fallback |
| Signup | Two-step flow built and tested, **gated off** |
| Infra | `greenlet` added; frontend healthcheck IPv6 fix; `/fonts/inter.css` 403 fix |

Full detail in `WORKLOG.md`; subsystem docs in `ADMIN_CONSOLE.md`,
`VISION_TRAINING.md`, `scripts/db/README.md`, and the canon in `CLAUDE.md`.
