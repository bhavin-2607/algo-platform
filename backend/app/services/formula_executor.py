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
from app.broker.order_ops import client_order_id_for, place_once
from app.core.redis_client import get_redis
from app.market.candle_builder import build_ohlcv_closed, latest_closed_bar_ts, record_tick
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
        open_rows = await self.db.execute(
            select(ManagedPosition).where(
                ManagedPosition.strategy_id == strat.id,
                ManagedPosition.status == PositionStatus.open,
            ).order_by(ManagedPosition.created_at.desc())
        )
        position = open_rows.scalars().first()
        if position:
            logger.info(f"Restored open {position.direction} {position.symbol} @ ₹{position.entry_price}")

        ba = await self.db.get(BrokerAccount, strat.broker_account_id) if strat.broker_account_id else None
        try:
            adapter = get_broker_adapter(ba) if ba else None
        except Exception as e:
            logger.error(f"Broker adapter unavailable for formula {self.strategy_id}: {e}")
            return

        # Mark running
        await redis.set(run_key, "1", ex=86400)
        logger.info(f"▶ Formula executor started: {strat.name} | {strat.symbol}")

        tick_ch = f"tick:{strat.exchange}:{strat.token}"
        pubsub  = redis.pubsub()
        await pubsub.subscribe(tick_ch)

        last_bar_ts = None
        last_ltp = None
        flatten = False

        try:
            async for message in pubsub.listen():
                # Check stop signal
                if self._stop or not await redis.get(run_key):
                    flatten = True
                    break
                if message["type"] != "message":
                    continue

                try:
                    tick = json.loads(message["data"])
                except Exception:
                    continue

                ltp = float(tick.get("ltp", 0))
                last_ltp = ltp or last_ltp
                record_tick(strat.exchange, strat.token, tick)

                # ── Update open position (T/SL/Trail) on every tick ───────────
                if position and position.status == PositionStatus.open:
                    position = await order_mgr.update_position(position, ltp)
                    if position.status != PositionStatus.open:
                        position = None  # closed by T/SL

                # ── Evaluate only when a new closed bar appears ───────────────
                df = build_ohlcv_closed(
                    strat.exchange, strat.token,
                    timeframe_minutes=strat.timeframe_minutes or 5,
                )
                bar_ts = latest_closed_bar_ts(df)
                if bar_ts is None or df.empty or len(df) < 5:
                    continue
                if last_bar_ts is not None and bar_ts == last_bar_ts:
                    continue
                last_bar_ts = bar_ts

                # ── Exit existing position? ───────────────────────────────────
                if position and position.status == PositionStatus.open:
                    ev = exit_long_ev if position.direction == "BUY" else exit_short_ev
                    if ev and ev.evaluate(df, ltp):
                        position = await order_mgr.manual_exit(position, ltp)
                        if position.status != PositionStatus.open:
                            position = None
                    continue  # don't enter a new position on the same bar

                if not adapter:
                    continue

                if entry_long_ev and entry_long_ev.evaluate(df, ltp):
                    position = await self._enter(
                        redis, adapter, order_mgr, strat, "BUY", ltp, bar_ts
                    )
                elif entry_short_ev and entry_short_ev.evaluate(df, ltp):
                    position = await self._enter(
                        redis, adapter, order_mgr, strat, "SELL", ltp, bar_ts
                    )

        except asyncio.CancelledError:
            flatten = True
        except Exception as e:
            logger.error(f"Formula executor error: {e}", exc_info=True)
        finally:
            if flatten and position and position.status == PositionStatus.open:
                try:
                    await order_mgr.manual_exit(position, last_ltp or position.entry_price)
                except Exception as e:
                    logger.error(f"Formula flatten failed: {e}")
            await pubsub.unsubscribe(tick_ch)
            await redis.delete(run_key)
            logger.info(f"⏹ Formula executor stopped: {strat.name}")

    async def _enter(self, redis, adapter, order_mgr, strat, direction: str, ltp: float, bar_ts):
        client_order_id = client_order_id_for(str(strat.id), bar_ts, strat.symbol, direction)
        result = await place_once(
            redis,
            adapter,
            OrderRequest(
                symbol=strat.symbol, exchange=strat.exchange,
                direction=direction, quantity=strat.quantity,
                order_type=strat.order_type, price=ltp,
            ),
            client_order_id,
        )
        if not result["ok"]:
            logger.error(f"Formula entry not filled: {strat.symbol} {direction} {result['status']}")
            return None
        fill_price = float(result["fill_price"] or ltp)
        position = await order_mgr.open_position(
            user_id=strat.user_id,
            broker_account_id=strat.broker_account_id,
            symbol=strat.symbol, exchange=strat.exchange,
            direction=direction, quantity=strat.quantity,
            entry_price=fill_price, entry_order_id=result["broker_order_id"],
            target_pct=strat.target_pct, sl_pct=strat.sl_pct,
            trailing_sl=strat.trailing_sl, trail_pct=strat.trail_pct,
            strategy_id=strat.id, is_paper=strat.paper_trading,
        )
        logger.info(f"📡 {direction} entry: {strat.symbol} @ ₹{fill_price}")
        return position

    def stop(self):
        self._stop = True
