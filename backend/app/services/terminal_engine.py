"""
Terminal Engine
===============
Runs all active TerminalRows simultaneously — like the Excel terminal running
multiple symbol rows at once.

For each active row:
  1. Subscribes to tick feed for that symbol
  2. On each tick → updates live data (LTP, OHLC, OI) in Redis
  3. Evaluates entry/exit formula
  4. If signal fires → places order (auto or pending approval)
  5. Monitors open position for T/SL/Trail

One instance runs all rows for one user — equivalent to one Excel terminal session.
"""
import asyncio
import json
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.broker.factory import get_broker_adapter
from app.broker.base import OrderRequest
from app.core.redis_client import get_redis
from app.market.candle_builder import build_ohlcv, record_tick
from app.models.terminal import TerminalRow, TerminalRowStatus
from app.models.broker import BrokerAccount
from app.strategy.formula_engine import FormulaEvaluator

logger = logging.getLogger(__name__)

TERMINAL_TICK_KEY  = "terminal:tick:{row_id}"
TERMINAL_STATE_KEY = "terminal:state:{row_id}"
TERMINAL_RUN_KEY   = "terminal:running:{user_id}"


class TerminalEngine:
    """
    Runs all active rows for one user simultaneously.
    Each row gets its own asyncio task watching its symbol's tick channel.
    """

    def __init__(self, user_id: str, db: AsyncSession):
        self.user_id  = user_id
        self.db       = db
        self._stop    = False
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        redis   = get_redis()
        run_key = TERMINAL_RUN_KEY.format(user_id=self.user_id)
        await redis.set(run_key, "1", ex=86400)

        # Load all active rows for this user
        result = await self.db.execute(
            select(TerminalRow).where(
                TerminalRow.owner_id  == UUID(self.user_id),
                TerminalRow.is_active == True,
            ).order_by(TerminalRow.row_order)
        )
        rows = result.scalars().all()

        if not rows:
            logger.info(f"Terminal: no active rows for user {self.user_id}")
            return

        logger.info(f"▶ Terminal started: {len(rows)} rows for user {self.user_id}")

        # Run all rows concurrently
        self._tasks = [
            asyncio.create_task(self._run_row(row, redis))
            for row in rows
        ]

        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        finally:
            await redis.delete(run_key)
            logger.info(f"⏹ Terminal stopped for user {self.user_id}")

    async def _run_row(self, row: TerminalRow, redis):
        """Watch one symbol row — feeds data, evaluates formula, manages position."""
        tick_ch = f"tick:{row.exchange}:{row.token or row.symbol}"
        pubsub  = redis.pubsub()
        await pubsub.subscribe(tick_ch)

        # Compile formulas
        entry_ev = FormulaEvaluator(row.entry_formula) if row.entry_formula else None
        exit_ev  = FormulaEvaluator(row.exit_formula)  if row.exit_formula  else None

        # Load broker adapter
        ba = await self.db.get(BrokerAccount, row.broker_account_id) if row.broker_account_id else None
        adapter = get_broker_adapter(ba) if ba else None

        in_position = row.status == TerminalRowStatus.active
        tick_count  = 0

        logger.info(f"  Row [{row.symbol}]: watching tick channel {tick_ch}")

        try:
            async for message in pubsub.listen():
                # Check global stop or row-level stop
                still_running = await redis.get(TERMINAL_RUN_KEY.format(user_id=self.user_id))
                row_active = await redis.get(f"terminal:row:active:{row.id}")
                if self._stop or not still_running:
                    break

                if message["type"] != "message":
                    continue

                try:
                    tick = json.loads(message["data"])
                except Exception:
                    continue

                ltp = float(tick.get("ltp", 0))
                if ltp == 0:
                    continue

                record_tick(row.exchange, row.token or row.symbol, tick)
                tick_count += 1

                # ── Build live state for this row ─────────────────────────────
                live = {
                    "row_id":   str(row.id),
                    "symbol":   row.symbol,
                    "ltp":      ltp,
                    "open":     float(tick.get("o", ltp)),
                    "high":     float(tick.get("h", ltp)),
                    "low":      float(tick.get("l", ltp)),
                    "close":    float(tick.get("c", ltp)),
                    "volume":   int(tick.get("v", 0)),
                    "oi":       int(tick.get("oi", 0)),
                    "bp1":      float(tick.get("bp1", 0)),
                    "sp1":      float(tick.get("sp1", 0)),
                    "status":   row.status,
                    "signal":   row.last_signal or "—",
                    "entry_price":    row.entry_price,
                    "current_sl":     row.current_sl,
                    "current_target": row.current_target,
                    "pnl":            _calc_pnl(row, ltp),
                    "peak_price":     row.peak_price,
                }

                # Publish live data to Redis for WebSocket relay
                await redis.set(
                    TERMINAL_TICK_KEY.format(row_id=row.id),
                    json.dumps(live), ex=300
                )
                await redis.publish(
                    f"terminal:user:{self.user_id}",
                    json.dumps(live)
                )

                # ── T/SL/Trail check if in position ──────────────────────────
                if in_position and row.entry_price:
                    exited, reason = _check_exit_levels(row, ltp)
                    if exited:
                        await self._close_position(row, ltp, reason, redis, adapter)
                        in_position = False
                        continue

                    # Update trailing SL
                    if row.trailing_sl and row.trail_pct:
                        _update_trail(row, ltp)

                # ── Evaluate signals every 10 ticks ──────────────────────────
                if tick_count % 10 != 0:
                    continue

                df = build_ohlcv(
                    row.exchange, row.token or row.symbol,
                    timeframe_minutes=5
                )
                if df.empty or len(df) < 5:
                    continue

                # Exit signal
                if in_position and exit_ev:
                    if exit_ev.evaluate(df, ltp):
                        await self._close_position(row, ltp, "EXIT_SIGNAL", redis, adapter)
                        in_position = False
                        row.last_signal = "EXIT"
                        continue

                # Entry signal
                if not in_position and entry_ev:
                    signal = entry_ev.evaluate(df, ltp)
                    if signal is True:
                        direction = "BUY"   # default; short selling = separate formula
                        row.last_signal = "BUY"

                        if row.auto_execute and adapter:
                            await self._open_position(row, ltp, direction, redis, adapter)
                            in_position = True
                        else:
                            # Manual approval mode — publish pending signal
                            row.status = TerminalRowStatus.entry_pending
                            await redis.publish(
                                f"terminal:user:{self.user_id}",
                                json.dumps({**live, "status": "entry_pending", "signal": "BUY_PENDING"})
                            )
                    else:
                        row.last_signal = "—"

                # Persist row state to DB periodically (every 100 ticks)
                if tick_count % 100 == 0:
                    row.last_ltp    = ltp
                    row.updated_at  = datetime.utcnow()
                    await self.db.commit()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Row [{row.symbol}] error: {e}", exc_info=True)
        finally:
            await pubsub.unsubscribe(tick_ch)

    async def _open_position(self, row: TerminalRow, ltp: float, direction: str, redis, adapter):
        try:
            resp = await adapter.place_order(OrderRequest(
                symbol=row.symbol, exchange=row.exchange,
                direction=direction, quantity=row.quantity,
                order_type=row.order_type, price=ltp,
            ))
            row.status         = TerminalRowStatus.active
            row.entry_price    = ltp
            row.entry_order_id = resp.broker_order_id
            row.peak_price     = ltp
            row.current_sl     = round(ltp * (1 - (row.sl_pct or 1) / 100), 2)
            row.current_target = round(ltp * (1 + (row.target_pct or 2) / 100), 2)
            await self.db.commit()
            logger.info(f"  [{row.symbol}] Entry: {direction} @ ₹{ltp} | T={row.current_target} SL={row.current_sl}")
        except Exception as e:
            logger.error(f"  [{row.symbol}] Entry order failed: {e}")

    async def _close_position(self, row: TerminalRow, ltp: float, reason: str, redis, adapter):
        try:
            exit_dir = "SELL" if row.entry_price else "BUY"
            if adapter:
                await adapter.place_order(OrderRequest(
                    symbol=row.symbol, exchange=row.exchange,
                    direction=exit_dir, quantity=row.quantity,
                    order_type="MARKET", price=ltp,
                ))
            pnl = _calc_pnl(row, ltp)
            row.status       = TerminalRowStatus.watching
            row.pnl          = pnl
            row.entry_price  = None
            row.entry_order_id = None
            row.current_sl   = None
            row.current_target = None
            row.peak_price   = None
            row.last_signal  = "EXIT"
            await self.db.commit()
            logger.info(f"  [{row.symbol}] Exit: {reason} @ ₹{ltp} | PnL=₹{pnl}")
        except Exception as e:
            logger.error(f"  [{row.symbol}] Exit order failed: {e}")

    def stop(self):
        self._stop = True
        for t in self._tasks:
            t.cancel()


def _calc_pnl(row: TerminalRow, ltp: float) -> float | None:
    if not row.entry_price:
        return row.pnl  # last closed PnL
    return round((ltp - row.entry_price) * row.quantity, 2)


def _check_exit_levels(row: TerminalRow, ltp: float) -> tuple[bool, str]:
    if row.current_target and ltp >= row.current_target:
        return True, "TARGET_HIT"
    if row.current_sl and ltp <= row.current_sl:
        return True, "SL_HIT"
    return False, ""


def _update_trail(row: TerminalRow, ltp: float):
    if not row.trail_pct:
        return
    if ltp > (row.peak_price or row.entry_price or ltp):
        row.peak_price = ltp
        new_sl = round(ltp * (1 - row.trail_pct / 100), 2)
        if row.current_sl is None or new_sl > row.current_sl:
            row.current_sl = new_sl
