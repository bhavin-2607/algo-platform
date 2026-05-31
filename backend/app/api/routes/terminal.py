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


# ── Formula Management (Admin only) ──────────────────────────────────────────

class FormulaConfig(BaseModel):
    entry_formula:  Optional[str] = None   # @ORFib / @MACross(9,21) / custom expr
    exit_formula:   Optional[str] = None
    target_formula: Optional[str] = None   # e.g. "entry * 1.02"
    sl_formula:     Optional[str] = None   # e.g. "entry * 0.99"
    trail_pct:      Optional[float] = None
    strategy_label: Optional[str] = None   # shown to user instead of formula


@router.put("/rows/{row_id}/formula")
async def set_row_formula(
    row_id:       UUID,
    payload:      FormulaConfig,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """
    Set or update the hidden formula for a terminal row.
    Admin only — formulas are never returned to regular users.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    row = await _get_row(row_id, current_user.id, db)

    if payload.entry_formula  is not None: row.entry_formula  = payload.entry_formula
    if payload.exit_formula   is not None: row.exit_formula   = payload.exit_formula
    if payload.target_pct     is not None: row.target_pct     = payload.target_pct
    if payload.sl_pct         is not None: row.sl_pct         = payload.sl_pct
    if payload.trailing_sl    is not None: row.trailing_sl    = payload.trailing_sl
    if payload.trail_pct      is not None: row.trail_pct      = payload.trail_pct
    if payload.strategy_label is not None: row.strategy_label = payload.strategy_label

    await db.commit()
    return {"status": "formula updated", "row_id": str(row_id)}


@router.get("/rows/{row_id}/formula")
async def get_row_formula(
    row_id:       UUID,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Get formula config for a row — admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    row = await _get_row(row_id, current_user.id, db)
    return {
        "row_id":        str(row.id),
        "symbol":        row.symbol,
        "entry_formula": row.entry_formula,
        "exit_formula":  row.exit_formula,
        "target_pct":    row.target_pct,
        "sl_pct":        row.sl_pct,
        "trailing_sl":   row.trailing_sl,
        "trail_pct":     row.trail_pct,
        "strategy_label":row.strategy_label,
    }


@router.get("/formula-presets")
async def list_formula_presets(current_user: User = Depends(get_current_user)):
    """
    List available built-in formula shortcuts.
    Visible to admin only to set on rows.
    Users never see these — they only see strategy_label.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    return [
        {
            "shortcut": "@ORFib",
            "name": "Opening Range Fibonacci",
            "description": "Proprietary square-root entry formula. Fires once at 9:15 AM open.",
            "params": "Optional: @ORFib(trail=0.3)",
            "example_entry_label": "ORFib",
        },
        {
            "shortcut": "@ORFib(trail=0.3)",
            "name": "Opening Range Fibonacci + Trailing SL",
            "description": "Same as ORFib but with 0.3% trailing stop loss.",
            "params": "trail = trailing SL %",
            "example_entry_label": "ORFib Trail",
        },
        {
            "shortcut": "@MACross(9,21)",
            "name": "Moving Average Crossover",
            "description": "Golden cross = BUY, Death cross = SELL.",
            "params": "@MACross(fast, slow)",
            "example_entry_label": "MA 9/21",
        },
        {
            "shortcut": "@RSI(14,30,70)",
            "name": "RSI Oversold/Overbought",
            "description": "BUY when RSI < 30, SELL when RSI > 70.",
            "params": "@RSI(period, oversold, overbought)",
            "example_entry_label": "RSI 14",
        },
        {
            "shortcut": "@VWAP",
            "name": "VWAP Breakout",
            "description": "BUY when LTP > VWAP, SELL when LTP < VWAP.",
            "params": "None",
            "example_entry_label": "VWAP",
        },
        {
            "shortcut": "custom",
            "name": "Custom Formula",
            "description": "Write your own entry/exit conditions using indicators.",
            "params": "entry_formula, exit_formula, target_formula, sl_formula",
            "example_entry_label": "Custom",
        },
    ]


# ── Terminal Columns (default + custom, all manageable) ─────────────────────

class ColumnCreate(BaseModel):
    name:        str
    formula:     Optional[str] = None   # None for default cols
    col_key:     Optional[str] = None   # for default cols: "ltp","high" etc
    col_type:    str   = "custom"       # "default" or "custom"
    col_order:   int   = 0
    width:       int   = 80
    is_visible:  bool  = True
    color_rules: Optional[str] = None


@router.get("/columns")
async def list_columns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all terminal columns for user.
    Seeds default columns on first visit.
    Formula hidden from non-admin users.
    """
    from sqlalchemy import select
    from app.models.terminal_column import TerminalColumn, DEFAULT_COLUMNS

    result = await db.execute(
        select(TerminalColumn)
        .where(TerminalColumn.user_id == current_user.id)
        .order_by(TerminalColumn.col_order)
    )
    cols = result.scalars().all()

    # Seed defaults on first visit
    if not cols:
        for d in DEFAULT_COLUMNS:
            db.add(TerminalColumn(
                user_id     = current_user.id,
                name        = d["name"],
                col_key     = d["col_key"],
                col_type    = d["col_type"],
                col_order   = d["col_order"],
                width       = d["width"],
                is_visible  = True,
                color_rules = d["color_rules"],
            ))
        await db.commit()
        result = await db.execute(
            select(TerminalColumn)
            .where(TerminalColumn.user_id == current_user.id)
            .order_by(TerminalColumn.col_order)
        )
        cols = result.scalars().all()

    is_admin = current_user.role == "admin"
    return [
        {
            "id":          str(c.id),
            "name":        c.name,
            "col_key":     c.col_key,
            "col_type":    c.col_type,
            "formula":     c.formula if is_admin else None,
            "col_order":   c.col_order,
            "width":       c.width,
            "is_visible":  c.is_visible,
            "color_rules": c.color_rules,
        }
        for c in cols
    ]


@router.post("/columns", status_code=201)
async def create_column(
    payload: ColumnCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new custom formula column. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    if payload.formula:
        from app.strategy.excel_formula_engine import validate_formula_excel
        ok, msg = validate_formula_excel(payload.formula)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Invalid formula: {msg}")
    else:
        msg = "OK"

    from app.models.terminal_column import TerminalColumn
    from sqlalchemy import select, func

    # Auto-assign col_order to end of list (ignore payload col_order for custom cols)
    max_result = await db.execute(
        select(func.max(TerminalColumn.col_order))
        .where(TerminalColumn.user_id == current_user.id)
    )
    max_order = max_result.scalar() or 0
    auto_order = max_order + 1

    col = TerminalColumn(
        user_id     = current_user.id,
        name        = payload.name.upper(),
        col_key     = payload.col_key,
        col_type    = payload.col_type,
        formula     = payload.formula,
        col_order   = auto_order,
        width       = payload.width,
        is_visible  = payload.is_visible,
        color_rules = payload.color_rules,
    )
    db.add(col)
    await db.commit()
    await db.refresh(col)
    return {"id": str(col.id), "name": col.name, "validated": msg}


@router.patch("/columns/{col_id}/visibility")
async def toggle_column_visibility(
    col_id: UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Show/hide any column — available to all users."""
    from sqlalchemy import select
    from app.models.terminal_column import TerminalColumn

    result = await db.execute(
        select(TerminalColumn).where(
            TerminalColumn.id      == col_id,
            TerminalColumn.user_id == current_user.id,
        )
    )
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Column not found")

    col.is_visible = bool(body.get("is_visible", not col.is_visible))
    await db.commit()
    return {"id": str(col.id), "name": col.name, "is_visible": col.is_visible}


@router.put("/columns/{col_id}")
async def update_column(
    col_id: UUID,
    payload: ColumnCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a column. Admin only for formula changes."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from sqlalchemy import select
    from app.models.terminal_column import TerminalColumn

    result = await db.execute(
        select(TerminalColumn).where(
            TerminalColumn.id      == col_id,
            TerminalColumn.user_id == current_user.id,
        )
    )
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Column not found")

    if payload.formula:
        from app.strategy.excel_formula_engine import validate_formula_excel
        ok, msg = validate_formula_excel(payload.formula)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Invalid formula: {msg}")

    col.name        = payload.name.upper()
    col.formula     = payload.formula
    col.col_order   = payload.col_order
    col.width       = payload.width
    col.is_visible  = payload.is_visible
    col.color_rules = payload.color_rules
    await db.commit()
    return {"status": "updated", "name": col.name}


@router.delete("/columns/{col_id}", status_code=204)
async def delete_column(
    col_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete any column — default or custom. All users can remove columns."""
    from sqlalchemy import select
    from app.models.terminal_column import TerminalColumn

    result = await db.execute(
        select(TerminalColumn).where(
            TerminalColumn.id      == col_id,
            TerminalColumn.user_id == current_user.id,
        )
    )
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Column not found")

    await db.delete(col)
    await db.commit()


@router.post("/columns/reset")
async def reset_columns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset columns to defaults — deletes all and reseeds."""
    from sqlalchemy import delete as sa_delete
    from app.models.terminal_column import TerminalColumn, DEFAULT_COLUMNS

    await db.execute(
        sa_delete(TerminalColumn).where(TerminalColumn.user_id == current_user.id)
    )
    for d in DEFAULT_COLUMNS:
        db.add(TerminalColumn(
            user_id     = current_user.id,
            name        = d["name"],
            col_key     = d["col_key"],
            col_type    = d["col_type"],
            col_order   = d["col_order"],
            width       = d["width"],
            is_visible  = True,
            color_rules = d["color_rules"],
        ))
    await db.commit()
    return {"status": "reset", "columns": len(DEFAULT_COLUMNS)}


@router.post("/columns/validate")
async def validate_column_formula(
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """Validate a formula before saving."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from app.strategy.excel_formula_engine import validate_formula_excel
    ok, msg = validate_formula_excel(body.get("formula", ""))
    return {"valid": ok, "message": msg}



class ColumnCreate(BaseModel):
    name:        str
    formula:     str
    col_order:   int   = 0
    width:       int   = 80
    is_visible:  bool  = True
    color_rules: Optional[str] = None  # JSON: {"UP":"green","DOWN":"red"}


@router.get("/columns")
async def list_columns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all formula columns. Formula hidden from non-admin users."""
    from sqlalchemy import select
    from app.models.terminal_column import TerminalColumn

    result = await db.execute(
        select(TerminalColumn)
        .where(TerminalColumn.user_id == current_user.id)
        .order_by(TerminalColumn.col_order)
    )
    cols = result.scalars().all()
    is_admin = current_user.role == "admin"

    return [
        {
            "id":          str(c.id),
            "name":        c.name,
            "formula":     c.formula if is_admin else None,  # hidden from users
            "col_order":   c.col_order,
            "width":       c.width,
            "is_visible":  c.is_visible,
            "color_rules": c.color_rules,
        }
        for c in cols
    ]


@router.post("/columns", status_code=201)
async def create_column(
    payload: ColumnCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new formula column. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    # Validate formula first
    from app.strategy.excel_formula_engine import validate_formula_excel
    ok, msg = validate_formula_excel(payload.formula)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Invalid formula: {msg}")

    from app.models.terminal_column import TerminalColumn
    col = TerminalColumn(
        user_id     = current_user.id,
        name        = payload.name.upper(),
        formula     = payload.formula,
        col_order   = payload.col_order,
        width       = payload.width,
        is_visible  = payload.is_visible,
        color_rules = payload.color_rules,
    )
    db.add(col)
    await db.commit()
    await db.refresh(col)
    return {"id": str(col.id), "name": col.name, "validated": msg}


@router.put("/columns/{col_id}")
async def update_column(
    col_id: UUID,
    payload: ColumnCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a formula column. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from sqlalchemy import select
    from app.models.terminal_column import TerminalColumn

    result = await db.execute(
        select(TerminalColumn).where(
            TerminalColumn.id      == col_id,
            TerminalColumn.user_id == current_user.id,
        )
    )
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Column not found")

    from app.strategy.excel_formula_engine import validate_formula_excel
    ok, msg = validate_formula_excel(payload.formula)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Invalid formula: {msg}")

    col.name        = payload.name.upper()
    col.formula     = payload.formula
    col.col_order   = payload.col_order
    col.width       = payload.width
    col.is_visible  = payload.is_visible
    col.color_rules = payload.color_rules
    await db.commit()
    return {"status": "updated", "name": col.name}


@router.delete("/columns/{col_id}", status_code=204)
async def delete_column(
    col_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a formula column. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from sqlalchemy import select
    from app.models.terminal_column import TerminalColumn

    result = await db.execute(
        select(TerminalColumn).where(
            TerminalColumn.id      == col_id,
            TerminalColumn.user_id == current_user.id,
        )
    )
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Column not found")

    await db.delete(col)
    await db.commit()


@router.post("/columns/validate")
async def validate_column_formula(
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """Validate a formula before saving."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from app.strategy.excel_formula_engine import validate_formula_excel
    ok, msg = validate_formula_excel(body.get("formula", ""))
    return {"valid": ok, "message": msg}


class ManualOrderRequest(BaseModel):
    symbol:           str
    security_id:      str
    exchange_segment: str   = "NSE_EQ"
    transaction_type: str
    quantity:         int
    order_type:       str   = "MARKET"
    product_type:     str   = "INTRADAY"
    price:            float = 0.0
    trigger_price:    float = 0.0


@router.post("/order")
async def place_manual_order(
    body: ManualOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Place a manual BUY/SELL order via Dhan."""
    from app.broker.factory import get_broker_adapter
    from app.broker.base import OrderRequest
    from app.models.broker import BrokerAccount, BrokerName
    from sqlalchemy import select

    result = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.user_id       == current_user.id,
            BrokerAccount.broker        == BrokerName.dhan,
            BrokerAccount.paper_trading == False,
            BrokerAccount.is_active     == True,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=400, detail="No active Dhan live account")

    try:
        adapter  = get_broker_adapter(account)
        order    = OrderRequest(
            symbol        = body.symbol,
            exchange      = body.exchange_segment,
            direction     = body.transaction_type.upper(),
            quantity      = body.quantity,
            order_type    = body.order_type.upper(),
            product       = body.product_type.upper(),
            price         = body.price if body.order_type == "LIMIT" else 0,
            trigger_price = body.trigger_price,
        )
        response = await adapter.place_order(order)
        if response.status == "FAILED":
            raise HTTPException(status_code=502, detail=response.message)
        return {
            "status":           "placed",
            "order_id":         response.broker_order_id,
            "symbol":           body.symbol,
            "transaction_type": body.transaction_type,
            "quantity":         body.quantity,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Order failed: {str(e)}")


class ManualOrderRequest(BaseModel):
    symbol:           str
    security_id:      str
    exchange_segment: str   = "NSE_EQ"
    transaction_type: str
    quantity:         int
    order_type:       str   = "MARKET"
    product_type:     str   = "INTRADAY"
    price:            float = 0.0
    trigger_price:    float = 0.0


@router.post("/order")
async def place_manual_order(
    body: ManualOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Place a manual BUY/SELL order via Dhan."""
    from app.broker.factory import get_broker_adapter
    from app.broker.base import OrderRequest
    from app.models.broker import BrokerAccount, BrokerName
    from sqlalchemy import select

    result = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.user_id       == current_user.id,
            BrokerAccount.broker        == BrokerName.dhan,
            BrokerAccount.paper_trading == False,
            BrokerAccount.is_active     == True,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=400, detail="No active Dhan live account")

    try:
        adapter  = get_broker_adapter(account)
        order    = OrderRequest(
            symbol        = body.symbol,
            exchange      = body.exchange_segment,
            direction     = body.transaction_type.upper(),
            quantity      = body.quantity,
            order_type    = body.order_type.upper(),
            product       = body.product_type.upper(),
            price         = body.price if body.order_type == "LIMIT" else 0,
            trigger_price = body.trigger_price,
        )
        response = await adapter.place_order(order)
        if response.status == "FAILED":
            raise HTTPException(status_code=502, detail=response.message)
        return {
            "status":           "placed",
            "order_id":         response.broker_order_id,
            "symbol":           body.symbol,
            "transaction_type": body.transaction_type,
            "quantity":         body.quantity,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Order failed: {str(e)}")
