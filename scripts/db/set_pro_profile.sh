#!/usr/bin/env bash
# Attach or fill in the ProfessionalProfile on a user's professional role.
#
#   scripts/db/set_pro_profile.sh --emails a@x.com --role physician \
#       --license '000-XXXX-0000-XX'                                   # DRY RUN on PROD
#   scripts/db/set_pro_profile.sh --emails a@x.com --role physician \
#       --license '000-XXXX-0000-XX' --apply
#   scripts/db/set_pro_profile.sh --target dev --emails a@x.com --role physician --apply
#
# Dry run is the default: this writes to production. Every statement runs and is
# then rolled back, so the printed "before"/"after" is exactly what applying does.
#
# Only the fields you pass are written — omitted ones keep whatever is already
# there, so seeding a placeholder cannot wipe details the user later filled in.
# `verification_status` stays 'unverified'; verification is a real review step
# and no provisioning script gets to skip it.
#
# Requires (prod only): gcloud ADC + PROD_DB_PASS. See scripts/db/README.md.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_lib.sh"

TARGET="prod"
EMAILS=""
ROLE=""
LICENSE=""
SPECIALTY=""
PRACTICE=""
APPLY=0

usage() {
  cat >&2 <<EOF
usage: $(basename "$0") --emails a@x.com[,b@y.com] --role ROLE [options]

  --target dev|prod     which database (default: prod)
  --emails LIST         comma-separated target emails (required)
  --role ROLE           the role assignment to attach the profile to (required)
  --license VALUE       license_number
  --specialty VALUE     specialty
  --practice VALUE      practice_name
  --apply               actually commit (default is a dry run)
EOF
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --target)    TARGET="${2:-}"; shift 2 ;;
    --emails)    EMAILS="${2:-}"; shift 2 ;;
    --role)      ROLE="${2:-}"; shift 2 ;;
    --license)   LICENSE="${2:-}"; shift 2 ;;
    --specialty) SPECIALTY="${2:-}"; shift 2 ;;
    --practice)  PRACTICE="${2:-}"; shift 2 ;;
    --apply)     APPLY=1; shift ;;
    --dry-run)   APPLY=0; shift ;;
    -h|--help)   usage ;;
    *)           warn "unknown argument: $1"; usage ;;
  esac
done

[ -n "$EMAILS" ] || { warn "--emails is required"; usage; }
[ -n "$ROLE" ]   || { warn "--role is required"; usage; }
[ "$TARGET" = "dev" ] || [ "$TARGET" = "prod" ] || die "--target must be dev or prod"

# The role column is a plain VARCHAR, so a typo would be stored happily and then
# matched by nothing in the app. Check it against the enum the app actually uses.
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

SQL_ARGS=(
  -v "emails=$EMAILS"
  -v "role=$ROLE"
  -v "license=$LICENSE"
  -v "specialty=$SPECIALTY"
  -v "practice=$PRACTICE"
  -v "dry_run=$((1 - APPLY))"
  -f /sql/set_pro_profile.sql
)

if [ "$TARGET" = "prod" ]; then
  [ -n "${PROD_DB_PASS:-}" ] || die "PROD_DB_PASS is not set (see scripts/db/README.md)"
  if [ "$APPLY" -eq 1 ]; then
    printf '\033[1;31mThis will write to PRODUCTION\033[0m (%s).\n' "$INSTANCE_CONN"
    printf 'targets: %s   role: %s   license: %s\n' "$EMAILS" "$ROLE" "${LICENSE:-<unchanged>}"
    printf 'A dry run should have been reviewed first.\n'
    read -r -p 'Type EXACTLY "write profile" to continue: ' reply
    [ "$reply" = "write profile" ] || die "aborted"
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
