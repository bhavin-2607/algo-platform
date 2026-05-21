"""
Trades routes — Phase 4
Trade history and P&L summary pulled from DB.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import date, datetime

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.trade import Trade, TradeStatus

router = APIRouter()


@router.get("")
async def list_trades(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit:  int = Query(50, le=200),
    offset: int = Query(0),
    symbol: Optional[str] = None,
    is_paper: Optional[bool] = None,
):
    """Return paginated trade history for the current user."""
    q = select(Trade).where(Trade.user_id == current_user.id)
    if symbol:
        q = q.where(Trade.symbol == symbol.upper())
    if is_paper is not None:
        q = q.where(Trade.is_paper == is_paper)
    q = q.order_by(Trade.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    trades = result.scalars().all()

    return [
        {
            "id":             str(t.id),
            "symbol":         t.symbol,
            "exchange":       t.exchange,
            "direction":      t.direction,
            "quantity":       t.quantity,
            "entry_price":    t.entry_price,
            "exit_price":     t.exit_price,
            "stop_loss":      t.stop_loss,
            "target_price":   t.target_price,
            "pnl":            t.pnl,
            "pnl_pct":        t.pnl_pct,
            "strategy_tag":   t.strategy_tag,
            "exit_reason":    t.exit_reason,
            "status":         t.status,
            "broker_order_id":t.broker_order_id,
            "is_paper":       t.is_paper,
            "created_at":     t.created_at.isoformat() if t.created_at else None,
            "closed_at":      t.closed_at.isoformat() if t.closed_at else None,
        }
        for t in trades
    ]


@router.get("/summary")
async def trade_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate P&L summary for the dashboard stat cards."""
    # Total trades
    total_q = select(func.count(Trade.id)).where(Trade.user_id == current_user.id)
    total = (await db.execute(total_q)).scalar() or 0

    # Closed trades for P&L
    closed_q = (
        select(Trade)
        .where(Trade.user_id == current_user.id)
        .where(Trade.status == TradeStatus.CLOSED)
        .where(Trade.pnl.isnot(None))
    )
    closed = (await db.execute(closed_q)).scalars().all()

    total_pnl  = sum(t.pnl for t in closed)
    winners    = [t for t in closed if t.pnl > 0]
    win_rate   = round(len(winners) / len(closed) * 100, 1) if closed else 0
    avg_win    = round(sum(t.pnl for t in winners) / len(winners), 2) if winners else 0
    losers     = [t for t in closed if t.pnl < 0]
    avg_loss   = round(sum(t.pnl for t in losers) / len(losers), 2) if losers else 0

    # Today's P&L
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_q = (
        select(func.sum(Trade.pnl))
        .where(Trade.user_id == current_user.id)
        .where(Trade.status == TradeStatus.CLOSED)
        .where(Trade.closed_at >= today_start)
    )
    today_pnl = (await db.execute(today_q)).scalar() or 0.0

    return {
        "total_trades":  total,
        "closed_trades": len(closed),
        "total_pnl":     round(total_pnl, 2),
        "today_pnl":     round(today_pnl, 2),
        "win_rate":      win_rate,
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "winners":       len(winners),
        "losers":        len(losers),
    }
