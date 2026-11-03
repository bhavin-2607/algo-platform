"""
Strategy Executor — full loop:
tick → closed candle → signal → PENDING trade → fill → OPEN → flatten → CLOSED
"""
import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.broker.factory import get_broker_adapter
from app.broker.base import OrderRequest
from app.broker.order_ops import (
    claim_order_intent,
    client_order_id_for,
    commit_order_intent,
    release_order_intent,
    wait_for_fill,
)
from app.core.redis_client import get_redis, strategy_running_key, strategy_state_key
from app.market.candle_builder import build_ohlcv_closed, latest_closed_bar_ts, record_tick
from app.models.strategy import UserStrategyMap
from app.models.broker import BrokerAccount
from app.models.trade import Trade, TradeDirection, TradeStatus
from app.risk.manager import RiskManager, RiskConfig
from app.strategy.recovery import (
    apply_order_result,
    flatten_open_trades,
    load_open_trades,
    reconcile_open_trades,
)
from app.strategy.exits import protective_prices
from app.strategy.registry import get_strategy_class

logger = logging.getLogger(__name__)


def _protective_prices(signal, price: float, params: dict) -> tuple[float, float]:
    """Stop and target from the shared exit helper."""
    return protective_prices(
        signal.direction,
        price,
        sl_pct=float((params or {}).get("sl_pct", 0.5)),
        target_pct=float((params or {}).get("target_pct", 1.0)),
        sl=signal.sl,
        target=signal.target,
    )


class StrategyExecutor:
    def __init__(self, map_id: str, db: AsyncSession):
        self.map_id = map_id
        self.db = db
        self._stop_flag = False

    async def start(self):
        redis = get_redis()
        risk: RiskManager | None = None
        pubsub = None
        tick_ch = None
        adapter = None
        usm = None
        symbol = None
        flatten_reason = None
        self._last_ltp = None

        # Load UserStrategyMap with related Strategy eagerly
        result = await self.db.execute(
            select(UserStrategyMap)
            .options(selectinload(UserStrategyMap.strategy))
            .where(UserStrategyMap.id == UUID(self.map_id))
        )
        usm = result.scalar_one_or_none()
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

        # Risk config — persisted in Redis by map_id
        risk = RiskManager(
            RiskConfig(
                daily_loss_limit       = float(usm.params.get("daily_loss_limit", 5000)),
                max_exposure           = float(usm.params.get("max_exposure", 50000)),
                max_quantity           = int(usm.params.get("max_quantity", 100)),
                max_consecutive_losses = int(usm.params.get("max_losses", 3)),
                paper_trading          = usm.paper_trading,
            ),
            map_id=self.map_id,
        )
        await risk.load()

        try:
            adapter = get_broker_adapter(broker_account)
        except Exception as e:
            logger.error(f"Broker adapter unavailable for {self.map_id}: {e}")
            return

        symbol    = usm.params.get("symbol", "RELIANCE")
        exchange  = usm.params.get("exchange", "NSE")
        token     = usm.params.get("token", "2885")
        timeframe = int(usm.params.get("timeframe_minutes", 1))

        await reconcile_open_trades(self.db, adapter, usm, symbol, token, strategy)
        if risk.is_killed:
            logger.error(f"Risk kill active for {self.map_id} — flattening and not starting")
            pnls = await flatten_open_trades(
                self.db, redis, adapter,
                await load_open_trades(self.db, usm, symbol),
                reason="KILL",
            )
            for pnl in pnls:
                risk.record_trade_pnl(pnl)
            await risk.save()
            await self._publish_status(redis, "killed", risk)
            return

        # Mark running
        await redis.set(strategy_running_key(self.map_id), "1", ex=86400)
        await self._publish_status(redis, "running", risk)
        logger.info(f"▶ Executor started: {self.map_id} | {symbol} | TF={timeframe}m")

        # Subscribe to tick channel
        tick_ch = f"tick:{exchange}:{token}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(tick_ch)

        last_bar_ts = None

        try:
            async for message in pubsub.listen():
                # Check stop flag via Redis key
                still_running = await redis.get(strategy_running_key(self.map_id))
                if self._stop_flag or not still_running:
                    logger.info(f"⏹ Stop signal received for {self.map_id}")
                    flatten_reason = "STOP"
                    break

                if message["type"] != "message":
                    continue

                try:
                    tick = json.loads(message["data"])
                except Exception:
                    continue

                record_tick(exchange, token, tick)

                # Evaluate only when a new fully closed bar appears
                df = build_ohlcv_closed(exchange, token, timeframe_minutes=timeframe)
                bar_ts = latest_closed_bar_ts(df)
                if bar_ts is None or df.empty or len(df) < 2:
                    logger.debug(f"Not enough closed candles yet: {len(df)}")
                    continue
                if last_bar_ts is not None and bar_ts == last_bar_ts:
                    continue
                last_bar_ts = bar_ts
                logger.info(f"🕯 Closed bar {bar_ts} — evaluating signal")

                signal = strategy.generate_signal(df)
                if signal is None or signal.direction == "HOLD":
                    continue

                logger.info(f"📡 Signal: {signal.direction} {signal.quantity} {signal.symbol}")

                ltp = float(tick.get("ltp", df["close"].iloc[-1]))
                self._last_ltp = ltp
                allowed, reason = risk.check_order(
                    signal.symbol, signal.quantity, ltp, signal.direction
                )
                if not allowed:
                    logger.warning(f"🚫 Risk blocked: {reason}")
                    await risk.save()
                    await self._publish_status(redis, f"blocked:{reason}", risk)
                    if risk.is_killed:
                        flatten_reason = "KILL"
                        break
                    continue

                # One order per map + closed bar + side. Survives worker restarts.
                client_order_id = client_order_id_for(
                    self.map_id, bar_ts, signal.symbol, signal.direction
                )
                if not await claim_order_intent(redis, client_order_id):
                    logger.warning(
                        f"Duplicate order suppressed: {client_order_id} "
                        f"{signal.direction} {signal.symbol}"
                    )
                    await self._publish_status(redis, "duplicate_suppressed", risk)
                    continue

                # signal → PENDING, then broker result moves it to OPEN or CANCELLED
                sl_price, target_price = _protective_prices(signal, ltp, usm.params)
                trade = Trade(
                    user_id           = usm.user_id,
                    broker_account_id = usm.broker_account_id,
                    strategy_id       = usm.strategy_id,
                    symbol            = signal.symbol,
                    exchange          = signal.exchange,
                    direction         = TradeDirection[signal.direction],
                    quantity          = signal.quantity,
                    stop_loss         = sl_price,
                    target_price      = target_price,
                    strategy_tag      = usm.strategy.name if usm.strategy else None,
                    status            = TradeStatus.PENDING,
                    is_paper          = usm.paper_trading,
                )
                self.db.add(trade)
                await self.db.commit()

                try:
                    if not usm.paper_trading:
                        from app.core.trading_mode import assert_feed_fresh
                        await assert_feed_fresh(redis)
                    order_resp = await adapter.place_order(OrderRequest(
                        symbol          = signal.symbol,
                        exchange        = signal.exchange,
                        direction       = signal.direction,
                        quantity        = signal.quantity,
                        order_type      = signal.order_type,
                        price           = signal.price or ltp,
                        client_order_id = client_order_id,
                    ))
                except Exception as e:
                    await release_order_intent(redis, client_order_id)
                    apply_order_result(trade, "REJECTED")
                    await self.db.commit()
                    logger.error(f"Order place error: {e}")
                    await self._publish_status(redis, "order_rejected", risk)
                    continue

                if not order_resp.broker_order_id or order_resp.status == "FAILED":
                    await release_order_intent(redis, client_order_id)
                    apply_order_result(trade, "REJECTED")
                    await self.db.commit()
                    logger.error(
                        f"Order place failed: status={order_resp.status} msg={order_resp.message}"
                    )
                    await self._publish_status(redis, "order_rejected", risk)
                    continue

                trade.broker_order_id = order_resp.broker_order_id
                await self.db.commit()
                await commit_order_intent(redis, client_order_id, order_resp.broker_order_id)

                fill = await wait_for_fill(adapter, order_resp.broker_order_id)
                outcome = apply_order_result(
                    trade, fill["status"], fill.get("fill_price") or ltp
                )
                if outcome != "opened":
                    await self.db.commit()
                    if fill["status"] == "TIMEOUT":
                        status_key = "order_timeout"
                    elif outcome == "cancelled":
                        status_key = "order_rejected"
                    else:
                        status_key = "order_pending"
                    logger.error(
                        f"Order not filled: id={order_resp.broker_order_id} "
                        f"result={fill['status']} trade={trade.status}"
                    )
                    await self._publish_status(redis, status_key, risk)
                    continue

                fill_price = float(trade.entry_price or ltp)
                sl_price, target_price = _protective_prices(signal, fill_price, usm.params)
                trade.stop_loss = sl_price
                trade.target_price = target_price
                await self.db.commit()
                strategy.on_order_filled(signal, fill_price)
                await risk.save()
                logger.info(
                    f"✅ Trade open: {signal.direction} {signal.quantity} "
                    f"{signal.symbol} @ ₹{fill_price}"
                )

                await self._publish_status(redis, "running", risk)

        except asyncio.CancelledError:
            flatten_reason = flatten_reason or "STOP"
        except Exception as e:
            logger.error(f"Executor error: {e}", exc_info=True)
        finally:
            if flatten_reason and adapter is not None and usm is not None and symbol:
                try:
                    pnls = await flatten_open_trades(
                        self.db, redis, adapter,
                        await load_open_trades(self.db, usm, symbol),
                        reason=flatten_reason,
                        price_hint=self._last_ltp,
                    )
                    if risk is not None:
                        for pnl in pnls:
                            risk.record_trade_pnl(pnl)
                except Exception as e:
                    logger.error(f"Flatten on {flatten_reason} failed: {e}", exc_info=True)
            if pubsub is not None and tick_ch is not None:
                try:
                    await pubsub.unsubscribe(tick_ch)
                except Exception:
                    pass
            await redis.delete(strategy_running_key(self.map_id))
            if risk is not None:
                await risk.save()
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
