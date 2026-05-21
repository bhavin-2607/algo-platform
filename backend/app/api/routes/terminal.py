"""
Terminal Routes
===============
REST API for the trading terminal — manages rows, starts/stops the engine.

SECURITY:
  - entry_formula and exit_formula are NEVER returned to non-admin users
  - Users only see strategy_label, symbol, live data, and trade status
  - Admin can set/edit formulas
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
from app.core.deps import get_current_user, require_admin
from app.core.redis_client import get_redis
from app.models.user import User, UserRole
from app.models.terminal import TerminalRow, TerminalRowStatus
from app.services.terminal_engine import TERMINAL_TICK_KEY, TERMINAL_RUN_KEY
from app.strategy.formula_engine import validate_formula

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TerminalRowCreate(BaseModel):
    symbol:            str
    exchange:          str   = "NSE"
    token:             Optional[str] = None
    strategy_label:    Optional[str] = None   # shown to user
    entry_formula:     Optional[str] = None   # hidden from users
    exit_formula:      Optional[str] = None   # hidden from users
    quantity:          int   = 1
    product_type:      str   = "MIS"
    order_type:        str   = "MARKET"
    trade_mode:        str   = "PAPER"
    target_pct:        Optional[float] = None
    sl_pct:            Optional[float] = None
    trailing_sl:       bool  = False
    trail_pct:         Optional[float] = None
    auto_execute:      bool  = True
    broker_account_id: Optional[UUID] = None
    row_order:         int   = 0


# ── Terminal Row CRUD ─────────────────────────────────────────────────────────

@router.get("/rows")
async def list_rows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all terminal rows for the current user.
    Formulas are hidden unless user is admin.
    """
    result = await db.execute(
        select(TerminalRow)
        .where(TerminalRow.owner_id == current_user.id)
        .order_by(TerminalRow.row_order)
    )
    rows   = result.scalars().all()
    redis  = get_redis()
    is_admin = current_user.role == UserRole.admin

    out = []
    for r in rows:
        # Fetch latest live tick from Redis
        raw  = await redis.get(TERMINAL_TICK_KEY.format(row_id=r.id))
        live = json.loads(raw) if raw else {}

        row_data = {
            "id":             str(r.id),
            "symbol":         r.symbol,
            "exchange":       r.exchange,
            "strategy_label": r.strategy_label or "Custom Strategy",
            "quantity":       r.quantity,
            "product_type":   r.product_type,
            "trade_mode":     r.trade_mode,
            "target_pct":     r.target_pct,
            "sl_pct":         r.sl_pct,
            "trailing_sl":    r.trailing_sl,
            "trail_pct":      r.trail_pct,
            "auto_execute":   r.auto_execute,
            "is_active":      r.is_active,
            "status":         r.status,
            "row_order":      r.row_order,
            # Live data
            "ltp":            live.get("ltp",    r.last_ltp),
            "open":           live.get("open"),
            "high":           live.get("high"),
            "low":            live.get("low"),
            "volume":         live.get("volume"),
            "oi":             live.get("oi"),
            "bp1":            live.get("bp1"),
            "sp1":            live.get("sp1"),
            "signal":         live.get("signal", r.last_signal or "—"),
            # Position
            "entry_price":    r.entry_price,
            "current_sl":     r.current_sl,
            "current_target": r.current_target,
            "pnl":            live.get("pnl", r.pnl),
        }

        # Only expose formulas to admin
        if is_admin:
            row_data["entry_formula"] = r.entry_formula
            row_data["exit_formula"]  = r.exit_formula

        out.append(row_data)

    return out


@router.post("/rows", status_code=201)
async def add_row(
    payload: TerminalRowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new symbol row to the terminal."""
    # Validate formulas if provided
    for field, expr in [("entry_formula", payload.entry_formula), ("exit_formula", payload.exit_formula)]:
        if expr:
            ok, err = validate_formula(expr)
            if not ok:
                raise HTTPException(status_code=400, detail=f"Invalid {field}: {err}")

    row = TerminalRow(
        owner_id          = current_user.id,
        symbol            = payload.symbol.upper(),
        exchange          = payload.exchange.upper(),
        token             = payload.token,
        strategy_label    = payload.strategy_label,
        entry_formula     = payload.entry_formula,
        exit_formula      = payload.exit_formula,
        quantity          = payload.quantity,
        product_type      = payload.product_type,
        order_type        = payload.order_type,
        trade_mode        = payload.trade_mode,
        target_pct        = payload.target_pct,
        sl_pct            = payload.sl_pct,
        trailing_sl       = payload.trailing_sl,
        trail_pct         = payload.trail_pct,
        auto_execute      = payload.auto_execute,
        broker_account_id = payload.broker_account_id,
        row_order         = payload.row_order,
        status            = TerminalRowStatus.idle,
        is_active         = False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": str(row.id), "symbol": row.symbol}


@router.put("/rows/{row_id}")
async def update_row(
    row_id: UUID,
    payload: TerminalRowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_row(row_id, current_user.id, db)
    for field, expr in [("entry_formula", payload.entry_formula), ("exit_formula", payload.exit_formula)]:
        if expr:
            ok, err = validate_formula(expr)
            if not ok:
                raise HTTPException(status_code=400, detail=f"Invalid {field}: {err}")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    return {"status": "updated"}


@router.delete("/rows/{row_id}", status_code=204)
async def delete_row(
    row_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_row(row_id, current_user.id, db)
    await db.delete(row)
    await db.commit()


@router.patch("/rows/{row_id}/activate")
async def toggle_row(
    row_id: UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Activate or deactivate a single row."""
    row = await _get_row(row_id, current_user.id, db)
    row.is_active = body.get("is_active", not row.is_active)
    row.status    = TerminalRowStatus.watching if row.is_active else TerminalRowStatus.idle
    await db.commit()
    return {"is_active": row.is_active}


@router.post("/rows/{row_id}/exit")
async def manual_exit_row(
    row_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually exit the current position on a row."""
    row = await _get_row(row_id, current_user.id, db)
    if row.status != TerminalRowStatus.active:
        raise HTTPException(status_code=400, detail="No active position on this row")

    redis = get_redis()
    await redis.publish(
        f"terminal:manual_exit:{row.id}", "1"
    )
    row.status = TerminalRowStatus.exit_pending
    await db.commit()
    return {"status": "exit_pending"}


# ── Terminal Engine Start/Stop ────────────────────────────────────────────────

@router.post("/start")
async def start_terminal(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start the terminal engine for the current user (all active rows)."""
    redis = get_redis()
    already_running = await redis.get(TERMINAL_RUN_KEY.format(user_id=current_user.id))
    if already_running:
        raise HTTPException(status_code=400, detail="Terminal already running")

    # Start simulated feed for paper rows
    result = await db.execute(
        select(TerminalRow).where(
            TerminalRow.owner_id  == current_user.id,
            TerminalRow.is_active == True,
            TerminalRow.trade_mode == "PAPER",
        )
    )
    paper_rows = result.scalars().all()
    for row in paper_rows:
        from app.worker.tasks import start_simulated_feed
        start_simulated_feed.delay(
            exchange   = row.exchange,
            token      = row.token or row.symbol,
            base_price = row.last_ltp or 2800.0,
        )

    # Launch terminal engine via Celery
    from app.worker.tasks import run_terminal
    task = run_terminal.delay(str(current_user.id))
    return {"status": "started", "task_id": task.id}


@router.post("/stop")
async def stop_terminal(
    current_user: User = Depends(get_current_user),
):
    """Stop the terminal engine."""
    redis = get_redis()
    await redis.delete(TERMINAL_RUN_KEY.format(user_id=current_user.id))
    return {"status": "stopped"}


@router.get("/status")
async def terminal_status(
    current_user: User = Depends(get_current_user),
):
    """Check if terminal is running."""
    redis = get_redis()
    running = bool(await redis.get(TERMINAL_RUN_KEY.format(user_id=current_user.id)))
    return {"running": running}


# ── Shared Instrument Search ──────────────────────────────────────────────────

@router.get("/instruments")
async def search_instruments(
    q: str = "",
    current_user: User = Depends(get_current_user),
):
    """Search NSE/NFO instruments for adding to the terminal."""
    INSTRUMENTS = {
        "RELIANCE": {"token": "2885", "exchange": "NSE"},
        "TCS":      {"token": "11536", "exchange": "NSE"},
        "INFY":     {"token": "1594", "exchange": "NSE"},
        "HDFCBANK": {"token": "1333", "exchange": "NSE"},
        "ICICIBANK":{"token": "4963", "exchange": "NSE"},
        "WIPRO":    {"token": "3787", "exchange": "NSE"},
        "SBIN":     {"token": "3045", "exchange": "NSE"},
        "TATAMOTORS":{"token":"3456", "exchange": "NSE"},
        "BAJFINANCE":{"token":"317",  "exchange": "NSE"},
        "NIFTY":    {"token": "26000","exchange": "NSE"},
        "BANKNIFTY":{"token": "26009","exchange": "NSE"},
        "FINNIFTY": {"token": "26037","exchange": "NSE"},
    }
    q = q.upper()
    return [
        {"symbol": sym, **info}
        for sym, info in INSTRUMENTS.items()
        if not q or q in sym
    ]


async def _get_row(row_id: UUID, user_id, db: AsyncSession) -> TerminalRow:
    result = await db.execute(
        select(TerminalRow).where(
            TerminalRow.id       == row_id,
            TerminalRow.owner_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Terminal row not found")
    return row
