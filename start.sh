#!/bin/bash

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "======================================"
echo " OpenWrt AI Copilot"
echo "======================================"

pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true
pkill -f "next dev" >/dev/null 2>&1 || true

source "$ROOT/.venv/bin/activate"

echo "Starting Backend..."

cd "$ROOT/backend"

nohup uvicorn app.main:app \
    --reload \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level debug \
    > "$ROOT/backend.log" 2>&1 &

echo "Starting Frontend..."

cd "$ROOT/frontend"

nohup npm run dev \
    > "$ROOT/frontend.log" 2>&1 &

sleep 5

echo ""
echo "Frontend : http://localhost:3000"
echo "Backend  : http://localhost:8000"
echo "Swagger  : http://localhost:8000/docs"
