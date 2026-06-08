#!/usr/bin/env bash
# PFC AI Agent — one-shot local runner
# Usage: ./run.sh
set -e
cd "$(dirname "$0")"

echo "=== PFC AI Agent v2.0 ==="
echo "Installing backend dependencies..."
cd backend
pip install -r requirements.txt -q

echo "Starting backend on http://localhost:8000 ..."
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

cd ../frontend
echo "Installing frontend dependencies..."
npm install --silent

echo "Starting frontend on http://localhost:5173 ..."
echo ""
echo "Open http://localhost:5173 in your browser"
echo "Press Ctrl+C to stop both servers"
echo ""
npm run dev &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
