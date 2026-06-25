#!/usr/bin/env bash
# stop.sh — gracefully stop ISHA Streamlit service
# Usage: ./stop.sh [--port N]

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✅  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $*${NC}"; }
err()  { echo -e "${RED}❌  $*${NC}"; }
info() { echo -e "${CYAN}ℹ️   $*${NC}"; }

PORT=8501

while [[ $# -gt 0 ]]; do
  case $1 in
    --port) PORT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--port N]"
      echo "  --port N    Streamlit port to stop (default 8501)"
      exit 0 ;;
    *) err "Unknown argument: $1"; exit 1 ;;
  esac
done

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  ✈️  ISHA — Stop Service                      ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── Find PIDs on the port ──────────────────────────────────────────────────
PIDS=$(lsof -ti:"$PORT" 2>/dev/null || true)

if [[ -z "$PIDS" ]]; then
  warn "No process found on port $PORT — ISHA may already be stopped."
  exit 0
fi

info "Found process(es) on port $PORT: $PIDS"

# ── SIGTERM — graceful shutdown ────────────────────────────────────────────
info "Sending SIGTERM..."
echo "$PIDS" | xargs kill -TERM 2>/dev/null || true

# ── Wait up to 5 seconds for clean exit ───────────────────────────────────
WAITED=0
while [[ $WAITED -lt 5 ]]; do
  REMAINING=$(lsof -ti:"$PORT" 2>/dev/null || true)
  if [[ -z "$REMAINING" ]]; then
    break
  fi
  sleep 1
  (( WAITED++ )) || true
done

# ── SIGKILL if still alive ─────────────────────────────────────────────────
REMAINING=$(lsof -ti:"$PORT" 2>/dev/null || true)
if [[ -n "$REMAINING" ]]; then
  warn "Process did not exit after ${WAITED}s — sending SIGKILL..."
  echo "$REMAINING" | xargs kill -KILL 2>/dev/null || true
  sleep 1
fi

# ── Confirm ───────────────────────────────────────────────────────────────
if lsof -ti:"$PORT" &>/dev/null; then
  err "Could not stop process on port $PORT."
  exit 1
fi

ok "ISHA stopped (port $PORT is free)."
echo ""
