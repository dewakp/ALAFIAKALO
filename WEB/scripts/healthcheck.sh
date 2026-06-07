#!/usr/bin/env bash
# healthcheck.sh — Quick smoke test for auth + AI chat endpoints
# Usage: ./scripts/healthcheck.sh [base_url]
# Example: ./scripts/healthcheck.sh http://localhost:8005

set -euo pipefail

BASE=${1:-http://localhost:8005}
PASS_COUNT=0
FAIL_COUNT=0

ok()   { echo "  [PASS] $1"; ((PASS_COUNT++)); }
fail() { echo "  [FAIL] $1"; ((FAIL_COUNT++)); }

# ── helpers ──────────────────────────────────────────────────────────────────
gen_csrf() { python3 -c "import uuid; print(uuid.uuid4())"; }

# ── 1. Health endpoint ────────────────────────────────────────────────────────
echo ""
echo "=== 1. Health ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BASE/api/health")
[ "$CODE" = "200" ] && ok "GET /api/health → $CODE" || fail "GET /api/health → $CODE (expected 200)"

# ── 2. Register ───────────────────────────────────────────────────────────────
echo ""
echo "=== 2. Register ==="
CSRF=$(gen_csrf)
EMAIL="healthcheck_$(date +%s)@example.com"
PASS="HcPass123!"
REG_CODE=$(curl -s -o /tmp/hc_reg.json -w "%{http_code}" --max-time 20 \
  -X POST "$BASE/api/v1/auth/register" \
  -H "X-CSRF-Token: $CSRF" -H "Cookie: csrf_token=$CSRF" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\",\"full_name\":\"HC Probe\"}")
[ "$REG_CODE" = "201" ] && ok "POST /api/v1/auth/register → $REG_CODE" || fail "POST /api/v1/auth/register → $REG_CODE (expected 201)"

# ── 3. Login ──────────────────────────────────────────────────────────────────
echo ""
echo "=== 3. Login ==="
LOGIN_CODE=$(curl -s -o /tmp/hc_login.json -w "%{http_code}" --max-time 20 \
  -X POST "$BASE/api/v1/auth/login" \
  -H "X-CSRF-Token: $CSRF" -H "Cookie: csrf_token=$CSRF" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=$EMAIL" \
  --data-urlencode "password=$PASS")
[ "$LOGIN_CODE" = "200" ] && ok "POST /api/v1/auth/login → $LOGIN_CODE" || fail "POST /api/v1/auth/login → $LOGIN_CODE (expected 200)"
TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/hc_login.json')).get('access_token',''))" 2>/dev/null || echo "")
[ -n "$TOKEN" ] && ok "JWT token present" || fail "JWT token missing"

# ── 4. AI Chat ────────────────────────────────────────────────────────────────
echo ""
echo "=== 4. AI Chat (slow — allow up to 120s) ==="
if [ -z "$TOKEN" ]; then
  fail "Skipped — no auth token"
else
  CHAT_CODE=$(curl -s -o /tmp/hc_chat.json -w "%{http_code}" --max-time 120 \
    -X POST "$BASE/api/v1/ai/chat" \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-CSRF-Token: $CSRF" -H "Cookie: csrf_token=$CSRF" \
    -H "Content-Type: application/json" \
    -d '{"query":"Say hello in one word","context_module":"general"}')
  if [ "$CHAT_CODE" = "200" ]; then
    ok "POST /api/v1/ai/chat → $CHAT_CODE"
    HAS_RESP=$(python3 -c "import json; d=json.load(open('/tmp/hc_chat.json')); print('yes' if 'response' in d else 'no')" 2>/dev/null || echo "no")
    [ "$HAS_RESP" = "yes" ] && ok "AI response field present" || fail "AI response field missing"
  else
    fail "POST /api/v1/ai/chat → $CHAT_CODE (expected 200)"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════"
echo "  PASSED: $PASS_COUNT   FAILED: $FAIL_COUNT"
echo "══════════════════════════════════"
[ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
