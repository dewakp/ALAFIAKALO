#!/usr/bin/env bash
# Post-deploy smoke test, including the AI surfaces.
#
# Why this exists: the checklist in DEPLOY.md checked /subscription/plans and
# /auth/csrf-cookie and nothing else. Both stayed green for 27 days while the
# three AI panels on the dashboard returned 503 to every user, because nothing
# in the deploy path or the 700-test suite ever called a real model.
#
#   scripts/gcp/smoke.sh                       # unauthenticated checks only
#   scripts/gcp/smoke.sh --token "$TOKEN"      # adds the AI checks
#
# Exit 0 = everything checked passed. Non-zero = count of failures.
#
# The AI checks are SLOW on purpose. A model that answers correctly in 100s is
# a pass here and a failure in a browser on the 30s CRUD default -- that gap is
# the whole bug this script was written for, so the timing is reported, not
# hidden.
set -uo pipefail

API="${API:-https://api.alafia.app}"
TOKEN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --token) TOKEN="${2:-}"; shift 2 ;;
    --api)   API="${2:-}";   shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAILURES=0
pass() { printf '  \033[32mPASS\033[0m  %-42s %s\n' "$1" "${2:-}"; }
fail() { printf '  \033[31mFAIL\033[0m  %-42s %s\n' "$1" "${2:-}"; FAILURES=$((FAILURES+1)); }

echo "── Public endpoints ─────────────────────────────────────────"

code=$(curl -s -o /dev/null -w '%{http_code}' -m 30 "$API/api/v1/subscription/plans")
[ "$code" = "200" ] && pass "subscription/plans" "200" || fail "subscription/plans" "got $code"

code=$(curl -s -o /dev/null -w '%{http_code}' -m 30 "$API/api/v1/auth/csrf-cookie")
# case, not a chained || &&: that idiom silently picks the wrong branch when
# the first test passes, and a smoke test that lies is worse than none.
case "$code" in
  200|204) pass "auth/csrf-cookie" "$code" ;;
  *)       fail "auth/csrf-cookie" "got $code" ;;
esac

if [ -z "$TOKEN" ]; then
  echo
  echo "No --token given: the AI checks were SKIPPED, not passed."
  echo "That distinction matters -- a green run without a token is exactly the"
  echo "signal that missed a month-long AI outage."
  exit $FAILURES
fi

AUTH=(-H "Authorization: Bearer $TOKEN")

echo
echo "── AI (real model calls -- expect tens of seconds) ──────────"

# One generated suggestion proves the whole chain: IAM to the private Ollama
# service, the model being reachable, and response parsing. Body and status are
# captured from ONE request -- calling twice bills a second ~100s GPU run just
# to read a status line.
start=$(date +%s)
resp=$(curl -s -w '\n%{http_code}' -m 280 "${AUTH[@]}" -H 'Content-Type: application/json' \
        -X POST "$API/api/v1/planners/meal-suggestions" \
        -d '{"health_goals":"smoke test","count":1}')
elapsed=$(( $(date +%s) - start ))
code=$(printf '%s' "$resp" | tail -n1)
body=$(printf '%s' "$resp" | sed '$d')

case "$code" in
  200) pass "planners/meal-suggestions" "200 in ${elapsed}s"
       # A pass that is slower than the browser's ceiling is still a user-facing
       # failure. AI_TIMEOUT_MS is 240s; warn well before it.
       [ "$elapsed" -gt 120 ] && echo "        note: ${elapsed}s is over half the 240s client ceiling" ;;
  503) fail "planners/meal-suggestions" "503 -- $(echo "$body" | head -c 140)" ;;
  502) fail "planners/meal-suggestions" "502 model returned junk" ;;
  *)   fail "planners/meal-suggestions" "got $code" ;;
esac

start=$(date +%s)
code=$(curl -s -o /dev/null -w '%{http_code}' -m 280 "${AUTH[@]}" -H 'Content-Type: application/json' \
        -X POST "$API/api/v1/personalization/recommendations" -d '{"type":"wellness"}')
elapsed=$(( $(date +%s) - start ))
case "$code" in
  200) pass "personalization/recommendations" "200 in ${elapsed}s" ;;
  403) pass "personalization/recommendations" "403 (ai_coaching off for this account)" ;;
  # The exact shape of the 27-day outage: instant 503 = a gate refused before
  # the model was ever asked. A slow 503 is a real outage.
  503) if [ "$elapsed" -le 2 ]; then
         fail "personalization/recommendations" "503 in ${elapsed}s -- refused WITHOUT asking the model (the api_key-gate regression)"
       else
         fail "personalization/recommendations" "503 after ${elapsed}s -- model genuinely unavailable"
       fi ;;
  *)   fail "personalization/recommendations" "got $code" ;;
esac

echo
[ "$FAILURES" -eq 0 ] && echo "All checks passed." || echo "$FAILURES check(s) failed."
exit $FAILURES
