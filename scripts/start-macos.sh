#!/bin/bash
# Start this app on a Mac that has its own checkout.
# Do not copy another machine's .env, node_modules, or database.
#
# Usage, from the repo root:
#   ./scripts/start-macos.sh docker
#   ./scripts/start-macos.sh native
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:-}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This launcher is for macOS. On Linux use ./start.sh or docker compose up."
  exit 1
fi

if [[ "$MODE" != "docker" && "$MODE" != "native" ]]; then
  echo "Choose docker (Docker Desktop) or native (local Python, Node, Postgres, Redis)."
  exit 1
fi

new_env_from_example() {
  local destination="$1"
  if [[ -f "$destination" ]]; then
    echo "Using existing $destination"
    return
  fi
  cp "$ROOT/.env.example" "$destination"
  echo "Created $destination from .env.example. Set new passwords and secrets before live trading."
}

echo
echo "Dhan live orders need this Mac's own public IPv4 whitelisted at web.dhan.co,"
echo "then a new access token in this machine's .env. Leave LIVE_TRADING_ENABLED=false until then."
echo

if [[ "$MODE" == "docker" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker Desktop is not installed or not on PATH."
    exit 1
  fi
  new_env_from_example "$ROOT/.env"
  docker compose up -d --build
  echo "Open http://localhost after the containers are healthy."
  exit 0
fi

# Native: Postgres and Redis must already be listening on localhost.
new_env_from_example "$ROOT/backend/.env"
sed -i '' \
  -e 's/@postgres:5432/@localhost:5432/' \
  -e 's/@redis:6379/@localhost:6379/' \
  -e 's|redis://:redis_password_here@localhost:6379/0|redis://localhost:6379/0|' \
  "$ROOT/backend/.env"

if command -v python3.12 >/dev/null 2>&1; then
  PYBIN="python3.12"
elif command -v python3 >/dev/null 2>&1; then
  PYBIN="python3"
else
  echo "Install Python 3.12, or Python 3, and run this again."
  exit 1
fi

PY="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  "$PYBIN" -m venv "$ROOT/backend/.venv"
fi
"$PY" -m pip install -r "$ROOT/backend/requirements.txt"

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  (cd "$ROOT/frontend" && npm install)
fi

osascript <<EOF
tell application "Terminal"
  do script "cd '$ROOT/backend' && '$PY' -m uvicorn app.main:app --reload"
  do script "cd '$ROOT/backend' && '$PY' -m celery -A app.worker.celery_app worker --loglevel=info"
  do script "cd '$ROOT/backend' && '$PY' -m celery -A app.worker.celery_app beat --loglevel=info"
  do script "cd '$ROOT/frontend' && npm run dev"
end tell
EOF

echo "API http://localhost:8000  UI http://localhost:5173"
echo "Register a new admin on this empty database. Other machines' users and trades are not here."
