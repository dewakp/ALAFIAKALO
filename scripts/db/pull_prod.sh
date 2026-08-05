#!/usr/bin/env bash
# Replace the local dev database with an exact copy of PROD, then prove it.
#
#   scripts/db/pull_prod.sh
#
# Direction is ONE WAY, always: prod → dev. Prod is gospel. There is deliberately
# no push_prod.sh — prod only ever changes through a migration + deploy.
#
# What it does:
#   1. dumps prod (schemas: public + identity) with pg_dump --format=custom
#   2. restores into the local dev DB with --clean --if-exists (dev is REPLACED)
#   3. runs verify_parity.sh and FAILS if the copy is not identical
#
# ⚠️  This pulls real patient data (PHI) onto this machine. The dump is written
#     to .db-parity/ (gitignored) and deleted at the end unless --keep-dump.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_lib.sh"

KEEP_DUMP=0
ASSUME_YES=0
for a in "$@"; do
  case "$a" in
    --keep-dump) KEEP_DUMP=1 ;;
    -y|--yes)    ASSUME_YES=1 ;;
    *) die "unknown flag: $a" ;;
  esac
done

mkdir -p "$ART_DIR"
DUMP="$ART_DIR/prod.dump"

require_dev_db_up

if [ "$ASSUME_YES" -ne 1 ]; then
  printf '\033[1;33mThis REPLACES the local dev database\033[0m (%s:%s/%s)\n' \
    "$DEV_HOST" "$DEV_PORT" "$DEV_DB"
  printf 'with an exact copy of PROD (%s), including real PHI.\n' "$INSTANCE_CONN"
  read -r -p 'Type EXACTLY "replace dev" to continue: ' reply
  [ "$reply" = "replace dev" ] || die "aborted"
fi

trap stop_proxy EXIT
start_proxy

# ── 1. Dump prod ─────────────────────────────────────────────────────────
# --format=custom so the restore can run in parallel and --clean works cleanly.
# --no-owner / --no-privileges because the local role set differs from Cloud SQL.
log "dumping prod → $DUMP"
schema_flags=()
IFS=',' read -ra _s <<< "$SCHEMAS"
for s in "${_s[@]}"; do schema_flags+=( --schema="$s" ); done

docker run --rm --network host -e PGPASSWORD="${PROD_DB_PASS:?PROD_DB_PASS is not set}" \
  -v "$ART_DIR:/out" "$PG_IMAGE" \
  pg_dump -h 127.0.0.1 -p "$PROXY_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --format=custom --no-owner --no-privileges --verbose \
    "${schema_flags[@]}" -f /out/prod.dump 2>&1 | tail -5

[ -s "$DUMP" ] || die "dump is empty — refusing to touch dev"
log "dump size: $(du -h "$DUMP" | cut -f1)"
stop_proxy

# ── 2. Restore into dev ──────────────────────────────────────────────────
# --clean --if-exists drops each object before recreating it, so leftovers from
# an older dev schema cannot survive and masquerade as parity.
log "restoring into dev (existing dev data is dropped)"
docker run --rm --network host -e PGPASSWORD="$DEV_PASS" \
  -v "$ART_DIR:/out:ro" "$PG_IMAGE" \
  pg_restore -h "$DEV_HOST" -p "$DEV_PORT" -U "$DEV_USER" -d "$DEV_DB" \
    --clean --if-exists --no-owner --no-privileges --jobs=4 \
    /out/prod.dump 2>&1 | grep -viE "does not exist, skipping" | tail -15 || true

# ── 3. Prove it ──────────────────────────────────────────────────────────
log "verifying parity"
if "$REPO_ROOT/scripts/db/verify_parity.sh"; then
  [ "$KEEP_DUMP" -eq 1 ] || { rm -f "$DUMP"; log "dump deleted (PHI hygiene); pass --keep-dump to retain"; }
  log "✅ dev now matches prod exactly"
else
  die "restore completed but parity FAILED — dev is NOT a faithful copy. Dump kept at $DUMP"
fi
