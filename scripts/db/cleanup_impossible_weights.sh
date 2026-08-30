#!/usr/bin/env bash
# Blank dialysis weights that are not a person's, and the fluid figure derived
# from them, in PRODUCTION.
#
#   scripts/db/cleanup_impossible_weights.sh            # DRY RUN (default)
#   scripts/db/cleanup_impossible_weights.sh --apply    # actually write
#
# Dry run is the default deliberately: this writes to a clinical table. It runs
# the IDENTICAL statements inside a transaction and rolls back, so the printed
# list is exactly what --apply changes — not a separate query that might drift
# from it.
#
# What it corrects, and why NULL rather than deletion:
#
#   The record holds a post-dialysis weight of 0.3 kg, and pre-dialysis weights
#   of 3.5 and 4.7 kg. Those are weighing-machine faults. `fluid_removed_ml` is
#   exactly (pre - post) x 1000, so each one became a fluid figure — +60,900 ml
#   and -59,800 ml — and then a bad average: the clinician dashboard reports
#   608 ml where the truth is 663 ml.
#
#   The SESSION stays. The treatment happened; only the weighing is wrong, and
#   deleting the row would lose a real dialysis session. The bad fields become
#   NULL, which the app already renders as "not recorded" rather than as zero.
#
# Selection is by physiology, not a list of ids, and uses the same bounds
# `TherapySessionBase` now enforces on the way in — so this cleans exactly what
# the validation would refuse today, and nothing else.
set -euo pipefail
cd "$(dirname "$0")/../.."
source scripts/db/db_lib.sh

SQL_FILE=/sql/cleanup_impossible_weights.sql
APPLY="${1:-}"

if [ "$APPLY" = "--apply" ]; then
  say "APPLYING — writing to production"
  printf 'BEGIN;\n\\i %s\nCOMMIT;\n' "$SQL_FILE" | prod_psql -f -
  say "applied."
else
  say "DRY RUN — the same statements, rolled back. Use --apply to write."
  printf 'BEGIN;\n\\i %s\nROLLBACK;\n' "$SQL_FILE" | prod_psql -f -
  say "nothing was written."
fi
