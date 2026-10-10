#!/usr/bin/env bash
set -euo pipefail

"$VENV_DIR/bin/uvicorn" app.main:app \
  --host 127.0.0.1 \
  --port 8001 \
  --workers 1 &
api_pid=$!

nginx -g 'daemon off;' &
nginx_pid=$!

cleanup() {
  trap - EXIT INT TERM
  kill -TERM "$api_pid" "$nginx_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
  wait "$nginx_pid" 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 0' INT TERM

if wait -n "$api_pid" "$nginx_pid"; then
  exit 0
else
  exit $?
fi
