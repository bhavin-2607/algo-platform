#!/bin/bash
set -e

PROJECT_DIR="/Users/bhavinamesara/Projects/algo-platform"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

# Ensure Homebrew is in PATH
export PATH="/opt/homebrew/bin:$PATH"

echo "=== Algo Platform — Launching on Mac (iTerm2) ==="

# Check if Redis is running
if ! nc -z localhost 6379 2>/dev/null; then
  echo "⚠️  Redis is not running on port 6379. Starting Homebrew redis..."
  /opt/homebrew/bin/redis-server --daemonize yes 2>/dev/null || true
fi

# Check if PostgreSQL is running; if not, forward from the remote Pi
if ! nc -z localhost 5432 2>/dev/null; then
  echo "⚠️  PostgreSQL is not listening on port 5432."
  echo "Connecting to PostgreSQL on Pi (192.168.29.115) via SSH tunnel..."
  sshpass -p groot ssh -o StrictHostKeyChecking=no -f -N -L 5432:127.0.0.1:5432 groot@192.168.29.115 2>/dev/null || true
  sleep 1
fi

# Commands for each service
CMD_BACKEND="cd '$BACKEND_DIR' && export PATH='/opt/homebrew/bin:\$PATH' && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
CMD_WORKER="cd '$BACKEND_DIR' && export PATH='/opt/homebrew/bin:\$PATH' && source .venv/bin/activate && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES celery -A app.worker.celery_app worker --loglevel=info -P solo"
CMD_FRONTEND="cd '$FRONTEND_DIR' && export PATH='/opt/homebrew/bin:\$PATH' && npm run dev"
CMD_BEAT="cd '$BACKEND_DIR' && export PATH='/opt/homebrew/bin:\$PATH' && source .venv/bin/activate && celery -A app.worker.celery_app beat --loglevel=info"

echo "Opening 4 tabs in iTerm2..."

osascript <<EOF
tell application "iTerm"
  activate
  set newWindow to (create window with default profile)
  
  -- Tab 1: Backend
  tell current session of newWindow
    set name to "Backend"
    write text "$CMD_BACKEND"
  end tell
  
  -- Tab 2: Celery Worker
  tell newWindow
    set tabWorker to (create tab with default profile)
    tell current session of tabWorker
      set name to "Celery Worker"
      write text "$CMD_WORKER"
    end tell
    
    -- Tab 3: Frontend
    set tabFrontend to (create tab with default profile)
    tell current session of tabFrontend
      set name to "Frontend"
      write text "$CMD_FRONTEND"
    end tell
    
    -- Tab 4: Celery Beat
    set tabBeat to (create tab with default profile)
    tell current session of tabBeat
      set name to "Celery Beat"
      write text "$CMD_BEAT"
    end tell
  end tell
end tell
EOF

echo "✅ All 4 services launched in iTerm2 tabs (Backend, Celery Worker, Frontend, Celery Beat)."
