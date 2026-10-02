#!/usr/bin/env bash
# Starts both api and frontend in parallel.
# Set ZAI_API_KEY before running:  export ZAI_API_KEY=your-key
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "[InkMind] Starting api on http://localhost:8000 ..."
cd "$ROOT/api"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!


echo "[GLM Chat] Starting frontend on http://localhost:5173 ..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo "[GLM Chat] Both services started. Press Ctrl+C to stop."
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
