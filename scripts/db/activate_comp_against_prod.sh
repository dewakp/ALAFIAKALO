#!/usr/bin/env bash
# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

# Finish a complimentary signup against PRODUCTION.
#
#   scripts/db/activate_comp_against_prod.sh --email a@b.com           # DRY RUN
#   scripts/db/activate_comp_against_prod.sh --email a@b.com --apply
#
# WHY THIS WRAPPER EXISTS
# -----------------------
# `activate_comp_signup.py` is a backend script, so its own docstring reaches
# for the compose service: `docker compose --profile test run --rm backend-test
# python scripts/activate_comp_signup.py`. That runs it against the DEV COPY of
# production — and that service's DATABASE_URL is an unreachable
# `localhost:5435/alafia` besides, where `localhost` is the container itself.
#
# So run as documented it either reaches no database at all, or writes the
# account into the wrong one, and prints "*** APPLIED. ***" over the result.
# The invitation tells the recipient to stop at the payment step and promises
# we will activate their membership; a tool that reports success against the
# wrong database does not keep that promise, it hides that it was broken.
#
# This routes the same script through the Cloud SQL Auth Proxy with
# production's own credentials, exactly as `grant_comp.sh` and
# `run_against_prod.sh` already do.
#
# RUN BOTH STEPS
# --------------
# This creates the ACCOUNT. It does not grant entitlement. Between the two the
# account exists but is UNPAID, so every gated route answers 402 and the person
# is locked out of the thing they were just told was live:
#
#   scripts/db/activate_comp_against_prod.sh --email a@b.com --apply
#   scripts/db/grant_comp.sh --emails a@b.com --months 12 --apply
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_lib.sh"

EMAIL=""
APPLY=0

usage() {
  cat >&2 <<EOF
usage: $(basename "$0") --email someone@example.com [--apply]

  --email ADDR   the address that signed up and stopped at payment (required)
  --apply        actually commit (default is a dry run that rolls back)
EOF
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --email)   EMAIL="${2:-}"; shift 2 ;;
    --apply)   APPLY=1; shift ;;
    --dry-run) APPLY=0; shift ;;
    -h|--help) usage ;;
    *)         warn "unknown argument: $1"; usage ;;
  esac
done

[ -n "$EMAIL" ] || { warn "--email is required"; usage; }

# There is NO secret named PROD_DB_PASS — the password lives inside the
# `alafia-database-url` secret. Derive it rather than requiring the operator to
# know that, which is the kind of undocumented step that turns into a
# half-finished activation at exactly the wrong moment.
if [ -z "${PROD_DB_PASS:-}" ]; then
  log "PROD_DB_PASS unset — deriving it from the alafia-database-url secret"
  DB_URL="$(gcloud secrets versions access latest --secret=alafia-database-url)" \
    || die "could not read the alafia-database-url secret (gcloud auth?)"
  # urlsplit, not a regex: the password is percent-encoded and may contain any
  # of :/@?#, each of which defeats a hand-rolled split in a different way.
  PROD_DB_PASS="$(printf '%s' "$DB_URL" | python3 -c \
    'import sys, urllib.parse as u; print(u.unquote(u.urlsplit(sys.stdin.read().strip()).password or ""))')"
  [ -n "$PROD_DB_PASS" ] || die "no password found in alafia-database-url"
fi

IMAGE="${IMAGE:-web-backend}"
docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || die "image '$IMAGE' not found. Build it:  cd WEB && docker compose build backend"

if [ "$APPLY" -eq 1 ]; then
  printf '\033[1;31mThis will write to PRODUCTION\033[0m (%s).\n' "$INSTANCE_CONN"
  printf 'It creates a real user account for: %s\n' "$EMAIL"
  printf 'A dry run should have been reviewed first.\n'
  read -r -p 'Type EXACTLY "activate prod" to continue: ' reply
  [ "$reply" = "activate prod" ] || die "aborted"
fi

trap stop_proxy EXIT
start_proxy

ARGS=(--email "$EMAIL")
[ "$APPLY" -eq 1 ] && ARGS+=(--apply)

log "running activate_comp_signup.py against PROD ($INSTANCE_CONN) — dry_run=$((1 - APPLY))"

# PYTHONPATH is /ml/src:/app, NOT /app:/ml/src. WEB/backend is bind-mounted over
# /app, and a killed deploy leaves an EMPTY `WEB/backend/alafia_model/` behind —
# which shadows the real package as a namespace package whenever /app comes
# first. Putting /ml/src ahead means the canonical source wins regardless.
docker run --rm --network host \
  -v "$REPO_ROOT/WEB/backend:/app" \
  -v "$REPO_ROOT/ML:/ml:ro" \
  -w /app \
  -e PYTHONPATH=/ml/src:/app \
  -e DATABASE_URL="postgresql+asyncpg://${DB_USER}:${PROD_DB_PASS}@127.0.0.1:${PROXY_PORT}/${DB_NAME}" \
  "$IMAGE" python scripts/activate_comp_signup.py "${ARGS[@]}"

if [ "$APPLY" -eq 0 ]; then
  log "DRY RUN only — nothing changed. Re-run with --apply once the plan looks right."
else
  log "NOW GRANT THE MEMBERSHIP, or the account is unpaid and answers 402:"
  log "  scripts/db/grant_comp.sh --emails $EMAIL --months 12 --apply"
fi
