#!/usr/bin/env bash
# start.sh — local dev launcher for ISHA
# Usage: ./start.sh [--port N] [--skip-verify] [--reset]

set -euo pipefail

# ── colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✅  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $*${NC}"; }
err()  { echo -e "${RED}❌  $*${NC}"; }
info() { echo -e "${CYAN}ℹ️   $*${NC}"; }

# ── defaults ──────────────────────────────────────────────────────────────────
PORT=8501
SKIP_VERIFY=false
RESET=false

# ── arg parse ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --port)        PORT="$2"; shift 2 ;;
    --skip-verify) SKIP_VERIFY=true; shift ;;
    --reset)       RESET=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--port N] [--skip-verify] [--reset]"
      echo "  --port N        Streamlit port (default 8501)"
      echo "  --skip-verify   Skip Qdrant data check"
      echo "  --reset         Re-ingest documents (--reset --verify)"
      exit 0 ;;
    *) err "Unknown argument: $1"; exit 1 ;;
  esac
done

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   ✈️  ISHA — IndiGo Smart Helpdesk Assistant  ║${NC}"
echo -e "${BOLD}║         Local Development Launcher            ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. working directory ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
info "Working directory: $SCRIPT_DIR"

# ── 2. check uv ───────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  err "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
ok "uv $(uv --version 2>&1 | head -1)"

# ── 3. check .env ─────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  err ".env not found. Copy and fill: cp .env.example .env"
  exit 1
fi
ok ".env found"

# ── 4. validate required env vars ─────────────────────────────────────────────
set -a; source .env; set +a

REQUIRED_VARS=(OPENAI_API_KEY QDRANT_URL QDRANT_API_KEY)
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
  val="${!var:-}"
  if [[ -z "$val" || "$val" == sk-...* || "$val" == https://your-* || "$val" == your-* ]]; then
    MISSING+=("$var")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  err "Missing or placeholder values in .env:"
  for v in "${MISSING[@]}"; do err "  $v"; done
  exit 1
fi
ok "Required env vars set (OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY)"

# ANTHROPIC_API_KEY is optional (falls back to OpenAI)
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
if [[ -z "$ANTHROPIC_API_KEY" ]]; then
  warn "ANTHROPIC_API_KEY not set — will use OpenAI gpt-4o-mini fallback for answers"
else
  ok "ANTHROPIC_API_KEY set — using claude-opus-4-8 for answers"
fi

# ── 5. install / sync deps ────────────────────────────────────────────────────
info "Syncing dependencies..."
uv sync --quiet
ok "Dependencies up to date"

# ── 6. Qdrant data check / ingest ─────────────────────────────────────────────
if [[ "$RESET" == true ]]; then
  info "Re-ingesting documents (--reset)..."
  uv run python scripts/ingest.py --reset --verify
  ok "Ingestion complete"
elif [[ "$SKIP_VERIFY" == false ]]; then
  info "Verifying Qdrant data..."
  VERIFY_OUT=$(uv run python scripts/ingest.py --verify 2>&1)
  if echo "$VERIFY_OUT" | grep -q "no results\|Error\|error\|Exception"; then
    err "Qdrant verification failed:"
    echo "$VERIFY_OUT"
    echo ""
    warn "Run with --reset to ingest: ./start.sh --reset"
    exit 1
  fi
  # Extract vector count if present
  COUNT=$(echo "$VERIFY_OUT" | grep -oE '[0-9]+ vectors' | head -1 || true)
  ok "Qdrant ready${COUNT:+ — $COUNT loaded}"
else
  warn "Skipping Qdrant verify (--skip-verify)"
fi

# ── 7. port availability check ────────────────────────────────────────────────
if lsof -ti:"$PORT" &>/dev/null; then
  warn "Port $PORT already in use. Killing existing process..."
  lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# ── 8. launch ─────────────────────────────────────────────────────────────────
echo ""
ok "All checks passed — launching Streamlit on port $PORT"
echo -e "${BOLD}  Local URL:  http://localhost:${PORT}${NC}"
echo ""

# Trap Ctrl+C for clean shutdown
cleanup() {
  echo ""
  info "Shutting down ISHA..."
  kill "$STREAMLIT_PID" 2>/dev/null || true
  echo -e "${GREEN}Goodbye.${NC}"
  exit 0
}
trap cleanup INT TERM

uv run streamlit run app.py \
  --server.port "$PORT" \
  --server.headless false \
  --browser.gatherUsageStats false &
STREAMLIT_PID=$!

wait "$STREAMLIT_PID"
