# ALAFIA — Google Cloud deployment (web/API track)

Ship the backend (FastAPI) + frontend (React SPA) + shared PQC identity service to
**Cloud Run**, backed by **Cloud SQL** (PostgreSQL 16), with all secrets in
**Secret Manager**. One public origin (the frontend) proxies `/api` + `/ws` to the
backend, so the CSRF + refresh-token cookies stay same-site.

```
Browser ──▶ frontend (Cloud Run, nginx)  ──proxy /api,/ws──▶ backend (Cloud Run, FastAPI)
Mobile  ─────────────────────────────────────────────────▶ backend (Cloud Run)  ──▶ Cloud SQL
                                                             identity (Cloud Run) ──▶ Cloud SQL
```

## What you need first (owner actions — I can't do these for you)

- A **GCP project with billing enabled**, and `gcloud` logged in: `gcloud auth login`.
- **Docker running** locally (builds the images; this repo already builds on Docker).
- Sign the **HIPAA BAA** in the Google Cloud console before real PHI lands (free, self-service).

## Steps

```bash
cd deploy/gcp
cp config.env.example config.env        # set PROJECT_ID, REGION, sizing
```

**1. Generate the identity signing keys** (hybrid Ed25519 + ML-DSA-65 — needs liboqs,
so they're generated *inside* the identity image, then stored as a secret):

```bash
mkdir -p keys
docker compose -f ../../WEB/docker-compose.yml run --rm --no-deps \
  -v "$PWD/keys:/out" identity python -m scripts.generate_keys /out/identity_keys.json
gcloud secrets create identity-keys --data-file=keys/identity_keys.json   # back this up; keep it OUT of git
```

**2. Provision** (APIs, Artifact Registry, Cloud SQL, secrets — idempotent):

```bash
./provision.sh
```

**3. Deploy** (build+push images → identity → migrate → backend → frontend):

```bash
./deploy.sh
```

It prints the **App URL** (frontend), the **API URL** (what the mobile apps point at),
and the internal identity URL. Smoke test:

```bash
curl -fsS "<APP_URL>/api/v1/subscription/plans"     # → the $12/$14 pricing catalog
```

Then open the App URL, register, and confirm login works (identity SSO) end to end.

**4. Custom domain + TLS** (optional, recommended): map a domain to the frontend
service — `gcloud run domain-mappings create --service alafia-frontend --domain app.yourdomain.com`
— Cloud Run provisions a managed cert. Re-run `deploy.sh` so `PUBLIC_WEB_URL` picks
up the custom domain, or set it directly on the backend service.

## Going live on subscriptions (fill secrets, no code change)

The web app deploys fine **now** — with blank provider keys and `DEBUG=false`, the
paid rails return `503` (never a fake charge). Flip each rail live by putting its real
value in Secret Manager, then re-running `deploy.sh` (or `gcloud run services update`):

```bash
printf 'sk_live_…'   | gcloud secrets versions add stripe-secret-key --data-file=-
printf 'price_…'     | gcloud secrets versions add stripe-price-id --data-file=-
printf 'whsec_…'     | gcloud secrets versions add stripe-webhook-secret --data-file=-
# …paypal-*, apple-shared-secret likewise
```

- Create the recurring **$12/mo** price in Stripe and the **$12/mo** plan in PayPal.
- Point the Stripe webhook at `<APP_URL>/api/v1/subscription/webhook/stripe` and
  PayPal at `…/webhook/paypal` (both are signature-verified, CSRF-exempt).
- Google Play / Apple ($14/mo) are wired in the **mobile track** (separate runbook).

## Deferred by design (not needed to go live on web)

| Piece | Status on this deploy | To enable |
|---|---|---|
| **LLM / AI** (chat, vision, meal planner) | Returns a graceful `503` — no GPU attached | Point `OLLAMA_BASE_URL` at a GPU VM (GKE L4 node pool) or set `OPENAI_API_KEY` |
| **Redis** (live messaging/telehealth WS) | WS managers skip; REST works | Add Memorystore, set `REDIS_URL` |
| **Blockchain anchoring** (Anvil) | Best-effort; anchoring lazy | Run Anvil on a small VM, set `CHAIN_NODE_URL` |
| **Firebase sync + geocoder** | **Off** (in-process cron can't run on an autoscaled service) | Cloud Scheduler → a dedicated Cloud Run **job** |
| **Email** (password reset) | No-op (blank SMTP) | Set `SMTP_*` (e.g. SendGrid); AWS SES if you also use AWS |
| **Media storage** | Stays in Postgres (`image_base64`) | Set `S3_*` (GCS via the S3-compatible endpoint or a bucket) |

## Notes / gotchas baked into the scripts

- Backend is pinned to **exactly one always-on instance** (`min=max=1`) because it
  hosts in-process schedulers; the schedulers themselves are shipped **disabled**.
  Scale out only after moving them to Cloud Scheduler + a job.
- Images build `--platform linux/amd64` (dev Macs are arm64; Cloud Run is amd64).
- Cloud SQL is reached over the unix socket `/cloudsql/<connName>`; the full
  `DATABASE_URL` (with password) is a Secret Manager secret, not an env literal.
- Migrations run as a one-off Cloud Run **job** (`alafia-migrate`) before the backend
  rolls out — the same `alembic upgrade head` that reaches single-head `bb002` locally.
- Identity/backend/flowsheet share `IDENTITY_MIGRATION_SECRET`; it's one secret here.

See `../../docs/IDENTITY_DEPLOYMENT.md` for identity key rotation + fail-closed details,
and `../../CLOUD_PROVIDER_COMPARISON.md` for the AWS-vs-GCP rationale.
