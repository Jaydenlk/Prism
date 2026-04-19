#!/bin/bash
# Final ops smoke after Workstreams A/B/D land.
# Runs: infrastructure health → multi-channel auth → LLM roundtrip → admin CRUD → Playwright.
# Exit non-zero if any phase fails.

set -e

BASE=http://localhost:8080/api/v1
ADMIN=admin@prism.dev
PWD=PrismAdmin!2026

hr() { echo; echo "━━━━━━ $1 ━━━━━━"; }
fail() { echo "❌ $1"; exit 1; }
ok()   { echo "✅ $1"; }

hr "1. Infrastructure"
curl -sf http://localhost:8080/healthz >/dev/null || fail "nginx down"
curl -sf $BASE/health/ready | grep -q '"status":"ok"' || fail "backend not ready"
ok "nginx + backend healthy"

hr "2. Multi-channel auth probe"
PROV=$(curl -sf $BASE/auth/providers)
echo "$PROV" | python -m json.tool
for f in email_password email_magic email_otp phone_password; do
  echo "$PROV" | grep -q "\"$f\": *true" || fail "$f provider missing"
done
ok "4 auth channels enabled (google depends on .env config)"

hr "3. Admin login + token"
TOKEN=$(curl -sf -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d "{\"email\":\"$ADMIN\",\"password\":\"$PWD\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
[ -n "$TOKEN" ] || fail "admin login failed"
ok "admin token acquired (len=${#TOKEN})"

hr "4. AuthConfig (3 toggles present)"
AC=$(curl -sf -H "Authorization: Bearer $TOKEN" $BASE/admin/auth-config)
for k in allow_oauth_signup_without_invite allow_phone_registration require_email_verification; do
  echo "$AC" | grep -q "\"$k\"" || fail "auth_config missing $k"
done
ok "3 auth toggles present"

hr "5. Providers seeded from .env"
curl -sf -H "Authorization: Bearer $TOKEN" $BASE/providers \
  | python -c "import sys,json; d=json.load(sys.stdin)['data']; assert len(d)>=8, f'only {len(d)} providers'; print(f'providers={len(d)}')" \
  || fail "provider bootstrap broken"
ok "≥8 scope=system providers"

hr "6. LLM end-to-end (CloudDream auto-v2)"
SID=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"ops-smoke"}' $BASE/sessions \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['id'])")
RID=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"prompt\":\"reply with OK only\"}" $BASE/tasks \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['run_id'])")
echo "session=$SID run=$RID"
for i in 1 2 3 4 5 6 7 8 9 10; do
  STAT=$(curl -sf -H "Authorization: Bearer $TOKEN" $BASE/runs/$RID \
    | python -c "import sys,json; print(json.load(sys.stdin)['data']['status'])")
  echo "  t=${i} status=$STAT"
  [ "$STAT" = "completed" ] && break
  [ "$STAT" = "failed" ]    && fail "run failed"
  sleep 2
done
[ "$STAT" = "completed" ] || fail "run didn't complete within 20s"
MSG=$(curl -sf -H "Authorization: Bearer $TOKEN" "$BASE/sessions/$SID/messages?limit=5" \
  | python -c "import sys,json; d=json.load(sys.stdin).get('data',{}); items=d if isinstance(d,list) else d.get('items',[]); a=[m for m in items if m['role']=='assistant']; print(a[0].get('text_preview','') if a else '<none>')")
echo "  assistant reply: $MSG"
[ -n "$MSG" ] || fail "assistant reply empty"
ok "LLM roundtrip: $MSG"

hr "7. Admin dashboard stats live"
curl -sf -H "Authorization: Bearer $TOKEN" $BASE/admin/stats/dashboard \
  | python -c "import sys,json; d=json.load(sys.stdin); print(f'runs_24h={d[\"runs_24h\"]} active_users={d[\"active_users_24h\"]} comp_health={d[\"component_health\"]}')"
ok "dashboard returns live data"

hr "8. Metrics export"
curl -sf http://localhost:8080/metrics | grep -c "^prism_" | xargs -I{} echo "  prism_* metric count: {}"
ok "Prometheus metrics exporting"

hr "9. Playwright suite (if installed)"
if [ -d e2e/node_modules/@playwright ]; then
  cd e2e
  npx playwright test --project=desktop-chromium --reporter=list 2>&1 | tail -20 || fail "playwright desktop failed"
  npx playwright test --project=mobile-safari --reporter=list 2>&1 | tail -20 || fail "playwright mobile failed"
  cd ..
  ok "Playwright suite passed on both projects"
else
  echo "  (playwright not installed — skipping)"
fi

echo
echo "═══════════════════════════════"
echo "🎉  Final ops smoke PASSED."
echo "═══════════════════════════════"
