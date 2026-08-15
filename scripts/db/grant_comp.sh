#!/usr/bin/env bash
# Grant a complimentary membership (and optionally a professional role).
#
#   scripts/db/grant_comp.sh --emails a@x.com,b@y.com                    # DRY RUN on PROD
#   scripts/db/grant_comp.sh --emails a@x.com --role physician --apply
#   scripts/db/grant_comp.sh --target dev --emails a@x.com --apply       # local dev DB
#
# Dry run is the default deliberately: this writes to the production user,
# subscription and role tables. The dry run runs every statement and then rolls
# back, so what it prints is what applying would do — read it before --apply.
#
# The role name is validated against the real `UserRole` enum before anything
# runs. The column is a plain VARCHAR, so a typo would otherwise be accepted by
# the database and then matched by nothing in the app.
#
# Requires (prod only): gcloud ADC + PROD_DB_PASS. Everything runs in pinned
# containers — see scripts/db/README.md.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_lib.sh"

TARGET="prod"
EMAILS=""
ROLE=""
MAKE_PRIMARY=0
MONTHS=12
ALLOW_OVERWRITE=0
APPLY=0

usage() {
  cat >&2 <<EOF
usage: $(basename "$0") --emails a@x.com[,b@y.com] [options]

  --target dev|prod     which database (default: prod)
  --emails LIST         comma-separated target emails (required)
  --role ROLE           also grant this role (e.g. physician)
  --primary             make that role the user's primary role
  --months N            length of the complimentary period (default: 12)
  --allow-overwrite     permit replacing an existing PAID subscription
  --apply               actually commit (default is a dry run)
EOF
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --target)          TARGET="${2:-}"; shift 2 ;;
    --emails)          EMAILS="${2:-}"; shift 2 ;;
    --role)            ROLE="${2:-}"; shift 2 ;;
    --primary)         MAKE_PRIMARY=1; shift ;;
    --months)          MONTHS="${2:-}"; shift 2 ;;
    --allow-overwrite) ALLOW_OVERWRITE=1; shift ;;
    --apply)           APPLY=1; shift ;;
    --dry-run)         APPLY=0; shift ;;
    -h|--help)         usage ;;
    *)                 warn "unknown argument: $1"; usage ;;
  esac
done

[ -n "$EMAILS" ] || { warn "--emails is required"; usage; }
[ "$TARGET" = "dev" ] || [ "$TARGET" = "prod" ] || die "--target must be dev or prod"
[[ "$MONTHS" =~ ^[0-9]+$ ]] || die "--months must be a whole number of months"
[ "$MAKE_PRIMARY" -eq 0 ] || [ -n "$ROLE" ] || die "--primary needs --role"

# ── Validate the role against the enum the application actually uses ──────
GRANT_ROLE=0
if [ -n "$ROLE" ]; then
  GRANT_ROLE=1
  PY="${ALAFIA_PYTHON:-/Users/woleakpose/Developer/dev_env/bin/python}"
  if [ -x "$PY" ]; then
    PYTHONPATH="$REPO_ROOT/WEB/backend" "$PY" - "$ROLE" <<'PYCHECK' || die "invalid role: $ROLE"
import sys
from app.models.user_roles import UserRole
try:
    UserRole(sys.argv[1])
except ValueError:
    sys.exit(1)
PYCHECK
  else
    warn "python not found at $PY — role name NOT validated against UserRole"
  fi
fi

SQL_ARGS=(
  -v "emails=$EMAILS"
  -v "grant_role=$GRANT_ROLE"
  -v "role=$ROLE"
  -v "make_primary=$MAKE_PRIMARY"
  -v "months=$MONTHS"
  -v "allow_overwrite=$ALLOW_OVERWRITE"
  -v "dry_run=$((1 - APPLY))"
  -f /sql/grant_comp_and_role.sql
)

if [ "$TARGET" = "prod" ]; then
  [ -n "${PROD_DB_PASS:-}" ] || die "PROD_DB_PASS is not set (see scripts/db/README.md)"
  if [ "$APPLY" -eq 1 ]; then
    printf '\033[1;31mThis will write to PRODUCTION\033[0m (%s).\n' "$INSTANCE_CONN"
    printf 'targets: %s   role: %s   months: %s\n' "$EMAILS" "${ROLE:-<none>}" "$MONTHS"
    printf 'A dry run should have been reviewed first.\n'
    read -r -p 'Type EXACTLY "grant prod" to continue: ' reply
    [ "$reply" = "grant prod" ] || die "aborted"
  fi
  trap stop_proxy EXIT
  start_proxy
  log "running against PROD ($INSTANCE_CONN) — dry_run=$((1 - APPLY))"
  prod_psql "${SQL_ARGS[@]}"
else
  require_dev_db_up
  log "running against DEV ($DEV_HOST:$DEV_PORT) — dry_run=$((1 - APPLY))"
  dev_psql "${SQL_ARGS[@]}"
fi

if [ "$APPLY" -eq 0 ]; then
  log "DRY RUN only — nothing changed. Re-run with --apply once the plan looks right."
fi
