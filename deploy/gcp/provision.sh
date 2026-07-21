#!/usr/bin/env bash
# One-time GCP provisioning for the ALAFIA web/API stack: APIs, Artifact Registry,
# Cloud SQL, and the app secrets in Secret Manager. Idempotent — safe to re-run.
#
#   gcloud auth login          # you run this (interactive)
#   cp config.env.example config.env && $EDITOR config.env
#   ./provision.sh
set -euo pipefail
cd "$(dirname "$0")"
source ./config.env

gcloud config set project "$PROJECT_ID"

echo "── Enabling APIs ─────────────────────────────────────────────"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com

echo "── Artifact Registry ─────────────────────────────────────────"
gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1 || \
gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker --location="$REGION" \
  --description="ALAFIA container images"

echo "── Cloud SQL (PostgreSQL 16) ─────────────────────────────────"
if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  # --edition=ENTERPRISE is required for shared-core/small tiers (db-g1-small);
  # ENTERPRISE_PLUS (the new default) only accepts db-perf-optimized-* tiers.
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_16 --edition=ENTERPRISE --tier="$SQL_TIER" --region="$REGION" \
    --storage-auto-increase --backup --enable-point-in-time-recovery
fi
gcloud sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" >/dev/null 2>&1 || \
gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"

# DB password: generate once, set on the SQL user, and store the FULL connection
# URLs as secrets (Cloud Run can't template a password into a URL, so the whole
# URL is the secret). Cloud Run reaches Cloud SQL over a unix socket at
# /cloudsql/<connName>, which asyncpg/psycopg2 take via ?host=.
if ! gcloud secrets describe alafia-database-url >/dev/null 2>&1; then
  DB_PASS="$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"
  gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASS" 2>/dev/null || \
  gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASS"
  CONN="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')"
  SOCK="/cloudsql/${CONN}"
  printf 'postgresql+asyncpg://%s:%s@/%s?host=%s' "$DB_USER" "$DB_PASS" "$DB_NAME" "$SOCK" \
    | gcloud secrets create alafia-database-url --data-file=-
  printf 'postgresql://%s:%s@/%s?host=%s' "$DB_USER" "$DB_PASS" "$DB_NAME" "$SOCK" \
    | gcloud secrets create alafia-database-url-sync --data-file=-
fi

echo "── App secrets (Secret Manager) ──────────────────────────────"
# Create-if-absent; never overwrites an existing value (rotate manually).
create_secret_random () {  # name, byte-length
  gcloud secrets describe "$1" >/dev/null 2>&1 || \
  { openssl rand -base64 "$2" | gcloud secrets create "$1" --data-file=- ; }
}
create_secret_random alafia-secret-key 48          # backend SECRET_KEY (JWT)
create_secret_random identity-migration-secret 48  # shared IdP<->backend migration secret
create_secret_random flowsheet-secret-key 48       # (only if you deploy FlowSheet)

# Identity signing keys (hybrid Ed25519 + ML-DSA-65). Generated inside the
# identity image (it has liboqs) — see the runbook §2; stored as a secret here if
# you already have the JSON locally.
if [ -f identity_keys.json ] && ! gcloud secrets describe identity-keys >/dev/null 2>&1; then
  gcloud secrets create identity-keys --data-file=identity_keys.json
fi

echo "── Provider keys (subscriptions) — placeholders ──────────────"
# These start EMPTY. In DEBUG=false the rails raise 503 until you set real keys,
# so the web app deploys fine now and you fill these before charging cards.
for s in stripe-secret-key stripe-price-id stripe-webhook-secret \
         paypal-client-id paypal-client-secret paypal-plan-id paypal-webhook-id \
         apple-shared-secret; do
  gcloud secrets describe "$s" >/dev/null 2>&1 || printf '' | gcloud secrets create "$s" --data-file=-
done

echo "✅ Provisioning complete. Next: ./deploy.sh"
