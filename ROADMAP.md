# Algo Platform Roadmap — Real Trading Ready

Goal: make custom formulas + custom strategies safe enough for live capital, without rewriting the product.

### Implementation status

- [x] **Phase 0** — paper/live hard separation (`LIVE_TRADING_ENABLED`, live-kill Redis API, factory/strategy/terminal gates)
- [x] **Phase 1.1** — closed-bar candle evaluation in `StrategyExecutor`
- [x] **Phase 1.2** — fill confirmation via `wait_for_fill` before `on_order_filled` / Trade OPEN
- [x] **Phase 1.3** — Redis-persisted `RiskManager` state (`risk:state:{map_id}`)
- [ ] Phase 1.4+ / Terminal & Formula engines adopt shared helpers
- [ ] Phases 2–6 — not started

---

## Phase 0 — Freeze unsafe live paths (1–2 days)

**Outcome:** Live mode cannot silently use fake/dev behavior.

| # | Item | Why |
|---|------|-----|
| 0.1 | Hard-separate `paper` / `live` modes | Prevents accidental live orders on sim data |
| 0.2 | Disable random/synthetic market & backtest data in live | Fake prices in live = wrong trades |
| 0.3 | Require explicit “live enabled” flag + broker health check | Last safety gate before real money |
| 0.4 | Kill-switch API wired to stop all workers + flatten intent | Fast human override |

**Exit criteria:** Live start fails if feed/broker/token unhealthy; paper still works freely.

---

## Phase 1 — Execution correctness (1–2 weeks) — **P0**

**Outcome:** Strategies fire on real bars and only trade on real fills.

| # | Item | Why |
|---|------|-----|
| 1.1 | Replace tick-count candles with time-bucket / session candle closes | Current `ticks_per_candle` is test-only |
| 1.2 | Confirm order fill/reject via Dhan status poll or WS before `on_order_filled` | Stops phantom positions |
| 1.3 | Persist risk state (daily PnL, consecutive losses, kill) in Redis/DB | Survives worker restarts |
| 1.4 | Order idempotency (`client_order_id` + debounce) | Prevents double orders on retries/ticks |
| 1.5 | Flatten-on-stop / restart recovery from DB + broker positions | Crash-safe position truth |
| 1.6 | Structured trade lifecycle: signal → pending → filled → open → closed | Accurate PnL & audits |

**Exit criteria:** Paper run of MA / ORFib / one formula matches expected bar-close behavior; restart does not lose risk/position state.

---

## Phase 2 — Safe custom formulas (1–2 weeks) — **P0/P1**

**Outcome:** Users can write formulas without crashing or escaping the engine.

| # | Item | Why |
|---|------|-----|
| 2.1 | Replace bare `eval` with AST whitelist / expression DSL | Security + predictable errors |
| 2.2 | Documented function set (`ma`, `rsi`, `vwap`, `fib`, etc.) + validation UX | Users know what’s allowed |
| 2.3 | Formula dry-run / preview on historical bars | Catch logic bugs before live |
| 2.4 | Unit tests for parser, edge cases, malicious input | Formulas are user-controlled code |
| 2.5 | Per-row / per-strategy rate limits & max complexity | Protect worker CPU |

**Exit criteria:** Malicious/broken formulas rejected cleanly; valid formulas preview correctly on history.

---

## Phase 3 — Custom strategy platform (1–2 weeks) — **P1**

**Outcome:** Adding a strategy is a product workflow, not a deploy hack.

| # | Item | Why |
|---|------|-----|
| 3.1 | Real plugin path: `strategy/` mount → validate → register → version | Matches README intent |
| 3.2 | Strategy contract: params schema, warm-up bars, max positions, exits | Consistent engines |
| 3.3 | Versioning + assign specific version to a user map | Safe rollouts / rollbacks |
| 3.4 | Admin “validate & enable” before live assignment | Gate bad engines |
| 3.5 | Shared exit/SL/trail helper used by engines + terminal + formula | One risk language everywhere |

**Exit criteria:** Drop in a new engine file, register, paper-test, assign — without rebuilding the whole stack.

---

## Phase 4 — Trustworthy backtesting (1 week) — **P1**

**Outcome:** Same code path for backtest and live signals.

| # | Item | Why |
|---|------|-----|
| 4.1 | Historical OHLCV from Dhan / stored DB (no random series) | Real validation |
| 4.2 | Backtest runner reuses `generate_signal` / formula evaluator | No “backtest-only” logic |
| 4.3 | Costs: slippage, fees, partial fills model | Avoid over-optimism |
| 4.4 | Report: equity curve, drawdown, win rate, trades list | Decide go-live |

**Exit criteria:** Strategy that fails in backtest is blocked from live by policy (or strong warning).

---

## Phase 5 — Data, broker & ops hardening (1–2 weeks) — **P1/P2**

**Outcome:** Production stack stays up through market hours.

| # | Item | Why |
|---|------|-----|
| 5.1 | Celery beat service in Docker compose | Token renew, daily risk reset, instrument refresh |
| 5.2 | Alembic migrations (stop relying on `create_all`) | Safe schema evolution |
| 5.3 | Per-user / rotatable Dhan tokens (not only shared `.env`) | Multi-user + security |
| 5.4 | Feed watchdog (reconnect, stale-tick alert, pause trading) | Bad data → no trade |
| 5.5 | Prometheus metrics + Grafana dashboards + alerts | See failures before P&L does |
| 5.6 | Audit log: who started what, signals, orders, risk blocks | Post-trade forensics |

**Exit criteria:** Full compose stack runs worker + beat; alerts on feed down / kill switch / order rejects.

---

## Phase 6 — Product polish (ongoing) — **P2**

**Outcome:** Faster iteration for you as the trader/builder.

| # | Item |
|---|------|
| 6.1 | Wire orphan pages / notifications or remove dead code |
| 6.2 | Terminal + formula UX: clearer errors, param helpers |
| 6.3 | Paper leaderboard / strategy comparison |
| 6.4 | Options strategy helpers (if options stay in scope) |
| 6.5 | Docs: “Add a strategy”, “Write a formula”, “Go-live checklist” |

---

## Suggested sequence (calendar view)

```
Week 1–2   Phase 0 + Phase 1 (execution + risk)     ← do first
Week 3–4   Phase 2 (safe formulas)
Week 5–6   Phase 3 (strategy plugins) + Phase 4 start (history)
Week 7     Phase 4 finish (backtest quality)
Week 8–9   Phase 5 (ops / migrations / monitoring)
Ongoing    Phase 6 (UX / docs)
```

Solo builder: treat weeks as flexible; **don’t skip Phase 0–1** before live capital.

---

## Go-live checklist (gate)

Only enable real money when all are true:

- [ ] Paper-only proven on bar closes for each engine/formula you’ll use
- [ ] Fill confirmation working against Dhan
- [ ] Risk persisted + kill switch tested
- [ ] No synthetic data reachable in live mode
- [ ] Idempotent orders
- [ ] Restart recovery tested mid-position
- [ ] Formula sandbox tests passing
- [ ] Beat jobs running (token + daily risk reset)
- [ ] Alerts for feed/order/risk failures

---

## First implementation slice (when starting work)

1. Phase 0 mode separation
2. Phase 1.1 candle closes
3. Phase 1.2 fill confirmation
4. Phase 1.3 persisted risk

That unlocks trustworthy paper trading, then formulas/strategies on a solid base.
