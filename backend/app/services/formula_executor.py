"""
Formula Strategy Executor
=========================
Runs a FormulaStrategy end-to-end:
  1. Subscribes to tick feed for the instrument
  2. On each tick: builds candle DataFrame
  3. Evaluates entry/exit conditions using FormulaEvaluator
  4. Places orders and tracks them via OrderManager
  5. Publishes live status to Redis
"""
import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.broker.factory import get_broker_adapter
from app.broker.base import OrderRequest
from app.core.redis_client import get_redis, strategy_running_key
from app.market.candle_builder import build_ohlcv, record_tick
from app.models.formula import FormulaStrategy, ManagedPosition, PositionStatus
from app.models.broker import BrokerAccount
from app.services.order_manager import OrderManager
from app.strategy.formula_engine import FormulaEvaluator

logger = logging.getLogger(__name__)


class FormulaStrategyExecutor:
    def __init__(self, strategy_id: str, db: AsyncSession):
        self.strategy_id = strategy_id
        self.db          = db
        self._stop       = False

    async def start(self):
        redis = get_redis()
        run_key = f"formula:running:{self.strategy_id}"

        # Load strategy
        result = await self.db.execute(
            select(FormulaStrategy).where(FormulaStrategy.id == UUID(self.strategy_id))
        )
        strat: FormulaStrategy = result.scalar_one_or_none()
        if not strat:
            logger.error(f"FormulaStrategy {self.strategy_id} not found")
            return

        # Compile conditions
        entry_long_ev  = FormulaEvaluator(strat.entry_long)  if strat.entry_long  else None
        entry_short_ev = FormulaEvaluator(strat.entry_short) if strat.entry_short else None
        exit_long_ev   = FormulaEvaluator(strat.exit_long)   if strat.exit_long   else None
        exit_short_ev  = FormulaEvaluator(strat.exit_short)  if strat.exit_short  else None

        order_mgr = OrderManager(self.db)
        position: ManagedPosition | None = None

        # Mark running
        await redis.set(run_key, "1", ex=86400)
        logger.info(f"▶ Formula executor started: {strat.name} | {strat.symbol}")

        tick_ch = f"tick:{strat.exchange}:{strat.token}"
        pubsub  = redis.pubsub()
        await pubsub.subscribe(tick_ch)

        tick_count = 0

        try:
            async for message in pubsub.listen():
                # Check stop signal
                if self._stop or not await redis.get(run_key):
                    break
                if message["type"] != "message":
                    continue

                try:
                    tick = json.loads(message["data"])
                except Exception:
                    continue

                ltp = float(tick.get("ltp", 0))
                record_tick(strat.exchange, strat.token, tick)
                tick_count += 1

                # ── Update open position (T/SL/Trail) ────────────────────────
                if position and position.status == PositionStatus.open:
                    position = await order_mgr.update_position(position, ltp)
                    if position.status != PositionStatus.open:
                        position = None  # closed by T/SL

                # ── Evaluate signals every N ticks ────────────────────────────
                eval_every = strat.timeframe_minutes * 10
                if tick_count % eval_every != 0:
                    continue

                df = build_ohlcv(strat.exchange, strat.token,
                                 timeframe_minutes=strat.timeframe_minutes)
                if df.empty or len(df) < 5:
                    continue

                # ── Exit existing position? ───────────────────────────────────
                if position and position.status == PositionStatus.open:
                    ev = exit_long_ev if position.direction == "BUY" else exit_short_ev
                    if ev and ev.evaluate(df, ltp):
                        position = await order_mgr.manual_exit(position, ltp)
                        position = None
                    continue  # don't enter new position same tick

                # ── Entry conditions ──────────────────────────────────────────
                ba = await self.db.get(BrokerAccount, strat.broker_account_id)
                if not ba:
                    continue
                adapter = get_broker_adapter(ba)

                if entry_long_ev and entry_long_ev.evaluate(df, ltp):
                    resp = await adapter.place_order(OrderRequest(
                        symbol=strat.symbol, exchange=strat.exchange,
                        direction="BUY", quantity=strat.quantity,
                        order_type=strat.order_type, price=ltp,
                    ))
                    position = await order_mgr.open_position(
                        user_id=strat.user_id,
                        broker_account_id=strat.broker_account_id,
                        symbol=strat.symbol, exchange=strat.exchange,
                        direction="BUY", quantity=strat.quantity,
                        entry_price=ltp, entry_order_id=resp.broker_order_id,
                        target_pct=strat.target_pct, sl_pct=strat.sl_pct,
                        trailing_sl=strat.trailing_sl, trail_pct=strat.trail_pct,
                        strategy_id=strat.id, is_paper=strat.paper_trading,
                    )
                    logger.info(f"📡 BUY entry: {strat.symbol} @ ₹{ltp}")

                elif entry_short_ev and entry_short_ev.evaluate(df, ltp):
                    resp = await adapter.place_order(OrderRequest(
                        symbol=strat.symbol, exchange=strat.exchange,
                        direction="SELL", quantity=strat.quantity,
                        order_type=strat.order_type, price=ltp,
                    ))
                    position = await order_mgr.open_position(
                        user_id=strat.user_id,
                        broker_account_id=strat.broker_account_id,
                        symbol=strat.symbol, exchange=strat.exchange,
                        direction="SELL", quantity=strat.quantity,
                        entry_price=ltp, entry_order_id=resp.broker_order_id,
                        target_pct=strat.target_pct, sl_pct=strat.sl_pct,
                        trailing_sl=strat.trailing_sl, trail_pct=strat.trail_pct,
                        strategy_id=strat.id, is_paper=strat.paper_trading,
                    )
                    logger.info(f"📡 SELL entry: {strat.symbol} @ ₹{ltp}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Formula executor error: {e}", exc_info=True)
        finally:
            await pubsub.unsubscribe(tick_ch)
            await redis.delete(run_key)
            logger.info(f"⏹ Formula executor stopped: {strat.name}")

    def stop(self):
        self._stop = True
