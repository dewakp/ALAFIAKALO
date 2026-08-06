#!/usr/bin/env bash
# Deactivate robot/test accounts in PRODUCTION.
#
#   scripts/db/deactivate_test_accounts_prod.sh            # DRY RUN (default)
#   scripts/db/deactivate_test_accounts_prod.sh --apply    # actually apply
#
# Dry run is the default deliberately: this touches the production user table,
# and the patterns (`%@example.com`, `%@x.com`) are heuristics. `x.com` is a real
# live domain and `example.com` is only conventionally fake, so ALWAYS read the
# printed target list before applying.
#
# It deactivates rather than deletes — 65 of the 101 foreign keys referencing
# `users` are NO ACTION, so a DELETE would fail rather than cascade. Accounts
# holding a subscription are skipped outright and listed for manual review.
#
# Reverse with deactivate_test_accounts_rollback.sql (original emails are kept).
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
  printf '\033[1;31mThis will deactivate matching accounts in PRODUCTION\033[0m (%s).\n' "$INSTANCE_CONN"
  printf 'A dry run should have been reviewed first.\n'
  read -r -p 'Type EXACTLY "deactivate prod" to continue: ' reply
  [ "$reply" = "deactivate prod" ] || die "aborted"
fi

log "running against PROD ($INSTANCE_CONN) — dry_run=$((1 - APPLY))"
prod_psql -v "dry_run=$((1 - APPLY))" -f /sql/deactivate_test_accounts.sql

if [ "$APPLY" -eq 1 ]; then
  log "applied. Verifying…"
  prod_psql -q -A -t -c "
    SELECT 'active users: ' || count(*) FROM users WHERE is_active;
    SELECT 'deactivated (recoverable): ' || count(*) FROM deactivated_accounts;
    SELECT 'identity-only disabled: ' || count(*) FROM deactivated_identity_only;
    SELECT 'still-active pattern matches (should be subscription holders only): '
           || count(*) FROM users
     WHERE is_active AND (lower(email) LIKE '%@example.com' OR lower(email) LIKE '%@x.com');"
  log "reverse with: prod_psql -f /sql/deactivate_test_accounts_rollback.sql"
else
  log "DRY RUN only — nothing changed. Re-run with --apply once the list looks right."
fi
