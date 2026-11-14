#!/bin/bash
# Start this app on a Mac.
# A new Mac uses Docker. From the repo root:
#   ./scripts/start-macos.sh
#
# Native installs Python 3.12, Node 22, Postgres 16, and Redis 7, then starts without Docker:
#   ./scripts/start-macos.sh native
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:-docker}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This launcher is for macOS. On Linux use ./start.sh or docker compose up."
  exit 1
fi

if [[ "$MODE" != "docker" && "$MODE" != "native" ]]; then
  echo "Use no argument for Docker, or 'native' for Homebrew Python, Node, Postgres, and Redis."
  exit 1
fi

echo
echo "Dhan live orders need this Mac's own public IPv4 whitelisted at web.dhan.co,"
echo "then a new access token in this machine's .env. Leave LIVE_TRADING_ENABLED=false until then."
echo

ensure_brew() {
  if command -v brew >/dev/null 2>&1; then
    return
  fi
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    return
  fi
  if [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
    return
  fi
  echo "Installing Homebrew."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  else
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

write_env() {
  local dest="$1"
  if [[ -f "$dest" ]]; then
    echo "Using existing $dest"
    return
  fi
  local pg redis jwt secret enc
  pg="$(openssl rand -hex 16)"
  redis="$(openssl rand -hex 16)"
  jwt="$(openssl rand -hex 24)"
  secret="$(openssl rand -hex 24)"
  enc="$(openssl rand -hex 16)"
  sed \
    -e "s/strong_password_here/${pg}/g" \
    -e "s/redis_password_here/${redis}/g" \
    -e "s/your-jwt-secret-key/${jwt}/" \
    -e "s/your-super-secret-key-change-this/${secret}/" \
    -e "s/your-32-byte-encryption-key-here!!/${enc}/" \
    "$ROOT/.env.example" > "$dest"
  echo "Created $dest with new local passwords. The Dhan token is empty. LIVE_TRADING_ENABLED stays false."
}

env_value() {
  local key="$1" file="$2" line
  line="$(grep -E "^${key}=" "$file" | head -1 || true)"
  echo "${line#*=}"
}

wait_http() {
  local url="$1"
  local i
  for i in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  echo "The API did not answer at $url"
  return 1
}

print_admin() {
  local pass out
  pass="$(openssl rand -hex 12)"
  if [[ "${1:-}" == "docker" ]]; then
    out="$(docker compose exec -T -e FIRST_ADMIN_PASSWORD="$pass" backend python -m app.scripts.create_admin)"
  else
    out="$(cd "$ROOT/backend" && FIRST_ADMIN_PASSWORD="$pass" "$ROOT/backend/.venv/bin/python" -m app.scripts.create_admin)"
  fi
  printf '%s\n' "$out"
  if printf '%s\n' "$out" | grep -q "Created admin"; then
    echo "Username: admin"
    echo "Password: $pass"
    echo "This password is shown once. It is not saved in .env."
  fi
}

choose_web_port() {
  if (echo >/dev/tcp/127.0.0.1/80) >/dev/null 2>&1; then
    echo 5173
  else
    echo 80
  fi
}

choose_native_web_port() {
  if python3 -c 'import socket
s=socket.socket()
try:
    s.bind(("0.0.0.0", 80))
except OSError:
    raise SystemExit(1)
finally:
    s.close()' >/dev/null 2>&1; then
    echo 80
  else
    echo 5173
  fi
}

lan_host() {
  local ip
  ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  if [[ -n "$ip" ]]; then
    echo "$ip"
  else
    echo "localhost"
  fi
}

print_home() {
  local port="$1" host url
  host="$(lan_host)"
  if [[ "$port" == "80" ]]; then
    url="http://${host}"
    echo "On this Mac: http://localhost"
  else
    url="http://${host}:${port}"
    echo "On this Mac: http://localhost:${port}"
  fi
  echo "On this home network: ${url}"
  echo "No router port forward is required. Postgres and Redis stay on this Mac."
  echo "macOS may ask to allow incoming connections. Allow it for this private network."
}

if [[ "$MODE" == "docker" ]]; then
  ensure_brew
  export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
  if ! command -v docker >/dev/null 2>&1 && [[ ! -d /Applications/Docker.app ]]; then
    echo "Installing Docker Desktop."
    brew install --cask docker
  fi
  open -a Docker
  echo "Waiting for Docker Desktop."
  ready=0
  for _ in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 5
  done
  if [[ "$ready" != "1" ]]; then
    echo "Docker Desktop did not start. Open it once, wait until it is running, then run this script again."
    exit 1
  fi
  write_env "$ROOT/.env"
  WEB_PORT="$(choose_web_port)"
  export WEB_PORT
  docker compose up -d --build
  if [[ "$WEB_PORT" == "80" ]]; then
    wait_http "http://localhost/api/health"
    open "http://localhost" || true
  else
    wait_http "http://localhost:${WEB_PORT}/api/health"
    open "http://localhost:${WEB_PORT}" || true
  fi
  print_admin docker
  print_home "$WEB_PORT"
  exit 0
fi

# Native versions that match this repo: Python 3.12, Node 22, Postgres 16, Redis 7.
# Do not use the system python3 when it is 3.13 or newer.
ensure_brew
brew install python@3.12 node@22 postgresql@16 redis
brew services start postgresql@16
brew services start redis

export PATH="$(brew --prefix node@22)/bin:$(brew --prefix python@3.12)/bin:$(brew --prefix postgresql@16)/bin:$PATH"
PYBIN="$(brew --prefix python@3.12)/bin/python3.12"
if [[ ! -x "$PYBIN" ]]; then
  echo "Python 3.12 was not installed. Native mode will not use another Python."
  exit 1
fi

write_env "$ROOT/backend/.env"
sed -i '' \
  -e 's/@postgres:5432/@localhost:5432/' \
  -e 's/@redis:6379/@localhost:6379/' \
  -e 's|^REDIS_URL=.*|REDIS_URL=redis://localhost:6379/0|' \
  "$ROOT/backend/.env"

DB_USER="$(env_value POSTGRES_USER "$ROOT/backend/.env")"
DB_PASS="$(env_value POSTGRES_PASSWORD "$ROOT/backend/.env")"
DB_NAME="$(env_value POSTGRES_DB "$ROOT/backend/.env")"
DB_USER="${DB_USER:-algo_user}"
DB_NAME="${DB_NAME:-algo_platform}"

for _ in $(seq 1 30); do
  if pg_isready >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! psql -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
  psql -d postgres -c "CREATE USER \"${DB_USER}\" WITH PASSWORD '${DB_PASS}' LOGIN;"
fi
if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  psql -d postgres -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${DB_USER}\";"
fi

PY="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  "$PYBIN" -m venv "$ROOT/backend/.venv"
fi
"$PY" -m pip install -r "$ROOT/backend/requirements.txt"

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  (cd "$ROOT/frontend" && npm install)
fi

WEB_PORT="$(choose_native_web_port)"
osascript <<EOF
tell application "Terminal"
  do script "cd '$ROOT/backend' && '$PY' -m uvicorn app.main:app --reload"
  do script "cd '$ROOT/backend' && '$PY' -m celery -A app.worker.celery_app worker --loglevel=info"
  do script "cd '$ROOT/backend' && '$PY' -m celery -A app.worker.celery_app beat --loglevel=info"
  do script "cd '$ROOT/frontend' && npm run dev -- --host 0.0.0.0 --port $WEB_PORT --strictPort"
end tell
EOF
print_home "$WEB_PORT"

if wait_http "http://localhost:8000/api/health"; then
  print_admin native
fi
if [[ "$WEB_PORT" == "80" ]]; then
  echo "API http://localhost:8000  UI http://localhost"
else
  echo "API http://localhost:8000  UI http://localhost:${WEB_PORT}"
fi
