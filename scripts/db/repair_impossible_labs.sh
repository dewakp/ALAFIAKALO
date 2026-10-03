#!/usr/bin/env bash
# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

# Repair lab values that cannot be true, and abnormality flags nobody computed.
#
#   scripts/db/repair_impossible_labs.sh            # DRY RUN (default)
#   scripts/db/repair_impossible_labs.sh --apply    # actually write
#   DB=dev scripts/db/repair_impossible_labs.sh     # against the dev copy
#
# Dry run is the default deliberately: this UPDATES a clinical table. The dry
# run executes the identical statements inside a transaction and rolls back, so
# the printed output is exactly what --apply would do — not a separate query
# that can drift from the action.
#
# WHAT IT REPAIRS
#
#   1. A haematocrit stored as 338.4% against a printed range of 42-52, shown to
#      the patient with a green tick. The true value is 38.4%: the analyte is
#      HCT CALC (HGBX3), haematocrit calculated as haemoglobin x 3, and that
#      day's haemoglobin was 12.8. A literal "3" had migrated from the END of
#      the NAME to the FRONT of the VALUE upstream, leaving the figure exactly
#      300 too high. Three rows carry that signature.
#
#      THIS IS NOT A GUESS, and the SQL proves that to itself before writing:
#      the UPDATE fires only where TWO independent derivations agree —
#      (stored - 300) and (that day's HGB x 3). §3ab is explicit that putting an
#      invented value onto a clinical record is worse than removing the row, so
#      a row where they disagree is left exactly as it is, for a human.
#
#      The value arrives corrupted in the Firestore export; our fault was
#      accepting it in silence. The parser now refuses to pre-tick a percentage
#      above 100, so this cannot recur through document import.
#
#   2. `is_abnormal`, wherever the row already carries the range needed to
#      compute it. It is a TRI-STATE, and 9,417 of 9,745 rows are NULL because
#      the bulk importers store ref_low, ref_high AND value while passing
#      through whatever `flag` the source CSV had — empty, for every firestore
#      row — and never call `normalize.compute_abnormal`. Every client rendered
#      NULL as the reassuring branch.
#
#      Rows with no range keep NULL, which is now honest: the clients say
#      "Not assessed" rather than "Normal".
#
# Requires, for prod: gcloud ADC + PROD_DB_PASS. Everything runs in pinned
# containers. `DB=dev` needs only the local stack up.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_lib.sh"

APPLY=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  ""|--dry-run) APPLY=0 ;;
  *) die "usage: $(basename "$0") [--dry-run|--apply]   (DB=dev|prod)" ;;
esac

TARGET="${DB:-prod}"
SQL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The SQL ends without COMMIT/ROLLBACK on purpose; the terminator is appended
# here so the dry run and the real run execute byte-identical statements.
TERMINATOR="ROLLBACK;"
[ "$APPLY" -eq 1 ] && TERMINATOR="COMMIT;"

run_sql() {
  { printf 'BEGIN;\n'; cat "$SQL_DIR/repair_impossible_labs.sql"; \
    printf '\n%s\n' "$TERMINATOR"; } | "$1" -f -
}

if [ "$TARGET" = "dev" ]; then
  require_dev_db_up
  log "running against DEV ($DEV_HOST:$DEV_PORT) — dry_run=$((1 - APPLY))"
  run_sql dev_psql
else
  [ -n "${PROD_DB_PASS:-}" ] || die "PROD_DB_PASS is not set (see scripts/db/README.md)"
  if [ "$APPLY" -eq 1 ]; then
    printf '\033[1;31mThis UPDATES lab rows in PRODUCTION\033[0m (%s).\n' "$INSTANCE_CONN"
    printf 'A dry run should have been reviewed first — read the printed rows.\n'
    read -r -p 'Type EXACTLY "repair lab values" to continue: ' reply
    [ "$reply" = "repair lab values" ] || die "aborted"
  fi
  trap stop_proxy EXIT
  start_proxy
  log "running against PROD ($INSTANCE_CONN) — dry_run=$((1 - APPLY))"
  run_sql prod_psql
fi

if [ "$APPLY" -eq 1 ]; then
  log "applied."
  log "NOTE: the three repaired rows keep their own history in \`notes\`, so the"
  log "      correction stays auditable rather than looking like original data."
else
  log "DRY RUN only — rolled back, nothing changed."
  log "Re-run with --apply once the printed rows look right."
fi
