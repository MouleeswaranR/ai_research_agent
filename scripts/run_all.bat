@echo off
rem ============================================================
rem Auto Dev Company – All-in-One Setup & Launcher Batch Script
rem ============================================================

echo ============================================================
echo   🤖 AUTO DEV COMPANY - ALL-IN-ONE SETUP & LAUNCHER
echo ============================================================
echo.

if not exist ".env" (
    echo 📄 .env file not found. Copying from .env.example...
    copy .env.example .env
    echo ✅ .env created. Please update API keys in .env if needed.
)

docker --version >nul 2>&1
if %errorlevel% == 0 (
    echo 🐳 Docker detected! Launching with Docker Compose...
    docker compose up -d --build
    if %errorlevel% == 0 (
        echo.
        echo ============================================================
        echo   🎉 ALL SERVICES STARTED SUCCESSFULLY IN DOCKER!
        echo   👉 Web Dashboard: http://localhost:8000/dashboard
        echo   👉 Health Check:  http://localhost:8000/health
        echo ============================================================
        exit /b 0
    )
)

echo ⚠️ Running setup natively with local Python environment...
python -m pip install -e ".[dev]" pydantic-settings

echo.
echo ============================================================
echo   🚀 STARTING FASTAPI WEB SERVER & DASHBOARD...
echo   👉 Web Dashboard: http://localhost:8000/dashboard
echo   👉 Health Check:  http://localhost:8000/health
echo ============================================================
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
