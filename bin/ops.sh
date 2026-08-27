#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
PID_FILE="$RUN_DIR/uvicorn.pid"
LOG_FILE="$RUN_DIR/uvicorn.log"
ENV_FILE="$ROOT_DIR/.env"

mkdir -p "$RUN_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

HOST="${PI_PLATFORM_HOST:-127.0.0.1}"
PORT="${PI_PLATFORM_PORT:-8000}"

read_pid() {
  [[ -f "$PID_FILE" ]] && tr -d '[:space:]' < "$PID_FILE" || true
}

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start() {
  local pid
  pid="$(read_pid)"
  if is_running "$pid"; then
    echo "pi studio is already running (pid $pid) at http://$HOST:$PORT"
    return 0
  fi

  cd "$ROOT_DIR"
  nohup uv run uvicorn app.main:app --env-file .env --host "$HOST" --port "$PORT" --reload \
    >> "$LOG_FILE" 2>&1 &
  echo "$!" > "$PID_FILE"
  echo "started pi studio (pid $!)"
  echo "url: http://$HOST:$PORT"
}

stop() {
  local pid
  pid="$(read_pid)"
  if ! is_running "$pid"; then
    rm -f "$PID_FILE"
    echo "pi studio is not running"
    return 0
  fi

  kill "$pid"
  for _ in {1..20}; do
    if ! is_running "$pid"; then
      rm -f "$PID_FILE"
      echo "stopped pi studio"
      return 0
    fi
    sleep 0.25
  done

  echo "pi studio did not stop within 5 seconds (pid $pid)" >&2
  return 1
}

status() {
  local pid
  pid="$(read_pid)"
  if is_running "$pid"; then
    if curl --silent --show-error --fail --max-time 2 "http://$HOST:$PORT/api/health" >/dev/null; then
      echo "pi studio is running (pid $pid) and healthy at http://$HOST:$PORT"
    else
      echo "pi studio process is running (pid $pid), health endpoint unavailable"
      return 1
    fi
  else
    echo "pi studio is stopped"
    return 1
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop || true; start ;;
  status) status ;;
  *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
