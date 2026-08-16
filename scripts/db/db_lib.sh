#!/usr/bin/env bash
# Shared config + helpers for the ALAFIA database parity tooling.
#
# Every postgres client call goes through a PINNED Docker image. Nothing is
# installed on the host, so the client version can never drift between machines
# or between you and CI — which is one of the ways the two databases silently
# diverged before.

set -euo pipefail

# ── Pinned tooling ───────────────────────────────────────────────────────
PG_IMAGE="postgres:18-alpine"                              # matches prod (PG18)
PROXY_IMAGE="gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.14.3"

# ── Topology (single source of truth; deploy/gcp/config.env is authoritative) ──
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
[ -f "$REPO_ROOT/deploy/gcp/config.env" ] && source "$REPO_ROOT/deploy/gcp/config.env"

PROJECT_ID="${PROJECT_ID:-alafia-prod-6igma}"
REGION="${REGION:-us-east4}"
SQL_INSTANCE="${SQL_INSTANCE:-alafia-db-va}"
DB_NAME="${DB_NAME:-alafia}"
DB_USER="${DB_USER:-alafia}"
INSTANCE_CONN="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"

# Local dev database (WEB/docker-compose.yml service `db`, published on 5435).
DEV_HOST="${DEV_HOST:-127.0.0.1}"
DEV_PORT="${DEV_PORT:-5435}"
DEV_USER="${DEV_USER:-alafia}"
DEV_PASS="${DEV_PASS:-alafia}"
DEV_DB="${DEV_DB:-alafia}"

# Port the Cloud SQL Auth Proxy listens on locally while a sync runs.
PROXY_PORT="${PROXY_PORT:-5436}"

# Schemas that MUST match. `public` is the app; `identity` is the PQC SSO store.
SCHEMAS="${SCHEMAS:-public,identity}"

ART_DIR="${ART_DIR:-$REPO_ROOT/.db-parity}"

log()  { printf '\033[1;36m[db]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[db]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[db] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# psql against the LOCAL dev database.
dev_psql() {
  docker run --rm --network host -e PGPASSWORD="$DEV_PASS" \
    -v "$REPO_ROOT/scripts/db:/sql:ro" "$PG_IMAGE" \
    psql -h "$DEV_HOST" -p "$DEV_PORT" -U "$DEV_USER" -d "$DEV_DB" "$@"
}

# psql against PROD, through an already-running Cloud SQL Auth Proxy.
prod_psql() {
  [ -n "${PROD_DB_PASS:-}" ] || die "PROD_DB_PASS is not set (see docs/DATABASE_PARITY.md)"
  docker run --rm --network host -e PGPASSWORD="$PROD_DB_PASS" \
    -v "$REPO_ROOT/scripts/db:/sql:ro" "$PG_IMAGE" \
    psql -h 127.0.0.1 -p "$PROXY_PORT" -U "$DB_USER" -d "$DB_NAME" "$@"
}

fingerprint_args=(-q -A -t -F '|' -v "schemas=$SCHEMAS" -f /sql/fingerprint.sql)

# Start the Cloud SQL Auth Proxy; returns once it is accepting connections.
start_proxy() {
  local adc="$HOME/.config/gcloud/application_default_credentials.json"
  [ -f "$adc" ] || die "No Application Default Credentials at $adc
  Run this yourself (it opens a browser):  gcloud auth application-default login"

  log "starting Cloud SQL Auth Proxy → $INSTANCE_CONN on :$PROXY_PORT"
  PROXY_CID=$(docker run -d --rm --network host \
    -v "$adc:/adc.json:ro" -e GOOGLE_APPLICATION_CREDENTIALS=/adc.json \
    "$PROXY_IMAGE" \
    --address 0.0.0.0 --port "$PROXY_PORT" "$INSTANCE_CONN")

  for _ in $(seq 1 45); do
    if docker run --rm --network host "$PG_IMAGE" \
         pg_isready -h 127.0.0.1 -p "$PROXY_PORT" >/dev/null 2>&1; then
      log "proxy ready"; return 0
    fi
    sleep 1
  done
  docker logs "$PROXY_CID" 2>&1 | tail -20 >&2
  die "Cloud SQL Auth Proxy did not become ready"
}

stop_proxy() {
  [ -n "${PROXY_CID:-}" ] && docker rm -f "$PROXY_CID" >/dev/null 2>&1 || true
  PROXY_CID=""
}

require_dev_db_up() {
  docker run --rm --network host "$PG_IMAGE" \
    pg_isready -h "$DEV_HOST" -p "$DEV_PORT" >/dev/null 2>&1 \
    || die "Local dev DB is not up on $DEV_HOST:$DEV_PORT
  Start it with:  cd WEB && docker compose up -d db"
}
