#!/usr/bin/env bash
# Test: Session Share + Fork API
# Base: http://localhost:8080
# Credentials: admin@prism.dev / admin123

set -euo pipefail

BASE="http://localhost:8080/api/v1"
EMAIL="admin@prism.dev"
PASSWORD="admin123"

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; exit 1; }

# ---------------------------------------------------------------------------
# 1. Login
# ---------------------------------------------------------------------------
echo "--- 1. Login ---"
LOGIN_RESP=$(curl -sf -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
[ -n "$TOKEN" ] && pass "login → got access_token" || fail "login failed: $LOGIN_RESP"

# ---------------------------------------------------------------------------
# 2. Create session
# ---------------------------------------------------------------------------
echo "--- 2. Create session ---"
SESSION_RESP=$(curl -sf -X POST "$BASE/sessions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"share-fork-test"}')
SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])")
[ -n "$SESSION_ID" ] && pass "created session $SESSION_ID" || fail "create session failed: $SESSION_RESP"

# ---------------------------------------------------------------------------
# 3. Verify session is accessible (no task submission needed for share test)
# ---------------------------------------------------------------------------
echo "--- 3. Verify session accessible ---"
GET_RESP=$(curl -sf "$BASE/sessions/$SESSION_ID" \
  -H "Authorization: Bearer $TOKEN")
SESS_STATUS=$(echo "$GET_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['status'])")
[ -n "$SESS_STATUS" ] && pass "session status=$SESS_STATUS" || fail "get session failed: $GET_RESP"

# ---------------------------------------------------------------------------
# 4. POST /sessions/{id}/share → expect 201 + token
# ---------------------------------------------------------------------------
echo "--- 4. Create share ---"
SHARE_BODY=$(mktemp)
SHARE_CODE=$(curl -s -o "$SHARE_BODY" -w "%{http_code}" -X POST "$BASE/sessions/$SESSION_ID/share" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"expires_in_days":7}')
SHARE_RESP=$(cat "$SHARE_BODY"); rm -f "$SHARE_BODY"
[ "$SHARE_CODE" = "201" ] || fail "POST /share expected 201, got $SHARE_CODE: $SHARE_RESP"
SHARE_TOKEN=$(echo "$SHARE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")
SHARE_URL=$(echo "$SHARE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['url'])")
[ -n "$SHARE_TOKEN" ] && pass "share created, token=$SHARE_TOKEN url=$SHARE_URL" || fail "create share failed: $SHARE_RESP"

# ---------------------------------------------------------------------------
# 5. GET /shared/{token} without auth → expect 200 + session content
# ---------------------------------------------------------------------------
echo "--- 5. Access shared session (no auth) ---"
SHARED_BODY=$(mktemp)
SHARED_CODE=$(curl -s -o "$SHARED_BODY" -w "%{http_code}" "http://localhost:8080/api/v1/shared/$SHARE_TOKEN")
SHARED_RESP=$(cat "$SHARED_BODY"); rm -f "$SHARED_BODY"
[ "$SHARED_CODE" = "200" ] || fail "GET /shared/{token} expected 200, got $SHARED_CODE: $SHARED_RESP"
SHARED_SESSION_ID=$(echo "$SHARED_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['session']['id'])")
[ "$SHARED_SESSION_ID" = "$SESSION_ID" ] && pass "shared session id matches ($SHARED_SESSION_ID)" || fail "shared session id mismatch: got $SHARED_SESSION_ID expected $SESSION_ID"

# ---------------------------------------------------------------------------
# 6. POST /sessions/{id}/fork → expect 201 + new session id
# ---------------------------------------------------------------------------
echo "--- 6. Fork session ---"
FORK_BODY=$(mktemp)
FORK_CODE=$(curl -s -o "$FORK_BODY" -w "%{http_code}" -X POST "$BASE/sessions/$SESSION_ID/fork" \
  -H "Authorization: Bearer $TOKEN")
FORK_RESP=$(cat "$FORK_BODY"); rm -f "$FORK_BODY"
[ "$FORK_CODE" = "201" ] || fail "POST /fork expected 201, got $FORK_CODE: $FORK_RESP"
FORKED_ID=$(echo "$FORK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])")
[ "$FORKED_ID" != "$SESSION_ID" ] && pass "fork created new session $FORKED_ID" || fail "fork returned same session id as source"
FORK_TITLE=$(echo "$FORK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['title'])")
echo "    forked title: $FORK_TITLE"

# ---------------------------------------------------------------------------
# 7. DELETE /sessions/{id}/share → expect 204
# ---------------------------------------------------------------------------
echo "--- 7. Revoke share ---"
REVOKE_CODE=$(curl -so /dev/null -w "%{http_code}" -X DELETE "$BASE/sessions/$SESSION_ID/share" \
  -H "Authorization: Bearer $TOKEN")
[ "$REVOKE_CODE" = "204" ] && pass "share revoked (204)" || fail "DELETE /share expected 204, got $REVOKE_CODE"

# ---------------------------------------------------------------------------
# 8. GET /shared/{token} after revoke → expect 404
# ---------------------------------------------------------------------------
echo "--- 8. Access revoked share → expect 404 ---"
AFTER_CODE=$(curl -so /dev/null -w "%{http_code}" "http://localhost:8080/api/v1/shared/$SHARE_TOKEN")
if [ "$AFTER_CODE" = "404" ] || [ "$AFTER_CODE" = "410" ]; then
  pass "revoked share returns $AFTER_CODE"
else
  fail "expected 404 or 410 after revoke, got $AFTER_CODE"
fi

# ---------------------------------------------------------------------------
# Cleanup: delete test session and forked session
# ---------------------------------------------------------------------------
echo "--- Cleanup ---"
curl -sf -X DELETE "$BASE/sessions/$SESSION_ID" -H "Authorization: Bearer $TOKEN" > /dev/null && echo "    deleted source session"
curl -sf -X DELETE "$BASE/sessions/$FORKED_ID" -H "Authorization: Bearer $TOKEN" > /dev/null && echo "    deleted forked session"

echo ""
echo "All checks passed."
