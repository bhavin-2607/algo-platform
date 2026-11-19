#!/bin/bash
# ==============================================================================
# Algo Platform — Desktop GUI Launcher (macOS & Linux)
# ==============================================================================
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Ensure Homebrew in PATH on macOS
if [[ -d "/opt/homebrew/bin" ]]; then
  export PATH="/opt/homebrew/bin:$PATH"
fi

if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  exec "$ROOT/backend/.venv/bin/python" "$ROOT/desktop_launcher.py" "$@"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" "$ROOT/desktop_launcher.py" "$@"
elif command -v python3 >/dev/null 2>&1; then
  exec python3 "$ROOT/desktop_launcher.py" "$@"
else
  echo "Error: Python 3 is not installed or not in PATH."
  exit 1
fi
