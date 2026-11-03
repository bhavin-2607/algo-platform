# Algo Trading Platform

Private multi-user trading platform. Strategies run on the server. Users see names and parameters, not engine code.

There are two editions:

- **Standalone** (Linux, Windows, Mac) runs the app only. No Prometheus or Grafana.
- **Linux server** adds Prometheus. Alert rules cover a stale feed, the kill switch, and live order rejects.

Each machine gets its own empty database and its own `.env`. Do not copy a `.env`, `node_modules`, or a database from another machine. Dhan must whitelist that machine's public IPv4 before live orders will be accepted.

Leave `LIVE_TRADING_ENABLED=false` until you have run a paper session, seen a real Dhan fill through the app, flattened once with the kill switch, and restarted with a position still open.

## Standalone

Docker, from the repo root:

```bash
cp .env.example .env
docker compose up -d --build
```

The UI and API are served by nginx at http://localhost. API docs (development only): http://localhost/api/docs.

Native:

| Machine | Command |
|---|---|
| Linux | `./start.sh` (tmux: API, Celery worker, beat, Vite) |
| Windows | `scripts/start-windows.ps1 -Docker` or `-Native` (Celery `--pool=solo`) |
| Mac | `scripts/start-macos.sh docker` or `native` (Celery prefork) |

Start native processes from `backend/` so settings load `backend/.env`. On Mac and Windows the native scripts copy `.env.example` and point Postgres and Redis at localhost.

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
