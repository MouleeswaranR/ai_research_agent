#!/usr/bin/env bash

# ============================================================
# Auto Dev Company – All-in-One Setup & Launcher Script
# ============================================================

set -e

echo -e "\033[1;36m============================================================\033[0m"
echo -e "\033[1;36m  🤖 AUTO DEV COMPANY - ALL-IN-ONE SETUP & LAUNCHER\033[0m"
echo -e "\033[1;36m============================================================\033[0m"
echo ""

# 1. Ensure .env file exists
if [ ! -f ".env" ]; then
    echo -e "\033[1;33m📄 .env file not found. Copying from .env.example...\033[0m"
    cp .env.example .env
    echo -e "\033[1;32m✅ .env created. Please update API keys in .env if needed.\033[0m"
fi

# 2. Check if Docker & Docker Compose are available
if command -v docker &> /dev/null && docker info &> /dev/null; then
    echo -e "\033[1;32m🐳 Docker detected! Launching container stack with Docker Compose...\033[0m"
    docker compose up -d --build
    echo ""
    echo -e "\033[1;32m============================================================\033[0m"
    echo -e "\033[1;32m  🎉 ALL SERVICES STARTED SUCCESSFULLY IN DOCKER!\033[0m"
    echo -e "\033[1;36m  👉 Web Dashboard: http://localhost:8000/dashboard\033[0m"
    echo -e "\033[1;36m  👉 Health Check:  http://localhost:8000/health\033[0m"
    echo -e "\033[1;32m============================================================\033[0m"
    exit 0
else
    echo -e "\033[1;33m⚠️ Docker daemon not available. Falling back to native local execution...\033[0m"
fi

# 3. Native Python execution fallback
echo -e "\033[1;36m📦 Installing Python package dependencies...\033[0m"
python -m pip install -e ".[dev]" pydantic-settings

echo ""
echo -e "\033[1;32m============================================================\033[0m"
echo -e "\033[1;32m  🚀 STARTING FASTAPI WEB SERVER & DASHBOARD...\033[0m"
echo -e "\033[1;36m  👉 Web Dashboard: http://localhost:8000/dashboard\033[0m"
echo -e "\033[1;36m  👉 Health Check:  http://localhost:8000/health\033[0m"
echo -e "\033[1;32m============================================================\033[0m"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
