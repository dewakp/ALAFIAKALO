#!/usr/bin/env bash
# Remove lab rows a document parser invented from a PDF's boilerplate and column
# overflow, in PRODUCTION.
#
#   scripts/db/cleanup_docparse_artifacts.sh            # DRY RUN (default)
#   scripts/db/cleanup_docparse_artifacts.sh --apply    # actually delete
#
# Dry run is the default deliberately: this DELETES from a clinical table. The
# dry run runs the identical statements inside a transaction and rolls back, so
# the printed list is exactly what --apply would remove — not a separate query
# that might drift from it.
#
# What it removes, and why deletion rather than correction:
#
#   * PROSE — the lab PDFs carry "disciplinary action, up to and including
#     termination of employment with DaVita.", which parsed into a test name and
#     a value and was shown to a clinician among real results.
#
#   * WEIGHT - PRE/POST DAY = 1 — a name wider than its header label spilled past
#     the column boundary, so the "1" of "DAY 1" became the value and the true
#     weight (57.5 kg) was discarded. The real value lives only in the source
#     PDF; writing a guessed one onto a clinical record would be worse than
#     removing the row.
#
# AFTER running this, re-import the source documents to restore the correct
# rows. Order matters: dedupe is keyed on (test_date, lower(test_name)) and the
# parser fix CHANGES the name ("WEIGHT - PRE DAY" -> "WEIGHT - PRE DAY 1"), so a
# re-import against the un-cleaned table inserts the corrected row ALONGSIDE the
# bad one and the patient ends up with two contradictory weights on one date.
#
# Requires: gcloud ADC + PROD_DB_PASS. Everything else runs in pinned containers.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_lib.sh"

APPLY=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  ""|--dry-run) APPLY=0 ;;
  *) die "usage: $(basename "$0") [--dry-run|--apply]" ;;
esac

[ -n "${PROD_DB_PASS:-}" ] || die "PROD_DB_PASS is not set (see scripts/db/README.md)"

trap stop_proxy EXIT
start_proxy

if [ "$APPLY" -eq 1 ]; then
  printf '\033[1;31mThis DELETES lab rows in PRODUCTION\033[0m (%s).\n' "$INSTANCE_CONN"
  printf 'A dry run should have been reviewed first — read the printed row list.\n'
  read -r -p 'Type EXACTLY "delete lab artifacts" to continue: ' reply
  [ "$reply" = "delete lab artifacts" ] || die "aborted"
fi

# The SQL ends without COMMIT/ROLLBACK on purpose; the terminator is appended
# here so the dry run and the real run execute byte-identical statements.
TERMINATOR="ROLLBACK;"
[ "$APPLY" -eq 1 ] && TERMINATOR="COMMIT;"

log "running against PROD ($INSTANCE_CONN) — dry_run=$((1 - APPLY))"
SQL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
{ cat "$SQL_DIR/cleanup_docparse_artifacts.sql"; printf '\n%s\n' "$TERMINATOR"; } \
  | prod_psql -f -

if [ "$APPLY" -eq 1 ]; then
  log "applied."
  log "NEXT: re-import the source PDFs so the corrected rows land. They will be"
  log "      DEDUPE_NEW (the parser fix changed the names), which is now correct"
  log "      because the bad rows are gone."
else
  log "DRY RUN only — rolled back, nothing changed."
  log "Re-run with --apply once the printed list looks right."
fi
