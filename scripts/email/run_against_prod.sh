#!/usr/bin/env bash
# Run send_announcement.py against the PRODUCTION database.
#
#   scripts/email/run_against_prod.sh              # dry run (default)
#   scripts/email/run_against_prod.sh --apply      # really send
#   scripts/email/run_against_prod.sh --to a@b.com --apply
#
# Why this wrapper exists: run the sender inside the dev compose container and it
# silently resolves its audience from the DEV COPY of prod and signs unsubscribe
# tokens with the DEV SECRET_KEY. Both failures are invisible — you get a
# plausible list and links that never verify. This routes the script through the
# Cloud SQL Auth Proxy with production's own secrets instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO_ROOT/scripts/db/db_lib.sh"

: "${POSTAL_ADDRESS:?POSTAL_ADDRESS must be set (CAN-SPAM requires a physical address)}"
[ -n "${PROD_DB_PASS:-}" ] || die "PROD_DB_PASS is not set"

SECRET_KEY="$(gcloud secrets versions access latest --secret=alafia-secret-key)"
RESEND_API_KEY="$(gcloud secrets versions access latest --secret=resend-api-key)"
[ -n "$SECRET_KEY" ]     || die "could not read alafia-secret-key"
[ -n "$RESEND_API_KEY" ] || die "could not read resend-api-key"

IMAGE="${IMAGE:-web-backend}"

trap stop_proxy EXIT
start_proxy

log "running the sender against PROD via 127.0.0.1:${PROXY_PORT}"
docker run --rm --network host \
  -v "$REPO_ROOT/WEB/backend:/app" \
  -v "$REPO_ROOT/ML:/ml:ro" \
  -v "$REPO_ROOT/scripts/email:/mail:ro" \
  -w /app \
  -e PYTHONPATH=/app:/ml/src \
  -e DATABASE_URL="postgresql+asyncpg://${DB_USER}:${PROD_DB_PASS}@127.0.0.1:${PROXY_PORT}/${DB_NAME}" \
  -e SECRET_KEY="$SECRET_KEY" \
  -e RESEND_API_KEY="$RESEND_API_KEY" \
  -e POSTAL_ADDRESS="$POSTAL_ADDRESS" \
  "$IMAGE" python /mail/send_announcement.py "$@"
