#!/usr/bin/env bash
# Prove that the local dev database is logically identical to PROD.
#
#   scripts/db/verify_parity.sh            # compare dev against prod
#   scripts/db/verify_parity.sh --dev-only # just print the dev fingerprint
#
# Exit 0 only when every table, every row, the column shape, and the alembic
# revision match. ANY difference exits non-zero and prints exactly what differs.
# Run this BEFORE starting work and BEFORE trusting anything you see in the app.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_lib.sh"

mkdir -p "$ART_DIR"
DEV_FP="$ART_DIR/dev.fingerprint"
PROD_FP="$ART_DIR/prod.fingerprint"

require_dev_db_up
log "fingerprinting DEV  ($DEV_HOST:$DEV_PORT/$DEV_DB)"
dev_psql "${fingerprint_args[@]}" | grep -E '^(TABLE|SCHEMA|ALEMBIC)\|' | sort > "$DEV_FP"
log "  $(grep -c '^TABLE|' "$DEV_FP") tables"

if [ "${1:-}" = "--dev-only" ]; then
  log "dev fingerprint written to $DEV_FP"
  exit 0
fi

trap stop_proxy EXIT
start_proxy
log "fingerprinting PROD ($INSTANCE_CONN)"
prod_psql "${fingerprint_args[@]}" | grep -E '^(TABLE|SCHEMA|ALEMBIC)\|' | sort > "$PROD_FP"
log "  $(grep -c '^TABLE|' "$PROD_FP") tables"
stop_proxy

if diff -q "$PROD_FP" "$DEV_FP" >/dev/null; then
  log "✅ PARITY OK — dev is byte-identical to prod across schemas: $SCHEMAS"
  exit 0
fi

printf '\n\033[1;31m❌ DRIFT DETECTED\033[0m  (prod = gospel, dev is wrong)\n\n'

# Tables present on only one side.
comm -23 <(grep '^TABLE|' "$PROD_FP" | cut -d'|' -f2,3 | sort) \
         <(grep '^TABLE|' "$DEV_FP"  | cut -d'|' -f2,3 | sort) \
  | sed 's/^/  MISSING IN DEV   /'
comm -13 <(grep '^TABLE|' "$PROD_FP" | cut -d'|' -f2,3 | sort) \
         <(grep '^TABLE|' "$DEV_FP"  | cut -d'|' -f2,3 | sort) \
  | sed 's/^/  EXTRA IN DEV     /'

# Tables on both sides whose contents differ.
join -t'|' -j1 \
  <(grep '^TABLE|' "$PROD_FP" | awk -F'|' '{print $2"."$3"|"$4"|"$5}' | sort) \
  <(grep '^TABLE|' "$DEV_FP"  | awk -F'|' '{print $2"."$3"|"$4"|"$5}' | sort) \
  | awk -F'|' '$2!=$4 || $3!=$5 {printf "  CONTENT DIFFERS  %-45s prod=%s rows  dev=%s rows\n", $1, $2, $4}'

for k in SCHEMA ALEMBIC; do
  p=$(grep "^$k|" "$PROD_FP" || true); d=$(grep "^$k|" "$DEV_FP" || true)
  [ "$p" = "$d" ] || printf '  %-16s prod=%s\n  %-16s dev =%s\n' "$k MISMATCH" "${p#*|}" "" "${d#*|}"
done

printf '\nFix by pulling prod down (one direction only):\n  scripts/db/pull_prod.sh\n\n'
exit 1
