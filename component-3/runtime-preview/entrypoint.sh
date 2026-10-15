#!/bin/sh
# Runs inside Docker only. Never use on the Windows host for generated code.
set -eu

WS=/tmp/generated-workspace

copy_workspace() {
  rm -rf "$WS"
  mkdir -p "$WS"
  if [ ! -d /workspace-ro/backend ] || [ ! -d /workspace-ro/frontend ]; then
    echo "ERROR: verified workspace must contain backend/ and frontend/." >&2
    exit 1
  fi
  cp -a /workspace-ro/. "$WS/"
}

install_deps() {
  (cd "$WS/backend" && npm install --ignore-scripts --no-audit --no-fund)
  (cd "$WS/frontend" && npm install --ignore-scripts --no-audit --no-fund --include=dev)
}

start_backend() {
  cd "$WS/backend"
  export CORS_ALLOWED_ORIGIN="${CORS_ALLOWED_ORIGIN:-http://127.0.0.1:5180}"
  node src/app.js &
  echo $! >/tmp/backend.pid
}

start_backend_adapter() {
  node /usr/local/lib/intelise-c3/preview-backend-proxy.mjs &
  echo $! >/tmp/proxy.pid
}

wait_for_backend() {
  i=0
  while [ "$i" -lt 60 ]; do
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/v1/tasks" >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 0.5
  done
  echo "Backend did not become ready on port ${BACKEND_PORT}" >&2
  return 1
}

copy_workspace
install_deps
start_backend
wait_for_backend
start_backend_adapter

cd "$WS/frontend"
exec node node_modules/vite/bin/vite.js --host 0.0.0.0 --port "${FRONTEND_PORT}"
