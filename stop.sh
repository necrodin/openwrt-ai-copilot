#!/bin/bash

echo "Stopping..."

pkill -f "uvicorn app.main:app" || true
pkill -f "next dev" || true

echo "Done."
