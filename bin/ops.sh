#!/usr/bin/env bash
# OMA Studio operations — Docker Compose mode.
#   bin/ops.sh start [PORT]|start-dev [PORT]|stop|restart [PORT]|status [PORT]|logs
# The container serves the API and UI on ${OMA_PORT:-8000}; storage lives in
# ~/.oma-studio/ and ~/.pi/agent via the mounts in docker-compose.yml.
#
# Local development with hot reload (no Docker):
#   uv run uvicorn app.main:app --env-file .env --reload
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Prefer the compose plugin, fall back to the standalone binary.
if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
else
  DC=(docker-compose)
fi

PORT=""
SERVICE="oma-studio"

usage() {
  echo "Usage: $0 {start|start-dev|restart|status} [PORT|-p PORT] | {stop|logs}" >&2
  echo "  PORT defaults to OMA_PORT or 8000 and changes the host port only." >&2
}

resolve_port() {
  local candidate="${OMA_PORT:-8000}"
  if [[ $# -eq 1 ]]; then
    candidate="$1"
  elif [[ $# -eq 2 && "$1" == "-p" ]]; then
    candidate="$2"
  elif [[ $# -gt 0 ]]; then
    usage
    exit 2
  fi

  if ! [[ "$candidate" =~ ^[0-9]+$ ]] || ((candidate < 1 || candidate > 65535)); then
    echo "Invalid port: $candidate (expected an integer from 1 to 65535)" >&2
    exit 2
  fi
  PORT="$candidate"
  export OMA_PORT="$PORT"
}

start() {
  "${DC[@]}" up -d --build
  wait_healthy || true
  status
}

start_dev() {
  exec uv run uvicorn app.main:app --env-file .env --port "$PORT" --reload
}

# Wait for the app to answer /api/health (image build + uvicorn boot take a moment).
wait_healthy() {
  local i
  for i in $(seq 1 15); do
    if curl --silent --fail --max-time 2 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

stop() {
  "${DC[@]}" down
}

restart() {
  stop || true
  start
}

status() {
  if "${DC[@]}" ps --status running --services 2>/dev/null | grep -qx "$SERVICE"; then
    if curl --silent --show-error --fail --max-time 3 "http://127.0.0.1:${PORT}/api/health" >/dev/null; then
      echo "oma-studio is running (docker) and healthy at http://127.0.0.1:${PORT}"
    else
      echo "oma-studio container is up but the health endpoint is unreachable on port ${PORT}"
      echo "check: ${DC[*]} logs ${SERVICE}"
      return 1
    fi
  else
    echo "oma-studio is stopped"
    return 1
  fi
}

logs() {
  "${DC[@]}" logs -f --tail 100 "$SERVICE"
}

case "${1:-}" in
  start|start-dev|restart|status)
    resolve_port "${@:2}"
    if [[ "$1" == "start-dev" ]]; then
      start_dev
    else
      "${1}"
    fi
    ;;
  stop|logs)
    if [[ $# -ne 1 ]]; then
      usage
      exit 2
    fi
    "${1}"
    ;;
  *)
    usage
    echo "  Local dev server (hot reload): uv run uvicorn app.main:app --env-file .env --reload" >&2
    exit 2
    ;;
esac
