"""
Order Manager
=============
Monitors all open ManagedPositions in real-time and automatically:
  - Exits at target price
  - Exits at stop loss price
  - Trails the SL upward as price moves in favour

Runs as a background asyncio task inside the strategy executor.
Also used by the Formula Strategy Executor.
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
from app.broker.order_ops import place_once
from app.core.redis_client import get_redis
from app.strategy.recovery import flatten_client_order_id
from app.models.formula import ManagedPosition, PositionStatus
from app.models.broker import BrokerAccount

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Monitors open positions and exits them when target/SL conditions are met.
    Call update_position() on every tick for each tracked position.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def open_position(
        self,
        user_id:           UUID,
        broker_account_id: UUID,
        symbol:            str,
        exchange:          str,
        direction:         str,
        quantity:          int,
        entry_price:       float,
        entry_order_id:    str,
        target_pct:        float | None = None,
        sl_pct:            float | None = None,
        trailing_sl:       bool         = False,
        trail_pct:         float | None = None,
        strategy_id:       UUID | None  = None,
        is_paper:          bool         = True,
    ) -> ManagedPosition:
        """Create a new managed position after an entry order is filled."""

        # Calculate absolute price levels
        target_price = None
        sl_price     = None

        if target_pct or sl_pct:
            from app.strategy.exits import protective_prices
            sl_price, target_price = protective_prices(
                direction,
                entry_price,
                sl_pct=float(sl_pct or 0),
                target_pct=float(target_pct or 0),
                sl=None if not sl_pct else None,
                target=None if not target_pct else None,
            )
            if not target_pct:
                target_price = None
            if not sl_pct:
                sl_price = None

        pos = ManagedPosition(
            strategy_id       = strategy_id,
            user_id           = user_id,
            broker_account_id = broker_account_id,
            symbol            = symbol,
            exchange          = exchange,
            direction         = direction,
            quantity          = quantity,
            entry_price       = entry_price,
            entry_order_id    = entry_order_id,
            target_price      = target_price,
            sl_price          = sl_price,
            trailing_sl       = trailing_sl,
            trail_pct         = trail_pct,
            peak_price        = entry_price,
            is_paper          = is_paper,
            status            = PositionStatus.open,
        )
        self.db.add(pos)
        await self.db.commit()
        await self.db.refresh(pos)

        logger.info(
            f"📌 Position opened: {direction} {quantity} {symbol} @ ₹{entry_price}"
            f" | T={target_price} SL={sl_price} Trail={trailing_sl}"
        )
        return pos

    async def update_position(self, pos: ManagedPosition, ltp: float) -> ManagedPosition:
        """
        Called on every tick. Updates trailing SL and checks exit conditions.
        Returns the updated position (status may change to closed).
        """
        if pos.status != PositionStatus.open:
            return pos

        # ── Update peak price & trail SL ─────────────────────────────────────
        if pos.trailing_sl and pos.trail_pct:
            from app.strategy.exits import trail_stop
            peak, new_sl = trail_stop(
                pos.direction, ltp, pos.peak_price, pos.sl_price, float(pos.trail_pct)
            )
            pos.peak_price = peak
            if new_sl is not None:
                pos.sl_price = new_sl
                logger.info(f"↑ Trailing SL updated: {pos.symbol} SL=₹{new_sl}")

        # ── Check target ──────────────────────────────────────────────────────
        if pos.target_price:
            target_hit = (
                (pos.direction == "BUY"  and ltp >= pos.target_price) or
                (pos.direction == "SELL" and ltp <= pos.target_price)
            )
            if target_hit:
                return await self._exit_position(pos, ltp, "TARGET_HIT", PositionStatus.target_hit)

        # ── Check stop loss ───────────────────────────────────────────────────
        if pos.sl_price:
            sl_hit = (
                (pos.direction == "BUY"  and ltp <= pos.sl_price) or
                (pos.direction == "SELL" and ltp >= pos.sl_price)
            )
            if sl_hit:
                return await self._exit_position(pos, ltp, "SL_HIT", PositionStatus.sl_hit)

        await self.db.commit()
        return pos

    async def manual_exit(self, pos: ManagedPosition, ltp: float) -> ManagedPosition:
        """Manually close a position at current LTP."""
        return await self._exit_position(pos, ltp, "MANUAL_EXIT", PositionStatus.closed)

    async def _exit_position(
        self,
        pos:    ManagedPosition,
        ltp:    float,
        reason: str,
        status: PositionStatus,
    ) -> ManagedPosition:
        # Place exit order via broker. Stay open until the fill is confirmed.
        ba = await self.db.get(BrokerAccount, pos.broker_account_id)
        if not ba:
            logger.error(f"Exit skipped for {pos.symbol}: no broker account")
            return pos
        try:
            adapter = get_broker_adapter(ba)
        except Exception as e:
            logger.error(f"Exit adapter unavailable for {pos.symbol}: {e}")
            return pos

        exit_direction = "SELL" if pos.direction == "BUY" else "BUY"
        redis = get_redis()
        result = await place_once(
            redis,
            adapter,
            OrderRequest(
                symbol     = pos.symbol,
                exchange   = pos.exchange,
                direction  = exit_direction,
                quantity   = pos.quantity,
                order_type = "MARKET",
                price      = ltp,
            ),
            flatten_client_order_id(str(pos.id)),
        )
        if not result["ok"]:
            logger.error(f"Exit not filled for {pos.symbol}: {result['status']}")
            return pos

        exit_price = float(result["fill_price"] or ltp)
        pos.exit_order_id = result["broker_order_id"]

        # Calculate P&L
        if pos.direction == "BUY":
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        pos.exit_price  = exit_price
        pos.pnl         = round(pnl, 2)
        pos.status      = status
        pos.exit_reason = reason
        pos.closed_at   = datetime.utcnow()

        await self.db.commit()

        emoji = "✅" if pnl >= 0 else "❌"
        logger.info(
            f"{emoji} Position closed: {pos.symbol} @ ₹{exit_price} | "
            f"Reason={reason} PnL=₹{pnl:.2f}"
        )

        # Publish to Redis for live UI update
        redis = get_redis()
        await redis.publish(f"position_update:{pos.user_id}", json.dumps({
            "position_id": str(pos.id),
            "symbol":      pos.symbol,
            "pnl":         round(pnl, 2),
            "status":      status.value if hasattr(status, "value") else status,
            "reason":      reason,
            "exit_price":  exit_price,
        }))

        return pos

    async def get_open_positions(self, user_id: UUID) -> list[ManagedPosition]:
        result = await self.db.execute(
            select(ManagedPosition).where(
                ManagedPosition.user_id == user_id,
                ManagedPosition.status  == PositionStatus.open,
            )
        )
        return result.scalars().all()
