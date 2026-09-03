#!/usr/bin/env bash
# Build + deploy the ALAFIA web/API stack to Cloud Run: identity → migrate →
# backend → frontend, then a second pass to point the backend at the public URL.
# Re-runnable: each run ships the current source. Run ./provision.sh first.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.env

REPO_ROOT="$(cd ../.. && pwd)"
AR="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"

# Prod config (versioned defaults; override in config.env). Making these part of
# the pipeline is what keeps prod == a dev commit — no post-deploy hand-patching.
: "${PUBLIC_DOMAIN:=https://alafia.app}"                 # apex the frontend/API serve on
: "${OLLAMA_URL:=https://alafia-ollama-1087818475199.us-central1.run.app}"  # private GPU LLM
GIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"

# Preflight 0: gcloud itself. The SDK is commonly installed outside PATH (e.g.
# ~/google-cloud-sdk/bin), and every check below hides stderr — so a missing
# binary used to surface as "secret 'identity-keys' is missing", sending you to
# create a secret that already existed. Fail on the real cause instead.
if ! command -v gcloud >/dev/null 2>&1; then
  for c in "$HOME/google-cloud-sdk/bin" "/opt/homebrew/share/google-cloud-sdk/bin" \
           "/usr/local/share/google-cloud-sdk/bin"; do
    [ -x "$c/gcloud" ] && { PATH="$c:$PATH"; export PATH; break; }
  done
fi
command -v gcloud >/dev/null 2>&1 || {
  echo "ERROR: gcloud is not on PATH and was not found in the usual install locations." >&2
  echo "  Add the SDK's bin/ to PATH, or set GCLOUD_BIN, then re-run." >&2
  exit 1; }

# Preflight 1: authenticated? Otherwise every describe below fails "not found".
gcloud auth print-access-token >/dev/null 2>&1 || {
  echo "ERROR: gcloud is not authenticated (or the token expired). Run:" >&2
  echo "  gcloud auth login && gcloud auth application-default login" >&2
  exit 1; }

# Preflight 2: identity signing keys must exist (they need liboqs, so they can't be
# auto-generated here — see runbook §"Generate identity keys" / IDENTITY_DEPLOYMENT.md).
# --project is explicit: the ambient config project is not guaranteed to be ours.
if ! gcloud secrets describe identity-keys --project "$PROJECT_ID" >/dev/null 2>&1; then
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
# LLM round-robin provider keys (ML/src/alafia_model/registry/providers.py).
# ENV_VAR:secret-name — each mounts ONLY when its secret exists, so a provider
# lights up the moment you `gcloud secrets create` its key: no code change, no
# app release (AI stays backend-driven — see canon).
LLM_PROVIDER_SECRETS="\
GEMINI_API_KEY:gemini-api-key GROQ_API_KEY:groq-api-key CEREBRAS_API_KEY:cerebras-api-key \
SAMBANOVA_API_KEY:sambanova-api-key MISTRAL_API_KEY:mistral-api-key OPENROUTER_API_KEY:openrouter-api-key \
GITHUB_MODELS_TOKEN:github-models-token NVIDIA_API_KEY:nvidia-api-key DASHSCOPE_API_KEY:dashscope-api-key \
ZHIPU_API_KEY:zhipu-api-key CLOUDFLARE_API_TOKEN:cloudflare-api-token CLOUDFLARE_ACCOUNT_ID:cloudflare-account-id \
DEEPSEEK_API_KEY:deepseek-api-key MOONSHOT_API_KEY:moonshot-api-key TOGETHER_API_KEY:together-api-key \
FIREWORKS_API_KEY:fireworks-api-key DEEPINFRA_API_KEY:deepinfra-api-key XAI_API_KEY:xai-api-key \
OPENAI_API_KEY:openai-api-key PERPLEXITY_API_KEY:perplexity-api-key ANTHROPIC_API_KEY:anthropic-api-key"

for s in alafia-secret-key alafia-database-url alafia-database-url-sync \
         identity-migration-secret identity-keys \
         stripe-secret-key stripe-price-id stripe-price-id-annual stripe-webhook-secret \
         apple-shared-secret alafia-pseudonym-secret \
         resend-api-key smtp-host smtp-user smtp-password smtp-from-email; do
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null 2>&1 || true
done
# …and each LLM provider key (binding is a no-op until the secret is created).
for pair in $LLM_PROVIDER_SECRETS; do
  gcloud secrets add-iam-policy-binding "${pair##*:}" --member="serviceAccount:${SA}" \
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

  # Vendor the ALAFIAModel package (ML/src/alafia_model) into the backend build
  # context — it lives outside WEB/backend, so without this the provider
  # round-robin / alafia_chat path is absent from the image. Staged for the build,
  # removed after (canonical home stays ML/src). alafia_model_service adds the
  # backend root to sys.path so the vendored copy imports in the container.
  VENDORED="$REPO_ROOT/WEB/backend/alafia_model"
  STAGE="$REPO_ROOT/WEB/frontend"
  rm -rf "$VENDORED"
  cp -R "$REPO_ROOT/ML/src/alafia_model" "$VENDORED"
  trap 'rm -rf "$VENDORED"; rm -f "$STAGE/deploy-nginx.conf.template"' EXIT
  gcloud builds submit "$REPO_ROOT/WEB/backend"          --tag "$AR/backend:latest"

  # Frontend (node, no native compile): local buildx amd64 with the prod Dockerfile,
  # which COPYs the proxy template from its build context — stage it, then remove.
  echo "── Building frontend (local buildx) ──────────────────────────"
  cp frontend/nginx.conf.template "$STAGE/deploy-nginx.conf.template"
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
BACKEND_ENV="${BACKEND_ENV},SUBSCRIPTION_ENABLED=true,APPLE_ENVIRONMENT=production"
# Hard paywall: every user needs an active subscription (owner email exempt via the
# config default). Flip to false to open the app.
BACKEND_ENV="${BACKEND_ENV},SUBSCRIPTION_REQUIRED=true"

# ── AI timeout ladder (CLAUDE.md §3ae / §5) ──────────────────────────────────
# Both rungs are set HERE, explicitly, so the ordering is visible in one place.
# NUTRIENT_ENRICHMENT_TIMEOUT used to be a hardcoded 120.0 in the service while
# this file set OLLAMA_TIMEOUT=290 — an outer rung shorter than the inner one, so
# Ollama's own limit could never fire and every meal needing the AI fallback was
# killed at exactly 120 s and reported to the user as "unavailable".
OLLAMA_TIMEOUT_S=290
ENRICHMENT_TIMEOUT_S=310
BACKEND_ENV="${BACKEND_ENV},NUTRIENT_ENRICHMENT_TIMEOUT=${ENRICHMENT_TIMEOUT_S}"

# Refuse to ship an inverted ladder. The unit tests compare the CODE DEFAULTS and
# cannot see this file, so without this check a green suite says nothing about
# what is actually deployed.
if [ "$ENRICHMENT_TIMEOUT_S" -le "$OLLAMA_TIMEOUT_S" ]; then
  echo "ERROR: NUTRIENT_ENRICHMENT_TIMEOUT=${ENRICHMENT_TIMEOUT_S} must EXCEED OLLAMA_TIMEOUT=${OLLAMA_TIMEOUT_S}." >&2
  echo "  A wrapper shorter than the call it waits on makes the inner timeout unreachable." >&2
  exit 1
fi
# alafia-ollama scales to zero (§5): a cold call pays ~77 s of model load on top
# of generation, ~250 s total. Every rung waiting on it must clear that.
if [ "$ENRICHMENT_TIMEOUT_S" -lt 250 ]; then
  echo "ERROR: NUTRIENT_ENRICHMENT_TIMEOUT=${ENRICHMENT_TIMEOUT_S} does not clear a cold Ollama model load (~250 s)." >&2
  exit 1
fi
# Two-step signup (verify email → pay → account) is CODE-READY but gated OFF
# here, because turning it on closes registration until email actually works:
#   /auth/register            -> 410 Gone
#   /auth/signup/start        -> 503 without an email provider, and with Resend
#                                configured but NO VERIFIED DOMAIN the send 403s,
#                                so the verification link never arrives.
# Either way no new account can be created. Flip to true ONLY after a domain is
# verified at resend.com/domains and a test signup completes end to end.
BACKEND_ENV="${BACKEND_ENV},TWO_STEP_SIGNUP_REQUIRED=${TWO_STEP_SIGNUP_REQUIRED:-false}"
# Where contact-form submissions are DELIVERED.
#
# `alafia.app` publishes DKIM and SPF but has NO MX RECORDS — it can send and
# cannot receive — so the per-desk contact@/privacy@/dpo@/security@alafia.app
# addresses bounce. Every desk therefore delivers to one real mailbox, with the
# desk name in the subject for filtering. The submission is written to
# `contact_submissions` regardless, so a bounced notification never loses a
# message; this only decides who gets TOLD.
#
# Clear this (and add MX records) once those mailboxes actually exist.
BACKEND_ENV="${BACKEND_ENV},CONTACT_DELIVERY_EMAIL=${CONTACT_DELIVERY_EMAIL:-woleakpose@outlook.com}"
# Schedulers OFF: in-process cron must not run on an autoscaled service.
BACKEND_ENV="${BACKEND_ENV},FIREBASE_SYNC_ENABLED=false,PRACTICE_GEOCODE_ENABLED=false"
# Private GPU Ollama LLM + the deployed commit stamp (surfaced by /api/health).
# OLLAMA_VISION_MODEL is set EXPLICITLY. Left unset, the backend falls back to a
# per-file default, and those defaults disagreed: image_ai.py said "moondream"
# (which CLAUDE.md §3a forbids -- it answers the food schema with bounding boxes)
# while ALAFIAModel said "llava". Naming it here means the deployed value is
# visible in the service description instead of buried in two code paths.
#
# 290, not 300: Cloud Run cuts the request at 300s, so an equal value means
# the backend's own timeout can never fire first and the caller gets the
# platform's error instead of ours. Keep every rung strictly ordered.
#
# The model must also be PULLED on the Ollama service -- Ollama answers
# /api/chat with 404 for a model it does not have, which is what took food-photo
# analysis down in production.
: "${OLLAMA_VISION_MODEL:=llava}"
BACKEND_ENV="${BACKEND_ENV},OLLAMA_BASE_URL=${OLLAMA_URL},OLLAMA_MODEL=gpt-oss:20b,OLLAMA_VISION_MODEL=${OLLAMA_VISION_MODEL},OLLAMA_TIMEOUT=${OLLAMA_TIMEOUT_S},GIT_SHA=${GIT_SHA}"
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
# The AI de-identification secret. NOT optional and deliberately not routed
# through add_secret_if_present: without it, `subject_token()` falls back to a
# constant in the source, so the pseudonym sent to model providers is reversible
# by enumerating user ids. The backend raises rather than serve in that state, so
# a missing secret must fail HERE, with an instruction, not at the first AI call.
if gcloud secrets versions list alafia-pseudonym-secret --filter='state=enabled' \
     --format='value(name)' --limit=1 2>/dev/null | grep -q .; then
  BACKEND_SECRETS="${BACKEND_SECRETS},ALAFIA_PSEUDONYM_SECRET=alafia-pseudonym-secret:latest"
  echo "   + mounting ALAFIA_PSEUDONYM_SECRET (required)"
else
  echo "ERROR: secret 'alafia-pseudonym-secret' does not exist." >&2
  echo "  AI requests identify the user by an HMAC of this secret. Without it the" >&2
  echo "  token is derived from a constant in the source and can be reversed." >&2
  echo "  Create it once (it must NEVER be rotated casually — every existing" >&2
  echo "  subject token changes with it):" >&2
  echo "    openssl rand -hex 32 | tr -d '\\n' \\" >&2
  echo "      | gcloud secrets create alafia-pseudonym-secret --data-file=- --project=${PROJECT_ID}" >&2
  exit 1
fi

add_secret_if_present STRIPE_SECRET_KEY       stripe-secret-key
add_secret_if_present STRIPE_PRICE_ID         stripe-price-id
add_secret_if_present STRIPE_PRICE_ID_ANNUAL  stripe-price-id-annual
add_secret_if_present STRIPE_WEBHOOK_SECRET   stripe-webhook-secret
add_secret_if_present APPLE_SHARED_SECRET     apple-shared-secret
# Email — transactional (signup verification, password reset).
# Resend (HTTPS API) is preferred over SMTP on Cloud Run: no outbound mail ports,
# no STARTTLS negotiation, and real error bodies instead of socket failures.
#   printf 're_xxx' | gcloud secrets create resend-api-key --data-file=-
add_secret_if_present RESEND_API_KEY           resend-api-key
# SMTP fallback (used only when RESEND_API_KEY is absent).
# Without these mounted the backend silently skips every send, which now blocks
# signup outright: an account is never created for an unverified address, so a
# production signup cannot complete until these exist. Create them with:
#   printf 'smtp.example.com' | gcloud secrets create smtp-host --data-file=-
#   printf 'apikey'           | gcloud secrets create smtp-user --data-file=-
#   printf '<password>'       | gcloud secrets create smtp-password --data-file=-
add_secret_if_present SMTP_HOST               smtp-host
add_secret_if_present SMTP_USER               smtp-user
add_secret_if_present SMTP_PASSWORD           smtp-password
add_secret_if_present SMTP_FROM_EMAIL         smtp-from-email
# LLM round-robin provider keys — mount whichever exist (adds them to the pool).
for pair in $LLM_PROVIDER_SECRETS; do
  add_secret_if_present "${pair%%:*}" "${pair##*:}"
done
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

# ── 6. Backend second pass — pin the public origin to the custom domain ───────
# (Not the *.run.app URL — the app is served at PUBLIC_DOMAIN, and mobile/web hit
# api.$domain. Using the domain here is what keeps CORS/redirects prod-correct.)
echo "── Wiring backend → public URL (${PUBLIC_DOMAIN}) ─────────────"
WWW="${PUBLIC_DOMAIN/https:\/\//https:\/\/www.}"
gcloud run services update "$SVC_BACKEND" --region "$REGION" \
  --update-env-vars "^|^PUBLIC_WEB_URL=${PUBLIC_DOMAIN}|CORS_ORIGINS=[\"${PUBLIC_DOMAIN}\",\"${WWW}\"]|EHR_REDIRECT_URI=${PUBLIC_DOMAIN}/ehr/callback"

echo ""
echo "✅ Deployed  (commit ${GIT_SHA})."
echo "   App:      ${PUBLIC_DOMAIN}"
echo "   API:      https://api.${PUBLIC_DOMAIN#https://}   (mobile apps point here)"
echo "   Identity: ${IDENTITY_URL}  (internal)"
echo "   Verify:   curl -s ${PUBLIC_DOMAIN}/api/health   # .version must == ${GIT_SHA}"
echo ""
echo "Smoke: curl -fsS ${FRONTEND_URL}/api/v1/subscription/plans"
