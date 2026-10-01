#!/usr/bin/env bash
# OmniPong / Rubberr — run the whole stack (backend + frontend) with one command.
#
#   ./dev.sh start     start backend (:8000) and frontend (:3000) together
#   ./dev.sh stop      stop both (and free the ports)
#   ./dev.sh restart   stop, then start
#   ./dev.sh status    show what's running
#   ./dev.sh logs      tail both logs
#
# Both processes are launched concurrently and tracked with pidfiles under
# .run/. Stopping kills the whole process tree, so `npm`/`next` children and
# the uvicorn reload worker all go down together.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
PID_DIR="$RUN_DIR/pids"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
API_URL="http://localhost:${BACKEND_PORT}"
APP_URL="http://localhost:${FRONTEND_PORT}"

mkdir -p "$LOG_DIR" "$PID_DIR"

c_grn=$'\033[32m'; c_red=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
info() { printf '%s\n' "$*"; }
ok()   { printf '%s%s%s\n' "$c_grn" "$*" "$c_off"; }
err()  { printf '%s%s%s\n' "$c_red" "$*" "$c_off" >&2; }

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
    if curl -fsS -m 2 -o /dev/null "$url" 2>/dev/null; then return 0; fi
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

start() {
  info "Starting Rubberr stack…"

  start_one backend "$ROOT" \
    env "$PYTHON_BIN" -m uvicorn rubberr.backend.main:app \
      --host 127.0.0.1 --port "$BACKEND_PORT" --reload

  start_one frontend "$ROOT/rubberr/frontend" \
    env NEXT_PUBLIC_API_URL="$API_URL" npm run dev -- --port "$FRONTEND_PORT"

  if wait_http "$API_URL/agent/actions" 60; then ok "backend  ready   $API_URL"; else err "backend  did not come up — see $LOG_DIR/backend.log"; fi
  if wait_http "$APP_URL" 160; then ok "frontend ready   $APP_URL"; else err "frontend did not come up — see $LOG_DIR/frontend.log"; fi

  echo
  ok   "App:   $APP_URL"
  info "API:   $API_URL"
  info "Logs:  ./dev.sh logs      Stop:  ./dev.sh stop"
  info "${c_dim}Open the app via localhost (not 127.0.0.1) so it can reach the API.${c_off}"
}

stop() {
  info "Stopping Rubberr stack…"
  local stopped=0 svc pidfile pid p
  for svc in backend frontend; do
    pidfile="$PID_DIR/$svc.pid"
    if [[ -f "$pidfile" ]]; then
      pid="$(cat "$pidfile" 2>/dev/null || true)"
      if pid_alive "$pid"; then kill_tree "$pid"; ok "stopped $svc (pid $pid)"; stopped=1; fi
      rm -f "$pidfile"
    fi
  done
  for p in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    for pid in $(port_pids "$p"); do kill_tree "$pid"; ok "stopped pid $pid on :$p"; stopped=1; done
  done
  if [[ "$stopped" -eq 0 ]]; then info "nothing was running"; else ok "all stopped"; fi
}

status() {
  local svc pidfile pid state
  for svc in backend frontend; do
    pidfile="$PID_DIR/$svc.pid"; pid=""
    [[ -f "$pidfile" ]] && pid="$(cat "$pidfile" 2>/dev/null || true)"
    if pid_alive "$pid"; then state="running (pid $pid)"; else state="stopped"; fi
    printf '  %-9s %s\n' "$svc" "$state"
  done
  printf '  %-9s %s :%s\n' "api" "$(curl -fsS -m 2 -o /dev/null "$API_URL/agent/actions" 2>/dev/null && echo up || echo down)" "$BACKEND_PORT"
  printf '  %-9s %s :%s\n' "app" "$(curl -fsS -m 2 -o /dev/null "$APP_URL" 2>/dev/null && echo up || echo down)" "$FRONTEND_PORT"
}

logs() { tail -n 40 -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"; }

usage() {
  cat <<EOF
Usage: ./dev.sh <command>

  start | up      start backend + frontend together
  stop  | down    stop both and free the ports
  restart         stop, then start
  status          show what's running
  logs            tail both logs

Ports: BACKEND_PORT=$BACKEND_PORT  FRONTEND_PORT=$FRONTEND_PORT (override via env)
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
