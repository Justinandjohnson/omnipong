#!/usr/bin/env bash
# OmniPong / Rubberr — run the whole stack with one command.
#
#   ./dev.sh start     start relay + companion + backend (:8000) + frontend (:3000)
#   ./dev.sh stop      stop them all (and free the ports)
#   ./dev.sh restart   stop, then start
#   ./dev.sh status    show what's running
#   ./dev.sh logs      tail the logs
#
# Every process is launched concurrently and tracked with pidfiles under .run/.
# Stopping kills the whole process tree, so npm/next children and the uvicorn
# reload worker all go down together.
#
# The relay + companion only start when they are set up: relay/local.env must
# exist (it holds RELAY_OPERATOR_TOKEN, RELAY_REGISTER_TOKEN, ...) and the
# relay/ and companion/ virtualenvs must be present. Without them the backend
# and frontend still come up; relay-backed features (USATT lookup) stay off.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
PID_DIR="$RUN_DIR/pids"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
RELAY_PORT="${RELAY_PORT:-8765}"
COMPANION_GATE_PORT="${COMPANION_GATE_PORT:-8766}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
RELAY_PY="$ROOT/relay/.venv/bin/python"
COMPANION_PY="$ROOT/companion/.venv/bin/python"
RELAY_ENV_FILE="${RELAY_ENV_FILE:-$ROOT/relay/local.env}"

API_URL="http://localhost:${BACKEND_PORT}"
APP_URL="http://localhost:${FRONTEND_PORT}"
RELAY_URL="http://127.0.0.1:${RELAY_PORT}"

mkdir -p "$LOG_DIR" "$PID_DIR"

c_grn=$'\033[32m'; c_red=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
info() { printf '%s\n' "$*"; }
ok()   { printf '%s%s%s\n' "$c_grn" "$*" "$c_off"; }
warn() { printf '%s%s%s\n' "$c_dim" "$*" "$c_off"; }
err()  { printf '%s%s%s\n' "$c_red" "$*" "$c_off" >&2; }

# Load relay secrets (gitignored) into the environment so the backend and the
# relay server both see RELAY_OPERATOR_TOKEN / OPERATOR_TOKEN / RELAY_BASE_URL.
if [[ -f "$RELAY_ENV_FILE" ]]; then
  set -a; . "$RELAY_ENV_FILE"; set +a
fi
export RELAY_BASE_URL="${RELAY_BASE_URL:-http://127.0.0.1:${RELAY_PORT}}"

kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do kill_tree "$child"; done
  kill "$pid" 2>/dev/null || true
}

port_pids() { lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }
pid_alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

wait_http() {
  local url="$1" tries="${2:-60}"
  for _ in $(seq 1 "$tries"); do
    if curl -fsS -m 1 -o /dev/null "$url" 2>/dev/null; then return 0; fi
    sleep 0.5
  done
  return 1
}

start_one() {
  local name="$1" workdir="$2"; shift 2
  local pidfile="$PID_DIR/$name.pid" logfile="$LOG_DIR/$name.log"
  if [[ -f "$pidfile" ]] && pid_alive "$(cat "$pidfile" 2>/dev/null)"; then
    ok "$name already running (pid $(cat "$pidfile"))"
    return 0
  fi
  ( cd "$workdir" && nohup "$@" >"$logfile" 2>&1 & echo $! >"$pidfile" )
}

relay_available() {
  [[ -x "$RELAY_PY" && -f "$ROOT/relay/register_tokens.json" && -n "${RELAY_OPERATOR_TOKEN:-}" ]]
}
companion_available() {
  [[ -x "$COMPANION_PY" && -n "${RELAY_REGISTER_TOKEN:-}" ]]
}

start() {
  info "Starting Rubberr stack…"

  # Clear any stale listeners first so nothing fails on a busy port.
  local p pid
  for p in "$BACKEND_PORT" "$FRONTEND_PORT" "$RELAY_PORT" "$COMPANION_GATE_PORT"; do
    for pid in $(port_pids "$p"); do kill_tree "$pid" 2>/dev/null || true; done
  done

  if relay_available; then
    start_one relay "$ROOT" "$RELAY_PY" relay/server.py
    info "waiting for relay…"
    if wait_http "$RELAY_URL/health" 20; then ok "relay    ready   $RELAY_URL"; else err "relay did not come up — see $LOG_DIR/relay.log"; fi
  else
    warn "relay: skipped (need relay/.venv, relay/register_tokens.json, and relay/local.env)"
  fi

  # Companion starts only after the relay is listening, so its first connect
  # can't race the relay's own startup and die with a connection error.
  if companion_available; then
    start_one companion "$ROOT/companion" "$COMPANION_PY" companion.py \
      --relay-base-url "ws://127.0.0.1:${RELAY_PORT}" \
      --register-token "$RELAY_REGISTER_TOKEN" \
      --gate-ui-port "$COMPANION_GATE_PORT"
  else
    warn "companion: skipped (need companion/.venv and RELAY_REGISTER_TOKEN)"
  fi

  start_one backend "$ROOT" \
    env "$PYTHON_BIN" -m uvicorn rubberr.backend.main:app \
      --host 127.0.0.1 --port "$BACKEND_PORT" --reload

  start_one frontend "$ROOT/rubberr/frontend" \
    env NEXT_PUBLIC_API_URL="$API_URL" NEXT_PUBLIC_OPERATOR_TOKEN="${OPERATOR_TOKEN:-}" \
      npm run dev -- --port "$FRONTEND_PORT"

  info "waiting for backend…"
  if wait_http "$API_URL/agent/actions" 40; then ok "backend  ready   $API_URL"; else err "backend  did not come up — see $LOG_DIR/backend.log"; fi
  info "waiting for frontend…"
  if wait_http "$APP_URL" 60; then ok "frontend ready   $APP_URL"; else err "frontend did not come up — see $LOG_DIR/frontend.log"; fi

  echo
  ok   "App:   $APP_URL"
  info "API:   $API_URL"
  [[ "$(companion_available && echo y || echo n)" == "y" ]] && info "Agent browser: companion running (gate UI http://127.0.0.1:${COMPANION_GATE_PORT})"
  info "Logs:  ./dev.sh logs      Stop:  ./dev.sh stop"
}

stop() {
  info "Stopping Rubberr stack…"
  local stopped=0 svc pidfile pid p
  for svc in frontend backend companion relay; do
    pidfile="$PID_DIR/$svc.pid"
    if [[ -f "$pidfile" ]]; then
      pid="$(cat "$pidfile" 2>/dev/null || true)"
      if pid_alive "$pid"; then kill_tree "$pid"; ok "stopped $svc (pid $pid)"; stopped=1; fi
      rm -f "$pidfile"
    fi
  done
  for p in "$BACKEND_PORT" "$FRONTEND_PORT" "$RELAY_PORT" "$COMPANION_GATE_PORT"; do
    for pid in $(port_pids "$p"); do kill_tree "$pid"; ok "stopped pid $pid on :$p"; stopped=1; done
  done
  if [[ "$stopped" -eq 0 ]]; then info "nothing was running"; else ok "all stopped"; fi
}

status() {
  local svc pidfile pid state
  for svc in relay companion backend frontend; do
    pidfile="$PID_DIR/$svc.pid"; pid=""
    [[ -f "$pidfile" ]] && pid="$(cat "$pidfile" 2>/dev/null || true)"
    if pid_alive "$pid"; then state="running (pid $pid)"; else state="stopped"; fi
    printf '  %-9s %s\n' "$svc" "$state"
  done
  printf '  %-9s %s :%s\n' "relay" "$(curl -fsS -m 2 -o /dev/null "$RELAY_URL/health" 2>/dev/null && echo up || echo down)" "$RELAY_PORT"
  printf '  %-9s %s :%s\n' "api" "$(curl -fsS -m 2 -o /dev/null "$API_URL/agent/actions" 2>/dev/null && echo up || echo down)" "$BACKEND_PORT"
  printf '  %-9s %s :%s\n' "app" "$(curl -fsS -m 2 -o /dev/null "$APP_URL" 2>/dev/null && echo up || echo down)" "$FRONTEND_PORT"
}

logs() { tail -n 40 -f "$LOG_DIR"/*.log; }

usage() {
  cat <<EOF
Usage: ./dev.sh <command>

  start | up      start relay + companion + backend + frontend together
  stop  | down    stop them all and free the ports
  restart         stop, then start
  status          show what's running
  logs            tail all logs

Ports: BACKEND_PORT=$BACKEND_PORT  FRONTEND_PORT=$FRONTEND_PORT
       RELAY_PORT=$RELAY_PORT  COMPANION_GATE_PORT=$COMPANION_GATE_PORT
Relay secrets: $RELAY_ENV_FILE (gitignored; see docs/PLATFORM_RUNBOOK.md)
EOF
}

case "${1:-start}" in
  start|up)     start ;;
  stop|down)    stop ;;
  restart)      stop; start ;;
  status)       status ;;
  logs)         logs ;;
  -h|--help|help) usage ;;
  *)            err "unknown command: $1"; usage; exit 1 ;;
esac
