#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_DIR="$ROOT_DIR/web"

if [[ ! -x "$VENV_DIR/bin/uvicorn" ]]; then
  echo "uvicorn not found in $VENV_DIR. Install API deps first:" >&2
  echo "  uv venv --python 3.12 .venv && uv pip install -e '.[dev]'" >&2
  exit 1
fi

if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  echo "web/node_modules not found. Install web deps first:" >&2
  echo "  npm install --prefix web" >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/.env" && -f "$ROOT_DIR/.env.example" ]]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  echo "Created .env from .env.example"
fi

find_free_port() {
  local host="$1" start_port="$2"
  python3 - "$host" "$start_port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

while port < 65535:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            port += 1
            continue
        print(port)
        break
else:
    sys.exit(1)
PY
}

if ! free_port="$(find_free_port "$API_HOST" "$API_PORT")"; then
  echo "No free port found for API starting at $API_PORT" >&2
  exit 1
fi
if [[ "$free_port" != "$API_PORT" ]]; then
  echo "Port $API_PORT is in use, switching API to port $free_port"
  API_PORT="$free_port"
fi

pids=()

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Stopping dev servers..."
  for pid in "${pids[@]}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}

trap cleanup INT TERM EXIT

echo "API -> http://$API_HOST:$API_PORT (docs: http://$API_HOST:$API_PORT/docs)"
setsid bash -c "cd '$ROOT_DIR' && exec '$VENV_DIR/bin/uvicorn' app.main:app --reload --host '$API_HOST' --port '$API_PORT'" &
pids+=("$!")

echo "Web -> see Vite output below"
setsid bash -c "cd '$WEB_DIR' && exec npm run dev -- --host '$WEB_HOST'" &
pids+=("$!")

wait -n "${pids[@]}" || true
