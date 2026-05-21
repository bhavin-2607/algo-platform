"""
Signal Fanout Service
=====================
When a TradingView webhook arrives, this service:
  1. Looks up all active followers of the leader
  2. For each auto-execute follower → places order via their broker adapter
  3. For notify-only followers → publishes to Redis (WebSocket picks it up)
  4. Logs each execution result to signal_executions table
"""
import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.broker.factory import get_broker_adapter
from app.broker.base import OrderRequest
from app.core.redis_client import get_redis
from app.models.signal import Signal, SignalExecution, SignalDirection, SignalStatus, CopyRelationship
from app.models.broker import BrokerAccount

logger = logging.getLogger(__name__)


async def fanout_signal(signal: Signal, db: AsyncSession):
    """
    Fan out a signal to all active followers of the leader.
    Called immediately after the webhook is received.
    """
    redis = get_redis()

    signal.status = SignalStatus.executing
    await db.commit()

    result = await db.execute(
        select(CopyRelationship).where(
            CopyRelationship.leader_id == signal.leader_id,
            CopyRelationship.is_active == True,
        )
    )
    relationships = result.scalars().all()

    if not relationships:
        logger.info(f"Signal {signal.id}: no active followers")
        signal.status = SignalStatus.done
        await db.commit()
        return

    logger.info(f"Signal {signal.id}: fanning out to {len(relationships)} followers")

    tasks = [
        _execute_for_follower(signal, rel, db, redis)
        for rel in relationships
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    signal.status = SignalStatus.done
    await db.commit()
    logger.info(f"Signal {signal.id}: fanout complete")


async def _execute_for_follower(
    signal: Signal,
    rel: CopyRelationship,
    db: AsyncSession,
    redis,
):
    execution = SignalExecution(
        signal_id         = signal.id,
        follower_id       = rel.follower_id,
        broker_account_id = rel.broker_account_id,
        quantity          = _calc_qty(signal.quantity, rel.qty_multiplier),
        status            = "pending",
    )
    db.add(execution)
    await db.flush()

    # Publish notification regardless of auto-execute
    await redis.publish(
        f"copy_signal:{rel.follower_id}",
        json.dumps({
            "type":         "signal",
            "signal_id":    str(signal.id),
            "symbol":       signal.symbol,
            "exchange":     signal.exchange,
            "direction":    signal.direction,
            "quantity":     execution.quantity,
            "strategy_tag": signal.strategy_tag,
            "auto_execute": rel.auto_execute,
        }),
    )

    if not rel.auto_execute:
        execution.status = "skipped"
        await db.commit()
        logger.info(f"  Follower {rel.follower_id}: notify-only, skipped")
        return

    if not rel.broker_account_id:
        execution.status    = "failed"
        execution.error_msg = "No broker account linked"
        await db.commit()
        return

    ba_result = await db.execute(
        select(BrokerAccount).where(BrokerAccount.id == rel.broker_account_id)
    )
    broker_account = ba_result.scalar_one_or_none()
    if not broker_account:
        execution.status    = "failed"
        execution.error_msg = "Broker account not found"
        await db.commit()
        return

    try:
        adapter = get_broker_adapter(broker_account)
        order_resp = await adapter.place_order(OrderRequest(
            symbol     = signal.symbol,
            exchange   = signal.exchange,
            direction  = signal.direction if signal.direction != SignalDirection.EXIT else "SELL",
            quantity   = execution.quantity or 1,
            order_type = "MARKET",
            price      = signal.price,
        ))
        execution.status          = "filled"
        execution.broker_order_id = order_resp.broker_order_id
        execution.is_paper        = broker_account.paper_trading
        logger.info(f"  Follower {rel.follower_id}: order placed {order_resp.broker_order_id}")
    except Exception as e:
        execution.status    = "failed"
        execution.error_msg = str(e)
        logger.error(f"  Follower {rel.follower_id}: order failed — {e}")

    await db.commit()


def _calc_qty(leader_qty: int | None, multiplier: float) -> int:
    if not leader_qty:
        return 1
    return max(1, int(leader_qty * multiplier))
