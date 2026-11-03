# Algo Platform Roadmap — Real Trading Ready

Goal: make custom formulas and custom strategies safe enough for live capital, without rewriting the product.

### Implementation status

- [x] **Phase 0** — paper/live separation, synthetic data blocked while live is on, live-kill flattens
- [x] **Phase 1** — closed bars, fill confirmation, persisted risk, idempotent orders, flatten-on-stop, pending → open → closed
- [x] **Phase 2.1, 2.2, 2.4, 2.5** — formula AST allow-list (`ma`, `ema`, `rsi`, `vwap`, `atr`, `bb_upper`, `bb_lower`, `supertrend`, `abs`, `min`, `max`, `round`), save-time validation, size limits, unit tests
- [x] **Phase 4** — Dhan historical candles, `generate_signal` backtest with fees and slippage, a losing run blocks the next live start of that version and symbol
- [x] **Phase 2.3 / 6.1** — formula preview on Dhan candles (`POST /api/formula/preview`) and the save error shown on the formula form
- [x] **Phase 5.1, 5.3 (override), 5.4, 5.6** — Celery beat in Compose, per-account Dhan token overrides `.env`, feed watchdog pauses new entries only while a session is running, `audit_events` for kill, formula start, and the daily risk reset
- [x] **Phase 5.2 (revised)** — boot still uses `create_all`. Alembic is only for a later change that `create_all` cannot express. Do not run Alembic inside Uvicorn startup (it reconfigured logging and hid "startup complete").
- [ ] **Phase 5.5** — Linux server edition only. Prometheus and Grafana live in `docker-compose.server.yml`. One alert rule for feed-stale, kill switch, and order rejects is still open. Standalone Linux, Windows, and Mac do not run that stack.
- [x] **Phase 3** — plugin load from `strategy/`, version on the catalogue and the assignment, admin enable-live before a live start, shared stop/target/trail helper
- [ ] **Go-live proof runs** — not done. Code cannot check these off.

---

## Phase 0 — Freeze unsafe live paths — done

**Outcome:** Live mode cannot silently use fake or dev behavior.

| # | Item | Status |
|---|------|--------|
| 0.1 | Hard-separate paper and live | Done. `LIVE_TRADING_ENABLED` plus start gates |
| 0.2 | No synthetic market or backtest data while live is on | Done |
| 0.3 | Explicit live flag and broker credentials before real orders | Done |
| 0.4 | Kill switch stops workers and flattens | Done |

---

## Phase 1 — Execution correctness — done in code

**Outcome:** Strategies fire on real bars and only trade on real fills.

| # | Item | Status |
|---|------|--------|
| 1.1 | Time-bucket candle closes | Done |
| 1.2 | Fill confirmation before a trade is OPEN | Done in code. Still needs a live Dhan proof run |
| 1.3 | Risk state in Redis | Done |
| 1.4 | `client_order_id` idempotency | Done |
| 1.5 | Flatten on stop; restart recovery from DB and broker positions | Done in code. Mid-position restart still needs a proof run |
| 1.6 | pending → open → closed / cancelled | Done |

---

## Phase 2 — Safe custom formulas — preview still open

**Outcome:** Users can write formulas without crashing or escaping the engine.

| # | Item | Status |
|---|------|--------|
| 2.1 | AST allow-list instead of `eval` | Done |
| 2.2 | Documented function set and validation on save | Done |
| 2.3 | Dry-run on real historical bars | Done. Preview uses Dhan candles. An invalid formula is returned before any broker call |
| 2.4 | Unit tests for malicious and broken input | Done (`tests/test_production_gates.py`) |
| 2.5 | Max length and max AST nodes | Done |

---

## Phase 3 — Custom strategy platform — done

**Outcome:** Adding a strategy is a product workflow, not a deploy hack.

| # | Item | Status |
|---|------|--------|
| 3.1 | Load an engine from `strategy/*.py` | Done. `strategy/hold_flat.py` registers as `hold_flat`. A bad file is skipped and reported by `POST /api/admin/strategy-plugins/reload` |
| 3.2 | Contract: `engine_id`, `version`, `warmup_bars`, `max_positions`, `validate_params` | Done on `BaseStrategy` |
| 3.3 | Catalogue version copied onto the user map as `engine_version` | Done. A live start pinned to another version is rejected |
| 3.4 | Admin enable before live | Done. New catalogue rows start with `live_enabled=false`. `POST /api/admin/strategies/{id}/enable-live` turns it on. Existing rows stay enabled |
| 3.5 | Shared stop, target, and trail | Done in `app/strategy/exits.py`, used by the executor, formula order manager, and terminal |

**Exit criteria:** Drop a class with `engine_id` into `strategy/`, reload, paper-assign it, and enable that version before any live assignment.

---

## Phase 4 — Trustworthy backtesting — done

**Outcome:** The backtest uses the same signal path as live, on Dhan candles.

| # | Item | Status |
|---|------|--------|
| 4.1 | Historical OHLCV from Dhan. No random series | Done. `POST /api/backtest/run` returns 502 when Dhan has no candles |
| 4.2 | Runner calls `generate_signal`. A `formula` on the request uses `FormulaEvaluator` inside that same call | Done |
| 4.3 | Slippage against the fill and a fee on entry and exit | Done. Defaults are 0.05% and ₹20 per order |
| 4.4 | Equity curve, drawdown, win rate, Sharpe, and the trade list | Done |
| 4.5 | Latest losing run blocks a live start of that engine version and symbol | Done. No stored run does not block. `GET /api/backtest/latest` shows the stored result |

A run passes only when it closes at least one trade and net P&L after costs is zero or better.

---

## Phase 5 — Data, broker, and ops — revised

**Outcome:** The stack stays up through market hours.

| # | Item | Status |
|---|------|--------|
| 5.1 | Celery beat in Compose (07:45 token renew, 08:00 instrument refresh, 09:15 risk reset, 60s feed watchdog) | Done |
| 5.2 | Schema changes | Boot uses `create_all`. Alembic revision `0001_audit_events` exists and is run by hand, not from Uvicorn |
| 5.3 | Per-account Dhan token | An encrypted token on the broker account overrides `.env`. Accounts without one still use the shared token |
| 5.4 | Feed watchdog | Pauses new live entries only while a strategy, formula, or terminal session is running and quotes have stopped. Exits still flatten |
| 5.5 | Server-edition alert rule | Open, and not part of standalone. Prometheus and Grafana start only with `docker compose -f docker-compose.yml -f docker-compose.server.yml up`. The rule for feed-stale, kill switch, and order rejects is still to be added there |
| 5.6 | Audit log | Done for kill, kill-clear, formula start, and the daily risk reset |

---

## Phase 6 — What is still in scope — narrowed

**Outcome:** Use the pieces from Phases 3 and 4 without extra product surface.

| # | Item | Status |
|---|------|--------|
| 6.1 | Formula preview on Dhan history, with the save error shown on the form | Done |
| 6.2 | Paper comparison of the registered engines from their backtest reports | Open |
| 6.3 | Short notes: add a strategy, write a formula, go-live checks | Open |

Out of this pass: a paper leaderboard, extra options helpers, and a sweep of orphan pages.

---

## Editions

- Standalone (Linux, Windows, Mac): `docker compose up`, `./start.sh`, `scripts/start-windows.ps1`, or `scripts/start-macos.sh`. No Prometheus or Grafana.
- Linux server: `docker compose -f docker-compose.yml -f docker-compose.server.yml up -d --build`. Phase 5.5 belongs here.

## Order of remaining work

```
1. Phase 6.2 and 6.3   paper comparison and the three short notes
2. Go-live proof runs below, by hand
3. Phase 5.5           server edition only: one alert rule
```

---

## Go-live checklist

Code items are checked. Proof runs stay open until they are actually run.

- [ ] Paper session on bar closes for each engine and formula you will use
- [ ] Fill confirmation observed against Dhan
- [ ] Kill switch used once and confirmed to flatten
- [x] Synthetic prices refused while live trading is on
- [x] Idempotent order ids
- [ ] Restart during an open position, then confirm the position and the risk counters
- [x] Formula sandbox tests passing
- [x] Beat jobs scheduled (token renew and 09:15 risk reset)
- [x] Alerts for a stale feed and the kill switch (log, Redis, Telegram when configured)

Leave `LIVE_TRADING_ENABLED=false` until the unchecked proof runs are done, the Windows or Pi public IPv4 is whitelisted at Dhan, and that machine has its own access token.
