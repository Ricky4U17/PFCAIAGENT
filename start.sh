#!/usr/bin/env bash
# PFC AI Agent — local startup script
# Usage: ./start.sh
# Press Ctrl+C to stop both servers

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   PFC AI Agent v2.2  — Local Start   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.10+ first."
  exit 1
fi

# Check Node
if ! command -v node &>/dev/null; then
  echo "ERROR: node not found. Install Node.js 18+ first."
  exit 1
fi

# API key advisory
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo -e "${YELLOW}Note: ANTHROPIC_API_KEY not set.${NC}"
  echo "  PDF extraction feature will be unavailable."
  echo "  All other features (Mode A, Steps 1-8, magnetic design) work without it."
  echo ""
fi

# ── Backend ──────────────────────────────────────────────────────────────────
echo -e "${GREEN}[1/4]${NC} Installing Python dependencies..."
cd backend

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
  echo "      Created Python virtual environment"
fi

source venv/bin/activate
pip install -r requirements.txt -q --disable-pip-version-check 2>&1 | grep -v "^Requirement already"

echo -e "${GREEN}[2/4]${NC} Starting FastAPI backend on http://localhost:8000"
uvicorn app.main:app --reload --port 8000 --log-level warning &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 2
if ! curl -s http://localhost:8000/health >/dev/null 2>&1; then
  echo "      Waiting for backend..."
  sleep 3
fi
echo "      Backend ready ✓"

# ── Frontend ─────────────────────────────────────────────────────────────────
cd ../frontend
echo -e "${GREEN}[3/4]${NC} Installing Node dependencies..."
npm install --silent

echo -e "${GREEN}[4/4]${NC} Starting React frontend on http://localhost:5173"
npm run dev -- --host &
FRONTEND_PID=$!

sleep 2
echo ""
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ PFC AI Agent is running!${NC}"
echo ""
echo -e "  Frontend: ${CYAN}http://localhost:5173${NC}"
echo -e "  Backend:  ${CYAN}http://localhost:8000${NC}"
echo -e "  API docs: ${CYAN}http://localhost:8000/docs${NC}"
echo ""
echo "  Press Ctrl+C to stop both servers"
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo ""

# Cleanup on exit
cleanup() {
  echo ""
  echo "Stopping servers..."
  kill $BACKEND_PID 2>/dev/null
  kill $FRONTEND_PID 2>/dev/null
  deactivate 2>/dev/null
  echo "Done."
  exit 0
}
trap cleanup SIGINT SIGTERM

# Keep alive
wait $FRONTEND_PID
