#!/usr/bin/env bash
# Prism v2 — Development Startup Script
# Usage: ./start-dev.sh [--backend-only | --frontend-only | --full]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
AMBER='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[Prism]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK ]${NC} $*"; }
warn() { echo -e "${AMBER}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

MODE="${1:-full}"

# ── Pre-flight checks ────────────────────────────────────────────────
check_deps() {
    command -v docker >/dev/null 2>&1 || fail "docker not found"
    command -v node >/dev/null 2>&1   || fail "node not found (needed for frontend)"
    command -v npm >/dev/null 2>&1    || fail "npm not found"
    [ -f ".env" ]                     || fail ".env not found — copy from .env.example and fill in secrets"
    ok "Dependencies checked"
}

# ── Backend (Docker Compose) ─────────────────────────────────────────
start_backend() {
    log "Starting backend services (postgres + redis + backend + nginx)..."

    docker compose up -d --build 2>&1 | tail -5

    log "Waiting for backend health..."
    local retries=0
    local max_retries=30
    while [ $retries -lt $max_retries ]; do
        if curl -sf http://localhost:8080/api/v1/health/live >/dev/null 2>&1; then
            ok "Backend healthy at http://localhost:8080"
            return 0
        fi
        retries=$((retries + 1))
        sleep 2
    done
    fail "Backend failed to start after ${max_retries} attempts"
}

# ── Frontend (Vite dev server) ───────────────────────────────────────
start_frontend() {
    if [ ! -d "frontend-react/node_modules" ]; then
        log "Installing frontend dependencies..."
        cd frontend-react && npm install && cd ..
        ok "Frontend dependencies installed"
    fi

    log "Starting Vite dev server on http://localhost:3000..."
    cd frontend-react
    npx vite --port 3000 &
    VITE_PID=$!
    cd ..

    sleep 3
    if curl -sf http://localhost:3000/ >/dev/null 2>&1; then
        ok "Frontend running at http://localhost:3000 (PID: $VITE_PID)"
    else
        warn "Frontend may still be starting (PID: $VITE_PID)"
    fi
}

# ── Status ───────────────────────────────────────────────────────────
show_status() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  Prism v2 — Development Environment${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  Backend API:   ${GREEN}http://localhost:8080/api/v1${NC}"
    echo -e "  Frontend:      ${GREEN}http://localhost:3000${NC}"
    echo -e "  Admin:         ${GREEN}http://localhost:3000/admin${NC}"
    echo ""
    echo -e "  Login:         admin@prism.dev / PrismAdmin!2026"
    echo ""
    echo -e "  Stop backend:  ${AMBER}docker compose down${NC}"
    echo -e "  Stop frontend: ${AMBER}kill $VITE_PID${NC} (or Ctrl+C)"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── Shutdown handler ─────────────────────────────────────────────────
cleanup() {
    log "Shutting down..."
    if [ -n "${VITE_PID:-}" ]; then
        kill "$VITE_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# ── Main ─────────────────────────────────────────────────────────────
case "$MODE" in
    --backend-only|-b)
        check_deps
        start_backend
        log "Backend only mode. Frontend not started."
        ;;
    --frontend-only|-f)
        check_deps
        start_frontend
        ;;
    --full|full|*)
        check_deps
        start_backend
        start_frontend
        show_status
        wait "$VITE_PID" 2>/dev/null
        ;;
esac
