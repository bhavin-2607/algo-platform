"""
Flatten-on-stop and restart recovery.

Open trades in the database are the position record. On start, a live
broker that is already flat closes those rows; otherwise the strategy
engine is told about the open trade. On stop or kill, each open trade
is closed with one opposite order, guarded by the same order claim used
for entries.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.base import OrderRequest
from app.broker.factory import get_broker_adapter
from app.broker.order_ops import claim_order_intent, commit_order_intent, release_order_intent, wait_for_fill
from app.models.broker import BrokerAccount
from app.models.strategy import UserStrategyMap
from app.models.trade import Trade, TradeStatus

logger = logging.getLogger(__name__)


def flatten_client_order_id(trade_id: str) -> str:
    return hashlib.sha256(f"flatten|{trade_id}".encode()).hexdigest()[:24]


def trade_pnl(direction: str, entry: float, exit_price: float, quantity: int) -> float:
    if direction == "BUY":
        return (exit_price - entry) * quantity
    return (entry - exit_price) * quantity


def net_quantity_for(positions: list, symbol: str, token: Optional[str] = None) -> int:
    """Sum broker net qty for this symbol or security id."""
    want = {str(symbol)}
    if token:
        want.add(str(token))
    total = 0
    for pos in positions or []:
        if not isinstance(pos, dict):
            continue
        names = {
            str(pos.get("symbol") or ""),
            str(pos.get("tradingSymbol") or ""),
            str(pos.get("securityId") or ""),
        }
        if names.isdisjoint(want):
            continue
        if pos.get("netQty") is not None:
            total += int(pos.get("netQty") or 0)
        else:
            total += int(pos.get("quantity") or 0)
    return total


def cancel_trade(trade: Trade, reason: str) -> None:
    """Order never became a position. PnL stays zero."""
    trade.status = TradeStatus.CANCELLED
    trade.exit_reason = reason
    trade.closed_at = datetime.utcnow()
    trade.pnl = 0.0
    trade.pnl_pct = 0.0


def apply_order_result(
    trade: Trade,
    status: str,
    fill_price: Optional[float] = None,
) -> str:
    """
    Move a PENDING trade from the broker result.

    Returns "opened", "cancelled", or "pending".
    """
    if trade.status != TradeStatus.PENDING:
        return "pending"
    if status == "FILLED":
        trade.entry_price = float(fill_price or trade.entry_price or 0)
        trade.status = TradeStatus.OPEN
        return "opened"
    if status == "REJECTED":
        cancel_trade(trade, "ORDER_REJECTED")
        return "cancelled"
    if status == "TIMEOUT":
        cancel_trade(trade, "ORDER_TIMEOUT")
        return "cancelled"
    if status == "UNCONFIRMED":
        cancel_trade(trade, "UNCONFIRMED")
        return "cancelled"
    return "pending"


def close_trade(trade: Trade, exit_price: float, reason: str) -> float:
    direction = trade.direction.value if hasattr(trade.direction, "value") else str(trade.direction)
    entry = float(trade.entry_price or exit_price or 0)
    exit_price = float(exit_price or entry)
    qty = int(trade.quantity or 0)
    pnl = trade_pnl(direction, entry, exit_price, qty)
    trade.exit_price = round(exit_price, 2)
    trade.pnl = round(pnl, 2)
    notional = entry * qty
    trade.pnl_pct = round((pnl / notional) * 100, 4) if notional else 0.0
    trade.status = TradeStatus.CLOSED
    trade.exit_reason = reason
    trade.closed_at = datetime.utcnow()
    return float(trade.pnl)


async def _load_trades(db: AsyncSession, usm: UserStrategyMap, symbol: str, status: TradeStatus) -> list[Trade]:
    result = await db.execute(
        select(Trade)
        .where(
            Trade.user_id == usm.user_id,
            Trade.strategy_id == usm.strategy_id,
            Trade.broker_account_id == usm.broker_account_id,
            Trade.symbol == symbol,
            Trade.is_paper == bool(usm.paper_trading),
            Trade.status == status,
        )
        .order_by(Trade.created_at.asc())
    )
    return list(result.scalars().all())


async def load_open_trades(db: AsyncSession, usm: UserStrategyMap, symbol: str) -> list[Trade]:
    return await _load_trades(db, usm, symbol, TradeStatus.OPEN)


async def resolve_pending_trades(db: AsyncSession, adapter, usm: UserStrategyMap, symbol: str) -> None:
    """On restart, promote or cancel trades left PENDING when the worker died."""
    from app.broker.order_ops import _extract_status_and_price

    pending = await _load_trades(db, usm, symbol, TradeStatus.PENDING)
    if not pending:
        return

    changed = False
    for trade in pending:
        if not trade.broker_order_id:
            apply_order_result(trade, "UNCONFIRMED")
            changed = True
            continue
        try:
            raw = await adapter.get_order_status(trade.broker_order_id) or {}
        except Exception as e:
            logger.warning(f"Pending order status failed for {trade.id}: {e}")
            raw = {}
        status, price = _extract_status_and_price(raw)
        if status == "UNKNOWN" and usm.paper_trading and not raw:
            # Paper state lived in the old process. An unknown order did not fill.
            outcome = apply_order_result(trade, "UNCONFIRMED")
        elif status == "FILLED":
            outcome = apply_order_result(trade, "FILLED", price or trade.entry_price)
        elif status == "REJECTED":
            outcome = apply_order_result(trade, "REJECTED")
        else:
            outcome = "pending"
        if outcome != "pending":
            changed = True
            logger.info(f"Pending trade {trade.id} → {trade.status} ({trade.exit_reason or 'filled'})")
    if changed:
        await db.commit()


async def reconcile_open_trades(
    db: AsyncSession,
    adapter,
    usm: UserStrategyMap,
    symbol: str,
    token: Optional[str],
    strategy,
) -> list[Trade]:
    """
    Paper trusts the database (the paper adapter is empty after a restart).
    Live closes database rows when the broker is flat, and otherwise restores
    the engine so it does not enter again. Pending orders are resolved first.
    """
    await resolve_pending_trades(db, adapter, usm, symbol)
    trades = await load_open_trades(db, usm, symbol)
    if not usm.paper_trading:
        try:
            net = net_quantity_for(await adapter.get_positions(), symbol, token)
        except Exception as e:
            logger.warning(f"Broker position read failed for {symbol}: {e}")
            net = None
        if not trades and net:
            logger.warning(
                f"Broker net {net} on {symbol} with no open trade for map {usm.id}"
            )
        if trades and net == 0:
            for trade in trades:
                close_trade(trade, float(trade.entry_price or 0), "RECONCILED")
            await db.commit()
            logger.warning(
                f"Broker flat for {symbol} — closed {len(trades)} stale trade(s)"
            )
            return []
    if not trades:
        return []

    latest = trades[-1]
    direction = latest.direction.value if hasattr(latest.direction, "value") else str(latest.direction)
    strategy.restore_position(direction, int(latest.quantity or 0))
    logger.info(
        f"Restored {direction} x{latest.quantity} from {len(trades)} open trade(s)"
    )
    return trades


async def flatten_open_trades(
    db: AsyncSession,
    redis,
    adapter,
    trades: list[Trade],
    reason: str = "STOP",
    price_hint: Optional[float] = None,
) -> list[float]:
    """Place one closing order per open trade. Returns realized PnL for each close."""
    pnls: list[float] = []
    for trade in trades:
        if trade.status != TradeStatus.OPEN or trade.id is None:
            continue
        direction = trade.direction.value if hasattr(trade.direction, "value") else str(trade.direction)
        close_side = "SELL" if direction == "BUY" else "BUY"
        client_order_id = flatten_client_order_id(str(trade.id))
        if not await claim_order_intent(redis, client_order_id):
            logger.info(f"Flatten already in progress for trade {trade.id}")
            continue

        price = float(price_hint or trade.entry_price or 0)
        try:
            order_resp = await adapter.place_order(OrderRequest(
                symbol=trade.symbol,
                exchange=trade.exchange,
                direction=close_side,
                quantity=int(trade.quantity or 0),
                order_type="MARKET",
                price=price,
                client_order_id=client_order_id,
            ))
        except Exception as e:
            await release_order_intent(redis, client_order_id)
            logger.error(f"Flatten place error for {trade.id}: {e}")
            continue

        if not order_resp.broker_order_id or order_resp.status == "FAILED":
            await release_order_intent(redis, client_order_id)
            logger.error(
                f"Flatten rejected for {trade.id}: {order_resp.status} {order_resp.message}"
            )
            continue

        await commit_order_intent(redis, client_order_id, order_resp.broker_order_id)
        fill = await wait_for_fill(adapter, order_resp.broker_order_id)
        if fill["status"] != "FILLED":
            logger.error(f"Flatten not filled for {trade.id}: {fill['status']}")
            continue

        exit_price = float(fill["fill_price"] or price)
        pnls.append(close_trade(trade, exit_price, reason))
        logger.info(f"Flattened {trade.symbol} {close_side} @ ₹{exit_price} ({reason})")

    if pnls:
        await db.commit()
    return pnls


async def flatten_map(db: AsyncSession, redis, map_id: str, reason: str = "STOP") -> list[float]:
    """Flatten whatever this strategy map still has open. Safe if the worker is already dead."""
    from uuid import UUID

    usm = await db.get(UserStrategyMap, UUID(map_id))
    if usm is None:
        return []
    symbol = (usm.params or {}).get("symbol", "RELIANCE")
    trades = await load_open_trades(db, usm, symbol)
    if not trades:
        return []

    account = await db.get(BrokerAccount, usm.broker_account_id)
    if account is None:
        logger.error(f"No broker account for map {map_id}; left {len(trades)} trade(s) open")
        return []
    if not account.paper_trading:
        from app.core.trading_mode import LiveTradingError, assert_live_allowed
        try:
            assert_live_allowed()
        except LiveTradingError as e:
            logger.error(f"Live flatten blocked for {map_id}: {e}")
            return []
    try:
        adapter = get_broker_adapter(account)
    except Exception as e:
        logger.error(f"Flatten adapter unavailable for {map_id}: {e}")
        return []
    return await flatten_open_trades(db, redis, adapter, trades, reason=reason)


async def flatten_all_open(db: AsyncSession, redis, reason: str = "KILL") -> int:
    """Close every open trade. Used by the global live kill switch."""
    result = await db.execute(
        select(Trade).where(Trade.status == TradeStatus.OPEN)
    )
    trades = list(result.scalars().all())
    by_account: dict = {}
    for trade in trades:
        by_account.setdefault(trade.broker_account_id, []).append(trade)

    closed = 0
    for account_id, group in by_account.items():
        account = await db.get(BrokerAccount, account_id)
        if account is None:
            continue
        if not account.paper_trading:
            from app.core.trading_mode import LiveTradingError, assert_live_allowed
            try:
                assert_live_allowed()
            except LiveTradingError as e:
                logger.error(f"Live flatten blocked: {e}")
                continue
        try:
            adapter = get_broker_adapter(account)
        except Exception as e:
            logger.error(f"Flatten adapter unavailable: {e}")
            continue
        pnls = await flatten_open_trades(db, redis, adapter, group, reason=reason)
        closed += len(pnls)
    return closed
