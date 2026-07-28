#!/usr/bin/env bash
# Build + deploy the ALAFIA web/API stack to Cloud Run: identity → migrate →
# backend → frontend, then a second pass to point the backend at the public URL.
# Re-runnable: each run ships the current source. Run ./provision.sh first.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.env

REPO_ROOT="$(cd ../.. && pwd)"
AR="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"

# Preflight: identity signing keys must exist (they need liboqs, so they can't be
# auto-generated here — see runbook §"Generate identity keys" / IDENTITY_DEPLOYMENT.md).
if ! gcloud secrets describe identity-keys >/dev/null 2>&1; then
  echo "ERROR: secret 'identity-keys' is missing. Generate the hybrid signing keys and store them:" >&2
  echo "  docker compose -f \$REPO_ROOT/WEB/docker-compose.yml run --rm --no-deps \\" >&2
  echo "    -v \"\$PWD/keys:/out\" identity python -m scripts.generate_keys /out/identity_keys.json" >&2
  echo "  gcloud secrets create identity-keys --data-file=keys/identity_keys.json" >&2
  exit 1
fi
CONN="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')"
gcloud config set project "$PROJECT_ID"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Runtime service account (the Compute Engine default SA, which Cloud Run uses)
# gets read access to the secrets it mounts. Derive it deterministically from the
# project number — the displayName varies and can't be filtered on reliably.
PROJ_NUM="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SA="${PROJ_NUM}-compute@developer.gserviceaccount.com"
for s in alafia-secret-key alafia-database-url alafia-database-url-sync \
         identity-migration-secret identity-keys \
         stripe-secret-key stripe-price-id stripe-webhook-secret \
         paypal-client-id paypal-client-secret paypal-plan-id paypal-webhook-id \
         apple-shared-secret; do
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null 2>&1 || true
done
# …and the ability to connect to Cloud SQL through the socket.
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${SA}" \
  --role=roles/cloudsql.client --quiet >/dev/null 2>&1 || true

# ── 1. Build + push images (set SKIP_BUILD=1 to reuse the images already in AR) ─
# backend (Rust) + identity (liboqs C) compile native code — build them on
# Cloud Build (native amd64) rather than slow local qemu emulation on an arm64 Mac.
if [ "${SKIP_BUILD:-}" != "1" ]; then
  echo "── Building identity + backend (Cloud Build) ─────────────────"
  gcloud builds submit "$REPO_ROOT/WEB/identity_service" --tag "$AR/identity:latest"
  gcloud builds submit "$REPO_ROOT/WEB/backend"          --tag "$AR/backend:latest"

  # Frontend (node, no native compile): local buildx amd64 with the prod Dockerfile,
  # which COPYs the proxy template from its build context — stage it, then remove.
  echo "── Building frontend (local buildx) ──────────────────────────"
  STAGE="$REPO_ROOT/WEB/frontend"
  cp frontend/nginx.conf.template "$STAGE/deploy-nginx.conf.template"
  trap 'rm -f "$STAGE/deploy-nginx.conf.template"' EXIT
  docker build --platform linux/amd64 -t "$AR/frontend:latest" -f frontend/Dockerfile "$STAGE"
  docker push "$AR/frontend:latest"
fi

# ── 2. Identity service ───────────────────────────────────────────────────────
echo "── Deploying identity ────────────────────────────────────────"
# Public: the backend calls it server-to-server (no Google ID token attached), and
# an IdP's endpoints (login, JWKS) are meant to be reachable. App auth still gates data.
gcloud run deploy "$SVC_IDENTITY" --image "$AR/identity:latest" --region "$REGION" \
  --allow-unauthenticated --port 8000 --add-cloudsql-instances "$CONN" \
  --set-env-vars "IDENTITY_ENV=production,IDENTITY_DB_SCHEMA=identity,IDENTITY_KEYS_FILE=/run/keys/identity_keys.json" \
  --set-secrets "IDENTITY_DATABASE_URL=alafia-database-url:latest,IDENTITY_MIGRATION_SECRET=identity-migration-secret:latest" \
  --set-secrets "/run/keys/identity_keys.json=identity-keys:latest"
IDENTITY_URL="$(gcloud run services describe "$SVC_IDENTITY" --region "$REGION" --format='value(status.url)')"

# ── 3. DB migrations (one-off Cloud Run job on the backend image) ─────────────
echo "── Running alembic upgrade head ──────────────────────────────"
gcloud run jobs deploy alafia-migrate --image "$AR/backend:latest" --region "$REGION" \
  --set-cloudsql-instances "$CONN" \
  --set-secrets "DATABASE_URL=alafia-database-url:latest,DATABASE_URL_SYNC=alafia-database-url-sync:latest,SECRET_KEY=alafia-secret-key:latest" \
  --command alembic --args "upgrade,head"
gcloud run jobs execute alafia-migrate --region "$REGION" --wait

# ── 4. Backend (first pass — public URL not known yet) ────────────────────────
echo "── Deploying backend ─────────────────────────────────────────"
BACKEND_ENV="DEBUG=false,IDENTITY_ENABLED=true,IDENTITY_BASE_URL=${IDENTITY_URL},IDENTITY_AUDIENCE=alafia"
BACKEND_ENV="${BACKEND_ENV},SUBSCRIPTION_ENABLED=true,APPLE_ENVIRONMENT=production,PAYPAL_API_BASE=https://api-m.paypal.com"
# Hard paywall: every user needs an active subscription (owner email exempt via the
# config default). Flip to false to open the app.
BACKEND_ENV="${BACKEND_ENV},SUBSCRIPTION_REQUIRED=true"
# Schedulers OFF: in-process cron must not run on an autoscaled service.
BACKEND_ENV="${BACKEND_ENV},FIREBASE_SYNC_ENABLED=false,PRACTICE_GEOCODE_ENABLED=false"
# Core secrets always mount. Provider keys mount ONLY if the secret has a value
# (an enabled version) — otherwise the rail stays unconfigured (503 in prod), which
# is the correct pre-go-live state. Add a version to a provider secret to enable it.
BACKEND_SECRETS="SECRET_KEY=alafia-secret-key:latest,DATABASE_URL=alafia-database-url:latest,DATABASE_URL_SYNC=alafia-database-url-sync:latest,IDENTITY_MIGRATION_SECRET=identity-migration-secret:latest"
add_secret_if_present() {  # ENV_VAR  SECRET_NAME
  if gcloud secrets versions list "$2" --filter='state=enabled' --format='value(name)' --limit=1 2>/dev/null | grep -q .; then
    BACKEND_SECRETS="${BACKEND_SECRETS},$1=$2:latest"
    echo "   + mounting $1 (configured)"
  fi
}
add_secret_if_present STRIPE_SECRET_KEY       stripe-secret-key
add_secret_if_present STRIPE_PRICE_ID         stripe-price-id
add_secret_if_present STRIPE_PRICE_ID_ANNUAL  stripe-price-id-annual
add_secret_if_present STRIPE_WEBHOOK_SECRET   stripe-webhook-secret
add_secret_if_present PAYPAL_CLIENT_ID        paypal-client-id
add_secret_if_present PAYPAL_CLIENT_SECRET    paypal-client-secret
add_secret_if_present PAYPAL_PLAN_ID          paypal-plan-id
add_secret_if_present PAYPAL_PLAN_ID_ANNUAL   paypal-plan-id-annual
add_secret_if_present PAYPAL_WEBHOOK_ID       paypal-webhook-id
add_secret_if_present APPLE_SHARED_SECRET     apple-shared-secret
gcloud run deploy "$SVC_BACKEND" --image "$AR/backend:latest" --region "$REGION" \
  --allow-unauthenticated --port 8000 --add-cloudsql-instances "$CONN" \
  --min-instances "$BACKEND_MIN_INSTANCES" --max-instances "$BACKEND_MAX_INSTANCES" \
  --cpu 2 --memory 2Gi --timeout 300 \
  --set-env-vars "$BACKEND_ENV" \
  --set-secrets "$BACKEND_SECRETS"
BACKEND_URL="$(gcloud run services describe "$SVC_BACKEND" --region "$REGION" --format='value(status.url)')"
BACKEND_HOST="${BACKEND_URL#https://}"

# ── 5. Frontend (proxies /api,/ws to the backend host) ────────────────────────
echo "── Deploying frontend ────────────────────────────────────────"
gcloud run deploy "$SVC_FRONTEND" --image "$AR/frontend:latest" --region "$REGION" \
  --allow-unauthenticated --port 8080 \
  --min-instances "$FRONTEND_MIN_INSTANCES" --max-instances "$FRONTEND_MAX_INSTANCES" \
  --set-env-vars "BACKEND_HOST=${BACKEND_HOST}"
FRONTEND_URL="$(gcloud run services describe "$SVC_FRONTEND" --region "$REGION" --format='value(status.url)')"

# ── 6. Backend second pass — now it knows the public origin ───────────────────
echo "── Wiring backend → public URL (${FRONTEND_URL}) ─────────────"
gcloud run services update "$SVC_BACKEND" --region "$REGION" \
  --update-env-vars "PUBLIC_WEB_URL=${FRONTEND_URL},CORS_ORIGINS=[\"${FRONTEND_URL}\"],EHR_REDIRECT_URI=${FRONTEND_URL}/ehr/callback"

echo ""
echo "✅ Deployed."
echo "   App:      ${FRONTEND_URL}"
echo "   API:      ${BACKEND_URL}   (mobile apps point here)"
echo "   Identity: ${IDENTITY_URL}  (internal)"
echo ""
echo "Smoke: curl -fsS ${FRONTEND_URL}/api/v1/subscription/plans"
