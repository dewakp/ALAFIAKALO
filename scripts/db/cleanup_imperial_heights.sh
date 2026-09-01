#!/usr/bin/env bash
# Correct profile heights stored as INCHES in a centimetre column, in PRODUCTION.
#
#   scripts/db/cleanup_imperial_heights.sh            # DRY RUN (default)
#   scripts/db/cleanup_imperial_heights.sh --apply    # actually write
#
# Dry run is the default deliberately: this writes to a clinical field that
# feeds BMI and every weight-derived nutrient target. It runs the IDENTICAL
# statements inside a transaction and rolls back, so the printed list is
# exactly what --apply changes.
#
# Why rows exist to clean: `PATCH /users/me` took a bare `height_cm: float`
# with no unit and no bounds, while `app/core/units.py`'s `inches_to_cm` had no
# callers anywhere. A patient whose locale is imperial entered 70 and it was
# stored as a 70 cm adult.
#
# Selection is by physiology plus the patient's OWN measurements — never by a
# list of ids, and never by arithmetic alone. A row is corrected only when the
# stored value is impossible for their age AND their vitals_logs corroborate a
# real height matching it read as inches. Adults with an impossible height and
# no corroborating measurement are printed and LEFT ALONE: a wrong height a
# clinician can see beats an invented one they cannot.
#
# The value written is the patient's MEASURED height, not the conversion —
# 176.35 is what they were measured at; 177.8 is only what 70 inches equals.
#
# The intake path is fixed too, so this cleans history rather than a leak that
# is still running: the endpoint now infers the unit from age and refuses an
# impossible value (tests/test_unit_intake.py).
set -euo pipefail
cd "$(dirname "$0")/../.."
source scripts/db/db_lib.sh

SQL_FILE=/sql/cleanup_imperial_heights.sql
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
