# Prism v2 — Development Startup Script (Windows PowerShell)
# Usage: .\start-dev.ps1 [-Mode full|backend|frontend]
param(
    [ValidateSet('full', 'backend', 'frontend')]
    [string]$Mode = 'full'
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Log($msg)  { Write-Host "[Prism] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[  OK ] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

# ── Pre-flight ───────────────────────────────────────────────────────
function Test-Dependencies {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "docker not found" }
    if (-not (Get-Command node -ErrorAction SilentlyContinue))   { Fail "node not found" }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue))    { Fail "npm not found" }
    if (-not (Test-Path ".env"))                                  { Fail ".env not found" }
    Ok "Dependencies checked"
}

# ── Backend ──────────────────────────────────────────────────────────
function Start-Backend {
    Log "Starting backend services..."
    docker compose up -d --build

    Log "Waiting for backend health..."
    $retries = 0
    while ($retries -lt 30) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:8080/api/v1/health/live" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) {
                Ok "Backend healthy at http://localhost:8080"
                return
            }
        } catch {}
        $retries++
        Start-Sleep -Seconds 2
    }
    Fail "Backend failed to start"
}

# ── Frontend ─────────────────────────────────────────────────────────
function Start-Frontend {
    if (-not (Test-Path "frontend-react\node_modules")) {
        Log "Installing frontend dependencies..."
        Push-Location frontend-react
        npm install
        Pop-Location
        Ok "Dependencies installed"
    }

    Log "Starting Vite dev server on http://localhost:3000..."
    $script:ViteProcess = Start-Process -FilePath "npx" -ArgumentList "vite --port 3000" -WorkingDirectory "frontend-react" -PassThru -NoNewWindow
    Start-Sleep -Seconds 3

    try {
        $r = Invoke-WebRequest -Uri "http://localhost:3000/" -UseBasicParsing -TimeoutSec 3
        Ok "Frontend running at http://localhost:3000 (PID: $($script:ViteProcess.Id))"
    } catch {
        Warn "Frontend may still be starting (PID: $($script:ViteProcess.Id))"
    }
}

# ── Status ───────────────────────────────────────────────────────────
function Show-Status {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "  Prism v2 — Development Environment" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Backend API:   " -NoNewline; Write-Host "http://localhost:8080/api/v1" -ForegroundColor Green
    Write-Host "  Frontend:      " -NoNewline; Write-Host "http://localhost:3000" -ForegroundColor Green
    Write-Host "  Admin:         " -NoNewline; Write-Host "http://localhost:3000/admin" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Login:         admin@prism.dev / PrismAdmin!2026"
    Write-Host ""
    Write-Host "  Stop backend:  " -NoNewline; Write-Host "docker compose down" -ForegroundColor Yellow
    Write-Host "  Stop frontend: " -NoNewline; Write-Host "Stop-Process -Id $($script:ViteProcess.Id)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
}

# ── Main ─────────────────────────────────────────────────────────────
Test-Dependencies

switch ($Mode) {
    'backend' {
        Start-Backend
        Log "Backend only. Frontend not started."
    }
    'frontend' {
        Start-Frontend
    }
    'full' {
        Start-Backend
        Start-Frontend
        Show-Status
        Log "Press Ctrl+C to stop frontend..."
        Wait-Process -Id $script:ViteProcess.Id
    }
}
