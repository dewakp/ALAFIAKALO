#!/usr/bin/env bash
# Retire accounts left behind by the broken one-step signup, in PRODUCTION.
#
#   scripts/db/deactivate_incomplete_signups_prod.sh            # DRY RUN (default)
#   scripts/db/deactivate_incomplete_signups_prod.sh --apply    # actually apply
#
# Dry run is the default deliberately: this touches the production user table.
# ALWAYS read the printed target list before applying — the selection is by
# state, not by a list of ids, so an unexpected row in it means a clause is
# wrong, not that the row is junk.
#
# What it targets: accounts that never signed in, never reached a payment
# attempt, and hold no clinical data of any kind, older than 7 days. These are
# the residue of `POST /auth/register` creating a loginable account while the
# web form reported nothing at all — a person pressed "Create", was charged
# nothing, got no email, and had their address permanently taken.
#
# It deactivates rather than deletes: 65 of the 101 foreign keys referencing
# `users` are NO ACTION, so a DELETE would fail rather than cascade. Scrambling
# the address to a reserved `.invalid` domain is also what FREES the real
# address, so the person can sign up again through the two-step flow.
#
# Reverse with deactivate_test_accounts_rollback.sql — it reads the same
# `deactivated_accounts` ledger, and the original addresses are preserved.
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
  printf '\033[1;31mThis will retire matching accounts in PRODUCTION\033[0m (%s).\n' "$INSTANCE_CONN"
  printf 'A dry run should have been reviewed first.\n'
  read -r -p 'Type EXACTLY "retire incomplete" to continue: ' reply
  [ "$reply" = "retire incomplete" ] || die "aborted"
fi

log "running against PROD ($INSTANCE_CONN) — dry_run=$((1 - APPLY))"
prod_psql -v "dry_run=$((1 - APPLY))" -f /sql/deactivate_incomplete_signups.sql

if [ "$APPLY" -eq 1 ]; then
  log "applied. Verifying…"
  prod_psql -q -A -t -c "
    SELECT 'active users: ' || count(*) FROM users WHERE is_active;
    SELECT 'retired (recoverable): ' || count(*)
      FROM deactivated_accounts WHERE reason = 'incomplete signup (one-step form)';
    SELECT 'still active with that shape (should be 0): ' || count(*)
      FROM users u
     WHERE u.is_active AND u.is_superuser = false AND u.last_login IS NULL
       AND u.created_at < now() - interval '7 days'
       AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id = u.id)
       AND NOT EXISTS (SELECT 1 FROM nutrition_logs n WHERE n.user_id = u.id);"
  log "reverse with: prod_psql -f /sql/deactivate_test_accounts_rollback.sql"
else
  log "DRY RUN only — nothing changed. Re-run with --apply once the list looks right."
fi
