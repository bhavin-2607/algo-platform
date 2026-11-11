# Algo Trading Platform

Private multi-user trading platform. Strategies run on the server. Users see names and parameters, not engine code.

There are two editions:

- **Standalone** (Linux, Windows, Mac) runs the app only. No Prometheus or Grafana.
- **Linux server** adds Prometheus. Alert rules cover a stale feed, the kill switch, and live order rejects.

Each machine gets its own empty database and its own `.env`. Do not copy a `.env`, `node_modules`, or a database from another machine. Dhan must whitelist that machine's public IPv4 before live orders will be accepted.

Leave `LIVE_TRADING_ENABLED=false` until you have run a paper session, seen a real Dhan fill through the app, flattened once with the kill switch, and restarted with a position still open.

## Standalone

A new Windows PC or Mac does not need Python, Node, Postgres, or Redis installed first. The launcher installs Docker Desktop and starts the app. The site is http://localhost. API docs (development only): http://localhost/api/docs.

Windows, from the repo root, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1
```

If Windows asks for a restart (WSL or Docker Desktop), restart the PC and run that same command again.

Mac, from the repo root:

```bash
./scripts/start-macos.sh
```

The first time the database has no users, the script prints an admin username and password once. That password is not written into `.env`. Sign in with it, then change it from Settings. Public registration stays closed.

Linux, when Docker is already installed:

```bash
cp .env.example .env
docker compose up -d --build
```

Then create the first admin from the backend container:

```bash
docker compose exec -e FIRST_ADMIN_PASSWORD='choose-a-password' backend python -m app.scripts.create_admin
```

Native mode installs the versions this repo is built for, then starts the API, worker, beat, and Vite on the machine. Python stays on 3.12, the same as the Docker image and the pinned requirements. Node is 22, which Vite 5 accepts. Postgres is 16, the same major version as Compose. Redis uses the Redis 7 protocol that the Python client and Celery are written for. Celery on Windows uses the solo pool. On Mac it uses the normal prefork pool.

| Machine | Command | What it installs |
|---|---|---|
| Linux | `./start.sh` | Nothing. Python, Node, Postgres, and Redis must already be running. |
| Windows | `powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1 -Native` | Python 3.12, Node.js 22, PostgreSQL 16, and Memurai (Redis 7 protocol; Windows has no current Redis build) |
| Mac | `./scripts/start-macos.sh native` | Python 3.12, Node 22, PostgreSQL 16, and Redis through Homebrew |

The native scripts create `backend/.env` when it is missing, point Postgres and Redis at localhost, create the database role, and print the first admin password once. Start later native processes from `backend/` so settings load that file.

## Linux server

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d --build
```

Set `GRAFANA_PASSWORD` in `.env` for this edition. Prometheus is on port 9090 and loads `monitoring/prometheus/alerts.yml`. Standalone Compose does not start it.

The API exposes `/metrics`. Feed-stale, kill-switch, and live order-reject values are read from Redis at scrape time, so the Celery worker and the API share one count.

## Adding a strategy

Drop one Python file in `strategy/` at the repo root. It needs one `BaseStrategy` subclass, an `engine_id`, and a `version`. Built-in engines `moving_average_crossover` and `opening_range_fibonacci` cannot be replaced.

Reload plugins from Admin, create the catalogue row, and assign it. Paper assign is allowed immediately. Live start stays blocked until an admin enables that version, and until the latest saved backtest for that version and symbol is not a loss. A missing backtest does not block.

The in-app Guide page (`/guide`) compares those stored runs and lists the formula and go-live checks.

## Formulas

Formulas use an allow-list: `ma`, `ema`, `rsi`, `vwap`, `atr`, `bb_upper`, `bb_lower`, `supertrend`, `abs`, `min`, `max`, `round`. Preview a formula on Dhan history before saving. Equity symbols such as `RELIANCE` resolve through the trading symbol on the instrument file.

## Tests

```bash
cd backend && python3 -m unittest tests.test_production_gates tests.test_strategy_phase3 tests.test_backtest_runner tests.test_ops_metrics tests.test_history_resolve
```

## Layout

```
algo-platform/
├── backend/          FastAPI, broker adapters, strategies, risk
├── frontend/         React dashboard
├── strategy/         Extra strategy plugins
├── scripts/          Windows and Mac start scripts
├── monitoring/       Prometheus config and alert rules (server edition)
├── nginx/            Reverse proxy
└── docker-compose.server.yml
```
