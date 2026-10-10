#!/bin/bash
# Start Pindora Shield (Backend + Frontend) locally

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=== Starting Pindora Shield Locally ==="

# 1. Start Backend
echo "Starting Backend API on http://localhost:8000..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 2. Start Frontend
echo "Starting Frontend UI on http://localhost:5173..."
cd "$DIR/frontend"
npm run dev -- --host &
FRONTEND_PID=$!

# Cleanup on exit
trap "echo 'Stopping all services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

echo ""
echo "=========================================="
echo " Pindora Shield is running locally!"
echo "   Frontend : http://localhost:5173"
echo "   Backend  : http://localhost:8000"
echo "   API Docs : http://localhost:8000/docs"
echo "=========================================="
echo "Press [Ctrl+C] to stop all services."

wait
