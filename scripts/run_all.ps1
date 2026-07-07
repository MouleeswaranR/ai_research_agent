# ============================================================
# Auto Dev Company – All-in-One Local Setup & Runner Script
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  🤖 AUTO DEV COMPANY - ALL-IN-ONE SETUP & LAUNCHER" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Ensure .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "📄 .env file not found. Copying from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "✅ .env created. Please update API keys in .env if needed." -ForegroundColor Green
}

# 2. Check if Docker is available
$dockerInstalled = $false
try {
    docker --version | Out-Null
    $dockerInstalled = $true
} catch {
    $dockerInstalled = $false
}

if ($dockerInstalled) {
    Write-Host "🐳 Docker detected! Attempting launch with Docker Compose..." -ForegroundColor Green
    try {
        docker compose up -d --build
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "  🎉 ALL SERVICES STARTED SUCCESSFULLY IN DOCKER!" -ForegroundColor Green
        Write-Host "  👉 Web Dashboard: http://localhost:8000/dashboard" -ForegroundColor Cyan
        Write-Host "  👉 Health Check:  http://localhost:8000/health" -ForegroundColor Cyan
        Write-Host "============================================================" -ForegroundColor Green
        exit 0
    } catch {
        Write-Host "⚠️ Docker Compose failed or docker daemon not running. Falling back to native execution..." -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️ Docker not found. Running setup natively with local Python environment..." -ForegroundColor Yellow
}

# 3. Native Python execution fallback
Write-Host "📦 Installing Python package dependencies..." -ForegroundColor Cyan
python -m pip install -e ".[dev]" pydantic-settings

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  🚀 STARTING FASTAPI WEB SERVER & DASHBOARD..." -ForegroundColor Green
Write-Host "  👉 Web Dashboard: http://localhost:8000/dashboard" -ForegroundColor Cyan
Write-Host "  👉 Health Check:  http://localhost:8000/health" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
