"""
Formula Strategy Routes
=======================
CRUD for no-code formula strategies and managed positions.
"""
import json
import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.formula import FormulaStrategy, ManagedPosition, PositionStatus
from app.models.broker import BrokerAccount
from app.services.order_manager import OrderManager
from app.strategy.formula_engine import validate_formula, FormulaEvaluator
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class FormulaStrategyCreate(BaseModel):
    name:              str
    symbol:            str
    exchange:          str   = "NSE"
    token:             str   = "2885"
    entry_long:        Optional[str] = None
    entry_short:       Optional[str] = None
    exit_long:         Optional[str] = None
    exit_short:        Optional[str] = None
    quantity:          int   = 1
    product_type:      str   = "MIS"
    order_type:        str   = "MARKET"
    timeframe_minutes: int   = 5
    target_pct:        Optional[float] = None
    sl_pct:            Optional[float] = None
    trailing_sl:       bool  = False
    trail_pct:         Optional[float] = None
    paper_trading:     bool  = True
    broker_account_id: Optional[UUID] = None


class ManualPositionCreate(BaseModel):
    symbol:            str
    exchange:          str   = "NSE"
    direction:         str               # BUY / SELL
    quantity:          int
    entry_price:       float
    broker_account_id: UUID
    target_pct:        Optional[float] = None
    sl_pct:            Optional[float] = None
    trailing_sl:       bool  = False
    trail_pct:         Optional[float] = None
    paper_trading:     bool  = True


# ── Formula Strategy CRUD ─────────────────────────────────────────────────────

@router.get("")
async def list_formula_strategies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FormulaStrategy).where(FormulaStrategy.user_id == current_user.id)
    )
    strats = result.scalars().all()
    redis  = get_redis()
    out    = []
    for s in strats:
        is_running = bool(await redis.get(f"formula:running:{s.id}"))
        out.append({
            "id":               str(s.id),
            "name":             s.name,
            "symbol":           s.symbol,
            "exchange":         s.exchange,
            "entry_long":       s.entry_long,
            "entry_short":      s.entry_short,
            "exit_long":        s.exit_long,
            "exit_short":       s.exit_short,
            "quantity":         s.quantity,
            "timeframe_minutes":s.timeframe_minutes,
            "target_pct":       s.target_pct,
            "sl_pct":           s.sl_pct,
            "trailing_sl":      s.trailing_sl,
            "trail_pct":        s.trail_pct,
            "is_active":        s.is_active,
            "is_running":       is_running,
            "paper_trading":    s.paper_trading,
        })
    return out


@router.post("", status_code=201)
async def create_formula_strategy(
    payload: FormulaStrategyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate all provided formulas
    for field, expr in [
        ("entry_long",  payload.entry_long),
        ("entry_short", payload.entry_short),
        ("exit_long",   payload.exit_long),
        ("exit_short",  payload.exit_short),
    ]:
        if expr:
            ok, err = validate_formula(expr)
            if not ok:
                raise HTTPException(status_code=400, detail=f"Invalid formula [{field}]: {err}")

    strat = FormulaStrategy(
        user_id           = current_user.id,
        name              = payload.name,
        symbol            = payload.symbol.upper(),
        exchange          = payload.exchange.upper(),
        token             = payload.token,
        entry_long        = payload.entry_long,
        entry_short       = payload.entry_short,
        exit_long         = payload.exit_long,
        exit_short        = payload.exit_short,
        quantity          = payload.quantity,
        product_type      = payload.product_type,
        order_type        = payload.order_type,
        timeframe_minutes = payload.timeframe_minutes,
        target_pct        = payload.target_pct,
        sl_pct            = payload.sl_pct,
        trailing_sl       = payload.trailing_sl,
        trail_pct         = payload.trail_pct,
        paper_trading     = payload.paper_trading,
        broker_account_id = payload.broker_account_id,
    )
    db.add(strat)
    await db.commit()
    await db.refresh(strat)
    return {"id": str(strat.id), "name": strat.name}


@router.put("/{strategy_id}")
async def update_formula_strategy(
    strategy_id: UUID,
    payload: FormulaStrategyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    strat = await _get_strat(strategy_id, current_user.id, db)

    for field, expr in [("entry_long", payload.entry_long), ("entry_short", payload.entry_short),
                        ("exit_long",  payload.exit_long),  ("exit_short",  payload.exit_short)]:
        if expr:
            ok, err = validate_formula(expr)
            if not ok:
                raise HTTPException(status_code=400, detail=f"Invalid formula [{field}]: {err}")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(strat, k, v)
    await db.commit()
    return {"status": "updated"}


@router.delete("/{strategy_id}", status_code=204)
async def delete_formula_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    strat = await _get_strat(strategy_id, current_user.id, db)
    await db.delete(strat)
    await db.commit()


@router.post("/{strategy_id}/start")
async def start_formula_strategy(
    strategy_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    strat = await _get_strat(strategy_id, current_user.id, db)
    strat.is_active = True
    await db.commit()

    # Start simulated feed if paper trading
    if strat.paper_trading:
        from app.worker.tasks import start_simulated_feed
        start_simulated_feed.delay(
            exchange=strat.exchange, token=strat.token, base_price=2800.0
        )

    # Launch formula executor via Celery
    from app.worker.tasks import run_formula_strategy
    task = run_formula_strategy.delay(str(strategy_id))
    return {"status": "started", "task_id": task.id}


@router.post("/{strategy_id}/stop")
async def stop_formula_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    strat = await _get_strat(strategy_id, current_user.id, db)
    strat.is_active = False
    await db.commit()

    redis = get_redis()
    await redis.delete(f"formula:running:{strategy_id}")
    return {"status": "stopped"}


@router.post("/validate-formula")
async def validate_formula_endpoint(
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """Validate a formula expression before saving."""
    expr = body.get("expression", "")
    ok, err = validate_formula(expr)
    return {"valid": ok, "error": err}


# ── Managed Positions ─────────────────────────────────────────────────────────

@router.get("/positions")
async def list_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
):
    q = select(ManagedPosition).where(ManagedPosition.user_id == current_user.id)
    if status:
        q = q.where(ManagedPosition.status == status)
    q = q.order_by(ManagedPosition.created_at.desc()).limit(100)
    result = await db.execute(q)
    positions = result.scalars().all()

    return [_pos_dict(p) for p in positions]


@router.post("/positions", status_code=201)
async def open_manual_position(
    payload: ManualPositionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually open a managed position with T/SL from the UI."""
    mgr = OrderManager(db)
    pos = await mgr.open_position(
        user_id           = current_user.id,
        broker_account_id = payload.broker_account_id,
        symbol            = payload.symbol.upper(),
        exchange          = payload.exchange.upper(),
        direction         = payload.direction.upper(),
        quantity          = payload.quantity,
        entry_price       = payload.entry_price,
        entry_order_id    = "MANUAL",
        target_pct        = payload.target_pct,
        sl_pct            = payload.sl_pct,
        trailing_sl       = payload.trailing_sl,
        trail_pct         = payload.trail_pct,
        is_paper          = payload.paper_trading,
    )
    return _pos_dict(pos)


@router.post("/positions/{pos_id}/exit")
async def exit_position(
    pos_id: UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually exit a position at a given price."""
    result = await db.execute(
        select(ManagedPosition).where(
            ManagedPosition.id      == pos_id,
            ManagedPosition.user_id == current_user.id,
            ManagedPosition.status  == PositionStatus.open,
        )
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Open position not found")

    ltp = float(body.get("ltp", pos.entry_price))
    mgr = OrderManager(db)
    pos = await mgr.manual_exit(pos, ltp)
    return _pos_dict(pos)


@router.patch("/positions/{pos_id}/sl")
async def update_sl(
    pos_id: UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update SL price for an open position."""
    result = await db.execute(
        select(ManagedPosition).where(
            ManagedPosition.id      == pos_id,
            ManagedPosition.user_id == current_user.id,
        )
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    if "sl_price" in body:
        pos.sl_price = float(body["sl_price"])
    if "target_price" in body:
        pos.target_price = float(body["target_price"])
    if "trailing_sl" in body:
        pos.trailing_sl = bool(body["trailing_sl"])

    await db.commit()
    return _pos_dict(pos)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_strat(strategy_id: UUID, user_id, db: AsyncSession) -> FormulaStrategy:
    result = await db.execute(
        select(FormulaStrategy).where(
            FormulaStrategy.id      == strategy_id,
            FormulaStrategy.user_id == user_id,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Formula strategy not found")
    return s


def _pos_dict(p: ManagedPosition) -> dict:
    pnl_pct = None
    if p.entry_price and p.exit_price:
        pnl_pct = round((p.exit_price - p.entry_price) / p.entry_price * 100, 2)
        if p.direction == "SELL":
            pnl_pct = -pnl_pct

    return {
        "id":             str(p.id),
        "symbol":         p.symbol,
        "exchange":       p.exchange,
        "direction":      p.direction,
        "quantity":       p.quantity,
        "entry_price":    p.entry_price,
        "exit_price":     p.exit_price,
        "target_price":   p.target_price,
        "sl_price":       p.sl_price,
        "trailing_sl":    p.trailing_sl,
        "trail_pct":      p.trail_pct,
        "peak_price":     p.peak_price,
        "pnl":            p.pnl,
        "pnl_pct":        pnl_pct,
        "status":         p.status,
        "exit_reason":    p.exit_reason,
        "is_paper":       p.is_paper,
        "created_at":     p.created_at.isoformat() if p.created_at else None,
        "closed_at":      p.closed_at.isoformat() if p.closed_at else None,
    }
