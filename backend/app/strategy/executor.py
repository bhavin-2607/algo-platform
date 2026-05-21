"""
Strategy Executor — full loop:
tick → candle → signal → risk → order → DB log → status publish
"""
import asyncio
import json
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.broker.factory import get_broker_adapter
from app.broker.base import OrderRequest
from app.core.redis_client import get_redis, strategy_running_key, strategy_state_key
from app.market.candle_builder import build_ohlcv, record_tick
from app.models.strategy import UserStrategyMap, StrategyStatus, Strategy
from app.models.broker import BrokerAccount
from app.models.trade import Trade, TradeDirection, TradeStatus
from app.risk.manager import RiskManager, RiskConfig
from app.strategy.registry import get_strategy_class

logger = logging.getLogger(__name__)


class StrategyExecutor:
    def __init__(self, map_id: str, db: AsyncSession):
        self.map_id = map_id
        self.db = db
        self._stop_flag = False

    async def start(self):
        redis = get_redis()

        # Load UserStrategyMap with related Strategy eagerly
        result = await self.db.execute(
            select(UserStrategyMap)
            .options(selectinload(UserStrategyMap.strategy))
            .where(UserStrategyMap.id == UUID(self.map_id))
        )
        usm: UserStrategyMap = result.scalar_one_or_none()
        if not usm:
            logger.error(f"UserStrategyMap {self.map_id} not found")
            return

        # Load broker account
        ba_result = await self.db.execute(
            select(BrokerAccount).where(BrokerAccount.id == usm.broker_account_id)
        )
        broker_account = ba_result.scalar_one_or_none()
        if not broker_account:
            logger.error(f"BrokerAccount not found for map {self.map_id}")
            return

        # Instantiate strategy engine
        strategy_cls = get_strategy_class(usm.strategy.engine_class)
        strategy = strategy_cls(usm.params)
        if not strategy.validate_params():
            logger.error(f"Invalid strategy params for {self.map_id}")
            return

        # Risk config
        risk = RiskManager(RiskConfig(
            daily_loss_limit       = float(usm.params.get("daily_loss_limit", 5000)),
            max_exposure           = float(usm.params.get("max_exposure", 50000)),
            max_quantity           = int(usm.params.get("max_quantity", 100)),
            max_consecutive_losses = int(usm.params.get("max_losses", 3)),
            paper_trading          = usm.paper_trading,
        ))

        adapter = get_broker_adapter(broker_account)

        symbol    = usm.params.get("symbol", "RELIANCE")
        exchange  = usm.params.get("exchange", "NSE")
        token     = usm.params.get("token", "2885")
        timeframe = int(usm.params.get("timeframe_minutes", 1))

        # Mark running
        await redis.set(strategy_running_key(self.map_id), "1", ex=86400)
        await self._publish_status(redis, "running", risk)
        logger.info(f"▶ Executor started: {self.map_id} | {symbol} | TF={timeframe}m")

        # Subscribe to tick channel
        tick_ch = f"tick:{exchange}:{token}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(tick_ch)

        candle_count = 0

        try:
            async for message in pubsub.listen():
                # Check stop flag via Redis key
                still_running = await redis.get(strategy_running_key(self.map_id))
                if self._stop_flag or not still_running:
                    logger.info(f"⏹ Stop signal received for {self.map_id}")
                    break

                if message["type"] != "message":
                    continue

                try:
                    tick = json.loads(message["data"])
                except Exception:
                    continue

                record_tick(exchange, token, tick)
                candle_count += 1

                # Only evaluate signal every timeframe worth of ticks
                # (approx 1 tick/sec from simulator, so timeframe_minutes * 60 ticks)
                ticks_per_candle = timeframe * 10  # evaluate every 10 ticks for faster testing
                if candle_count % ticks_per_candle != 0:
                    continue

                df = build_ohlcv(exchange, token, timeframe_minutes=timeframe)
                if df.empty or len(df) < 2:
                    logger.debug(f"Not enough candles yet: {len(df)}")
                    continue

                signal = strategy.generate_signal(df)
                if signal is None or signal.direction == "HOLD":
                    continue

                logger.info(f"📡 Signal: {signal.direction} {signal.quantity} {signal.symbol}")

                ltp = float(tick.get("ltp", df["close"].iloc[-1]))
                allowed, reason = risk.check_order(signal.symbol, signal.quantity, ltp, signal.direction)
                if not allowed:
                    logger.warning(f"🚫 Risk blocked: {reason}")
                    await self._publish_status(redis, f"blocked:{reason}", risk)
                    if risk.is_killed:
                        break
                    continue

                # Place order
                order_resp = await adapter.place_order(OrderRequest(
                    symbol     = signal.symbol,
                    exchange   = signal.exchange,
                    direction  = signal.direction,
                    quantity   = signal.quantity,
                    order_type = signal.order_type,
                    price      = signal.price or ltp,
                ))
                strategy.on_order_filled(signal, ltp)

                # Use signal's SL/target if strategy provided them,
                # otherwise calculate from risk params
                sl_pct       = float(usm.params.get("sl_pct", 0.5))
                target_pct   = float(usm.params.get("target_pct", 1.0))

                if signal.sl is not None:
                    sl_price = signal.sl
                elif signal.direction == "BUY":
                    sl_price = round(ltp * (1 - sl_pct / 100), 2)
                else:
                    sl_price = round(ltp * (1 + sl_pct / 100), 2)

                if signal.target is not None:
                    target_price = signal.target
                elif signal.direction == "BUY":
                    target_price = round(ltp * (1 + target_pct / 100), 2)
                else:
                    target_price = round(ltp * (1 - target_pct / 100), 2)

                # Log trade with full pricing details
                trade = Trade(
                    user_id           = usm.user_id,
                    broker_account_id = usm.broker_account_id,
                    strategy_id       = usm.strategy_id,
                    symbol            = signal.symbol,
                    exchange          = signal.exchange,
                    direction         = TradeDirection[signal.direction],
                    quantity          = signal.quantity,
                    entry_price       = ltp,
                    stop_loss         = sl_price,
                    target_price      = target_price,
                    strategy_tag      = usm.strategy.name if usm.strategy else None,
                    status            = TradeStatus.OPEN,
                    broker_order_id   = order_resp.broker_order_id,
                    is_paper          = usm.paper_trading,
                )
                self.db.add(trade)
                await self.db.commit()
                logger.info(f"✅ Trade logged: {signal.direction} {signal.quantity} {signal.symbol} @ ₹{ltp}")

                await self._publish_status(redis, "running", risk)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Executor error: {e}", exc_info=True)
        finally:
            await pubsub.unsubscribe(tick_ch)
            await redis.delete(strategy_running_key(self.map_id))
            await self._publish_status(redis, "stopped", risk)
            logger.info(f"⏹ Executor stopped: {self.map_id}")

    def stop(self):
        self._stop_flag = True

    async def _publish_status(self, redis, status: str, risk: RiskManager):
        payload = json.dumps({
            "map_id":             self.map_id,
            "status":             status,
            "daily_pnl":          round(risk.daily_pnl, 2),
            "consecutive_losses": risk.consecutive_losses,
            "killed":             risk.is_killed,
        })
        await redis.set(strategy_state_key(self.map_id), payload, ex=86400)
        await redis.publish(f"strategy_status:{self.map_id}", payload)
