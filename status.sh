#!/bin/bash

echo "Backend"

pgrep -fl "uvicorn app.main:app" || echo "Not running"

echo ""

echo "Frontend"

pgrep -fl "next dev" || echo "Not running"
