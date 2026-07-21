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

# Runtime service account gets read access to the secrets it mounts.
SA="$(gcloud iam service-accounts list --filter='displayName:Compute Engine default' --format='value(email)' | head -1)"
for s in alafia-secret-key alafia-database-url alafia-database-url-sync \
         identity-migration-secret identity-keys \
         stripe-secret-key stripe-price-id stripe-webhook-secret \
         paypal-client-id paypal-client-secret paypal-plan-id paypal-webhook-id \
         apple-shared-secret; do
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null 2>&1 || true
done

# ── 1. Build + push images (local Docker → Artifact Registry) ─────────────────
# Docker is this project's standard build tool; a local build also lets the
# frontend use the prod Dockerfile + proxy template cleanly. (Prefer Cloud Build
# later for CI: `gcloud builds submit` with a cloudbuild.yaml.)
echo "── Building + pushing images ─────────────────────────────────"
docker build --platform linux/amd64 -t "$AR/identity:latest" "$REPO_ROOT/WEB/identity_service"
docker push "$AR/identity:latest"
docker build --platform linux/amd64 -t "$AR/backend:latest" "$REPO_ROOT/WEB/backend"
docker push "$AR/backend:latest"

# Frontend: the prod Dockerfile COPYs the proxy template from its build context,
# so stage the template into WEB/frontend for the build, then remove it.
STAGE="$REPO_ROOT/WEB/frontend"
cp frontend/nginx.conf.template "$STAGE/deploy-nginx.conf.template"
trap 'rm -f "$STAGE/deploy-nginx.conf.template"' EXIT
docker build --platform linux/amd64 -t "$AR/frontend:latest" -f frontend/Dockerfile "$STAGE"
docker push "$AR/frontend:latest"

# ── 2. Identity service ───────────────────────────────────────────────────────
echo "── Deploying identity ────────────────────────────────────────"
gcloud run deploy "$SVC_IDENTITY" --image "$AR/identity:latest" --region "$REGION" \
  --no-allow-unauthenticated --add-cloudsql-instances "$CONN" \
  --set-env-vars "IDENTITY_ENV=production,IDENTITY_DB_SCHEMA=identity,IDENTITY_KEYS_FILE=/run/keys/identity_keys.json" \
  --set-secrets "IDENTITY_DATABASE_URL=alafia-database-url:latest,IDENTITY_MIGRATION_SECRET=identity-migration-secret:latest" \
  --set-secrets "/run/keys/identity_keys.json=identity-keys:latest"
IDENTITY_URL="$(gcloud run services describe "$SVC_IDENTITY" --region "$REGION" --format='value(status.url)')"

# ── 3. DB migrations (one-off Cloud Run job on the backend image) ─────────────
echo "── Running alembic upgrade head ──────────────────────────────"
gcloud run jobs deploy alafia-migrate --image "$AR/backend:latest" --region "$REGION" \
  --add-cloudsql-instances "$CONN" \
  --set-secrets "DATABASE_URL=alafia-database-url:latest,DATABASE_URL_SYNC=alafia-database-url-sync:latest,SECRET_KEY=alafia-secret-key:latest" \
  --command alembic --args "upgrade,head"
gcloud run jobs execute alafia-migrate --region "$REGION" --wait

# ── 4. Backend (first pass — public URL not known yet) ────────────────────────
echo "── Deploying backend ─────────────────────────────────────────"
BACKEND_ENV="DEBUG=false,IDENTITY_ENABLED=true,IDENTITY_BASE_URL=${IDENTITY_URL},IDENTITY_AUDIENCE=alafia"
BACKEND_ENV="${BACKEND_ENV},SUBSCRIPTION_ENABLED=true,APPLE_ENVIRONMENT=production,PAYPAL_API_BASE=https://api-m.paypal.com"
# Schedulers OFF: in-process cron must not run on an autoscaled service.
BACKEND_ENV="${BACKEND_ENV},FIREBASE_SYNC_ENABLED=false,PRACTICE_GEOCODE_ENABLED=false"
gcloud run deploy "$SVC_BACKEND" --image "$AR/backend:latest" --region "$REGION" \
  --allow-unauthenticated --port 8000 --add-cloudsql-instances "$CONN" \
  --min-instances "$BACKEND_MIN_INSTANCES" --max-instances "$BACKEND_MAX_INSTANCES" \
  --cpu 2 --memory 2Gi --timeout 300 \
  --set-env-vars "$BACKEND_ENV" \
  --set-secrets "SECRET_KEY=alafia-secret-key:latest,DATABASE_URL=alafia-database-url:latest,DATABASE_URL_SYNC=alafia-database-url-sync:latest,IDENTITY_MIGRATION_SECRET=identity-migration-secret:latest,STRIPE_SECRET_KEY=stripe-secret-key:latest,STRIPE_PRICE_ID=stripe-price-id:latest,STRIPE_WEBHOOK_SECRET=stripe-webhook-secret:latest,PAYPAL_CLIENT_ID=paypal-client-id:latest,PAYPAL_CLIENT_SECRET=paypal-client-secret:latest,PAYPAL_PLAN_ID=paypal-plan-id:latest,PAYPAL_WEBHOOK_ID=paypal-webhook-id:latest,APPLE_SHARED_SECRET=apple-shared-secret:latest"
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
