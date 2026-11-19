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
from app.models.broker import BrokerAccount, BrokerName
from app.broker.factory import get_broker_adapter
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
    live_rows = await db.execute(
        select(TerminalRow).where(
            TerminalRow.owner_id == current_user.id,
            TerminalRow.is_active == True,
            TerminalRow.trade_mode == "REAL",
        )
    )
    if live_rows.scalars().first():
        from app.core.trading_mode import LiveTradingError, assert_live_allowed, require_not_killed
        try:
            assert_live_allowed()
            await require_not_killed()
        except LiveTradingError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
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
    if payload.target_formula is not None: row.target_formula = payload.target_formula
    if payload.sl_formula     is not None: row.sl_formula     = payload.sl_formula
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
        "target_formula": row.target_formula,
        "sl_formula":    row.sl_formula,
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


COLUMN_PRESETS = [
    {"name": "TREND", "formula": '=IF((high+low+close)/3>ltp,"DOWN","UP")', "colors": '{"UP":"green","DOWN":"red"}'},
    {"name": "HCG", "formula": "=(high+close)/2", "colors": "{}"},
    {"name": "OCG", "formula": "=(open+close)/2", "colors": "{}"},
    {"name": "LCG", "formula": "=(low+close)/2", "colors": "{}"},
    {"name": "KD", "formula": "=-(ltp-low)/(low-high)*100", "colors": "{}"},
    {"name": "GANN", "formula": "=(high+low)/2", "colors": "{}"},
    {"name": "SIGNAL", "formula": '=IF(ltp>open,"BUY","SELL")', "colors": '{"BUY":"green","SELL":"red"}'},
    {"name": "SSIG", "formula": '=IFERROR(IF(AND(open>close,ltp>open),"BUY",IF(AND(open<close,ltp<open),"SELL","")),"")', "colors": '{"BUY":"green","SELL":"red"}'},
    {"name": "ENTRY", "formula": '=IF(AND(open=0,high=0,low=0)," ",IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0),IF(signal="SELL",ROUND(((SQRT(open)-0.015)^2),0)," ")))', "colors": "{}"},
    {"name": "SL", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)-(ROUND(((SQRT(open)+0.015)^2),0)*0.5%),ROUND(((SQRT(open)-0.015)^2),0)+(ROUND(((SQRT(open)-0.015)^2),0)*0.5%))', "colors": "{}"},
    {"name": "T11.8", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.118%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.118%))', "colors": "{}"},
    {"name": "T23.8", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.238%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.238%))', "colors": "{}"},
    {"name": "T38.2", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.382%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.382%))', "colors": "{}"},
    {"name": "T50", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.5%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.5%))', "colors": "{}"},
    {"name": "T61.8", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.618%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.618%))', "colors": "{}"},
    {"name": "T78.6", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.786%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.786%))', "colors": "{}"},
    {"name": "T100", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*1%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*1%))', "colors": "{}"},
    {"name": "T1.618", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*1.618%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*1.618%))', "colors": "{}"},
    {"name": "T2.618", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*2.618%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*2.618%))', "colors": "{}"},
]


def is_option_symbol(symbol: str, segment: Optional[str] = None) -> bool:
    """Robust detection for options and futures contracts."""
    s_upper = (symbol or "").upper().strip()
    seg_upper = (segment or "").upper().strip()
    if seg_upper in ("NSE_FNO", "NFO", "BSE_FNO", "BFO", "MCX", "OPTIDX", "OPTSTK", "FUTIDX", "FUTSTK"):
        return True
    if seg_upper in ("NSE_EQ", "BSE_EQ", "EQ"):
        return False
    import re
    if re.search(r'\b(CALL|PUT|CE|PE|FUT|OPT)\b', s_upper):
        return True
    if re.search(r'\d+\s*(CE|PE|CALL|PUT)\b', s_upper):
        return True
    return False


@router.get("/column-batches")
async def list_column_batches(current_user: User = Depends(get_current_user)):
    """List available formula batches."""
    from app.models.terminal_column import FIBONACCI_FORMULA_COLUMNS
    return [
        {"id": "fibonacci", "name": "Fibonacci Formula", "description": "19 Fibonacci percentage target & strategy formulas", "columns": len(FIBONACCI_FORMULA_COLUMNS)},
    ]


@router.get("/column-presets")
async def list_column_presets(
    book: str = "equity",
    batch: str = "fibonacci",
    current_user: User = Depends(require_admin),
):
    """House column templates by batch. Admin only."""
    from app.strategy.excel_formula_engine import formula_for_book

    if book not in ("equity", "option", "mcx"):
        raise HTTPException(status_code=400, detail="book must be equity, option, or mcx")

    return [
        {**preset, "formula": formula_for_book(preset["name"], preset["formula"], book)}
        for preset in COLUMN_PRESETS
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
    book:        str   = "equity"       # equity, option, or mcx; market columns are shared


class ColumnValueTick(BaseModel):
    symbol: str
    ltp: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    oi: Optional[float] = None
    vwap: Optional[float] = None
    atp: Optional[float] = None
    p_close: Optional[float] = None
    p_high: Optional[float] = None
    p_low: Optional[float] = None


class ColumnValueRequest(BaseModel):
    ticks: list[ColumnValueTick] = []
    book: str = "equity"


async def _column_for_editor(db: AsyncSession, col_id: str, current_user: User):
    """Admins and traders share columns; looks up by UUID or column key/name."""
    from app.models.terminal_column import TerminalColumn, DEFAULT_COLUMNS
    import uuid

    col = None
    try:
        uid = uuid.UUID(str(col_id))
        result = await db.execute(select(TerminalColumn).where(TerminalColumn.id == uid))
        col = result.scalar_one_or_none()
    except (ValueError, TypeError):
        pass

    if not col:
        result = await db.execute(
            select(TerminalColumn).where(
                (TerminalColumn.col_key == str(col_id).lower()) |
                (TerminalColumn.name == str(col_id).upper())
            )
        )
        col = result.scalars().first()

    if not col:
        # Create from DEFAULT_COLUMNS if matching default column definition
        target_def = next((d for d in DEFAULT_COLUMNS if d["col_key"] == str(col_id).lower() or d["name"] == str(col_id).upper()), None)
        if target_def:
            col = TerminalColumn(
                user_id=current_user.id,
                name=target_def["name"],
                col_key=target_def["col_key"],
                col_type=target_def["col_type"],
                formula=target_def.get("formula"),
                col_order=target_def["col_order"],
                width=target_def["width"],
                is_visible=True,
                color_rules=target_def.get("color_rules"),
                book="shared",
            )
            db.add(col)
            await db.commit()
            await db.refresh(col)

    if not col:
        raise HTTPException(status_code=404, detail="Column not found")
    return col


async def _shared_columns(db: AsyncSession, current_user: User):
    """Column definitions belong to admin accounts so every terminal shows the same set."""
    from app.models.terminal_column import TerminalColumn, DEFAULT_COLUMNS
    from sqlalchemy import delete as sa_delete

    # Remove any obsolete p_close columns
    await db.execute(
        sa_delete(TerminalColumn).where(
            (TerminalColumn.col_key == "p_close") | (TerminalColumn.name == "P.CLOSE") | (TerminalColumn.name == "PREV CLOSE")
        )
    )
    await db.commit()

    admins = await db.execute(
        select(User.id).where(User.role == UserRole.admin).order_by(User.created_at)
    )
    admin_ids = [row[0] for row in admins.all()]
    cols = []
    if admin_ids:
        # Use primary admin's columns or deduplicate across admins
        result = await db.execute(
            select(TerminalColumn)
            .where(TerminalColumn.user_id.in_(admin_ids))
            .order_by(TerminalColumn.col_order)
        )
        cols = list(result.scalars().all())

    if cols:
        existing_keys = {c.col_key for c in cols if c.col_key}
        owner_id = cols[0].user_id
        added = False
        for d in DEFAULT_COLUMNS:
            if d.get("col_key") and d["col_key"] not in existing_keys:
                db.add(TerminalColumn(
                    user_id=owner_id,
                    name=d["name"],
                    col_key=d["col_key"],
                    col_type=d["col_type"],
                    formula=d.get("formula"),
                    col_order=d["col_order"],
                    width=d["width"],
                    is_visible=d.get("is_visible", True),
                    color_rules=d.get("color_rules"),
                    book="shared",
                ))
                added = True
        if added:
            await db.commit()
            result = await db.execute(
                select(TerminalColumn)
                .where(TerminalColumn.user_id.in_(admin_ids) if admin_ids else TerminalColumn.user_id == owner_id)
                .order_by(TerminalColumn.col_order)
            )
            cols = list(result.scalars().all())

    if not cols:
        owner_id = admin_ids[0] if admin_ids else current_user.id
        for d in DEFAULT_COLUMNS:
            db.add(TerminalColumn(
                user_id=owner_id,
                name=d["name"],
                col_key=d["col_key"],
                col_type=d["col_type"],
                formula=d.get("formula"),
                col_order=d["col_order"],
                width=d["width"],
                is_visible=d.get("is_visible", True),
                color_rules=d["color_rules"],
                book="shared",
            ))
        await db.commit()
        result = await db.execute(
            select(TerminalColumn)
            .where(TerminalColumn.user_id == owner_id)
            .order_by(TerminalColumn.col_order)
        )
        cols = list(result.scalars().all())

    cols = await _ensure_book_formulas(db, cols)

    # Strictly deduplicate columns by (key/name, book) to prevent duplicate columns in table
    seen = set()
    deduped = []
    for c in cols:
        k = ((c.col_key or c.name).lower().strip(), (c.book or "shared").lower().strip())
        if k not in seen:
            seen.add(k)
            deduped.append(c)
    return deduped


async def _ensure_book_formulas(db: AsyncSession, cols: list):
    """Ensure options and mcx books have their own independent copies of formulas."""
    from app.models.terminal_column import TerminalColumn
    from app.strategy.excel_formula_engine import formula_for_book

    equity = [col for col in cols if col.formula and (col.book or "equity") == "equity"]
    to_add = []
    for target_book in ("option", "mcx"):
        existing_names = {col.name.upper() for col in cols if (col.book or "").lower() == target_book}
        for src in equity:
            if src.name.upper() not in existing_names:
                to_add.append(TerminalColumn(
                    user_id=src.user_id,
                    name=src.name,
                    col_key=src.col_key,
                    col_type=src.col_type,
                    formula=formula_for_book(src.name, src.formula, target_book),
                    col_order=src.col_order,
                    width=src.width,
                    is_visible=src.is_visible,
                    color_rules=src.color_rules,
                    book=target_book,
                ))
                existing_names.add(src.name.upper())

    if to_add:
        for item in to_add:
            db.add(item)
        await db.commit()
        owner_ids = {col.user_id for col in cols}
        result = await db.execute(
            select(TerminalColumn)
            .where(TerminalColumn.user_id.in_(owner_ids))
            .order_by(TerminalColumn.col_order)
        )
        cols = list(result.scalars().all())

    # Strictly deduplicate before returning
    seen = set()
    deduped = []
    for c in cols:
        k = ((c.col_key or c.name).lower().strip(), (c.book or "shared").lower().strip())
        if k not in seen:
            seen.add(k)
            deduped.append(c)
    return deduped


@router.post("/column-values")
async def column_values(
    payload: ColumnValueRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate the saved formulas for one book. Equity, options, and MCX are stored separately."""
    from app.strategy.excel_formula_engine import evaluate_columns_in_order

    book = payload.book if payload.book in ("equity", "option", "mcx") else "equity"
    cols = await _shared_columns(db, current_user)
    formulas = []
    for col in cols:
        if not col.formula or (col.book or "equity") != book:
            continue
        formulas.append({"name": col.name, "formula": col.formula})
    values: dict[str, dict] = {}
    for tick in payload.ticks:
        data = {
            key: val for key, val in tick.model_dump().items()
            if key != "symbol" and val is not None
        }
        raw = evaluate_columns_in_order(formulas, data)
        named = {}
        for col in formulas:
            key = col["name"].lower()
            if key in raw:
                named[col["name"]] = raw[key]
        values[tick.symbol] = named
    return {"values": values}


@router.get("/columns")
async def list_columns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Shared install columns. Formula text is included only for an admin."""
    from app.models.terminal_column import DEFAULT_COLUMNS

    cols = await _shared_columns(db, current_user)
    is_admin = current_user.role == UserRole.admin
    if cols:
        return [
            {
                "id":          str(col.id),
                "name":        col.name,
                "col_key":     col.col_key,
                "col_type":    col.col_type,
                "formula":     col.formula if is_admin else None,
                "col_order":   col.col_order,
                "width":       col.width,
                "is_visible":  col.is_visible,
                "color_rules": col.color_rules,
                "book":        col.book or "equity",
            }
            for col in cols
        ]
    return [
        {
            "id":          d["col_key"],
            "name":        d["name"],
            "col_key":     d["col_key"],
            "col_type":    d["col_type"],
            "formula":     None,
            "col_order":   d["col_order"],
            "width":       d["width"],
            "is_visible":  True,
            "color_rules": d["color_rules"],
            "book":        "shared",
        }
        for d in DEFAULT_COLUMNS
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
    if payload.book not in ("equity", "option", "mcx"):
        raise HTTPException(status_code=400, detail="book must be equity, option, or mcx")

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
        book        = payload.book,
    )
    db.add(col)
    await db.commit()
    await db.refresh(col)
    return {"id": str(col.id), "name": col.name, "validated": msg}


@router.patch("/columns/{col_id}/visibility")
async def toggle_column_visibility(
    col_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Show or hide a shared column. Any admin can change a column owned by another admin."""
    col = await _column_for_editor(db, col_id, current_user)

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

    col = await _column_for_editor(db, col_id, current_user)

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
    if (col.book or "equity") in ("equity", "option", "mcx") and payload.book in ("equity", "option", "mcx"):
        col.book = payload.book
    await db.commit()
    return {"status": "updated", "name": col.name}


@router.delete("/columns/{col_id}", status_code=204)
async def delete_column(
    col_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a shared column. Any admin can remove a column owned by another admin."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    col = await _column_for_editor(db, col_id, current_user)

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
            is_visible  = d.get("is_visible", True),
            color_rules = d.get("color_rules"),
            book        = "shared",
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


# ── Column Reordering ────────────────────────────────────────────────────────

class ColumnOrderItem(BaseModel):
    id: str
    col_order: int


class ColumnReorderRequest(BaseModel):
    orders: list[ColumnOrderItem]


@router.post("/columns/reorder")
async def reorder_columns(
    payload: ColumnReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update display order of terminal columns."""
    from app.models.terminal_column import TerminalColumn
    from sqlalchemy import select
    import uuid

    for item in payload.orders:
        col = None
        try:
            uid = uuid.UUID(str(item.id))
            result = await db.execute(select(TerminalColumn).where(TerminalColumn.id == uid))
            col = result.scalar_one_or_none()
        except (ValueError, TypeError):
            pass

        if not col:
            result = await db.execute(
                select(TerminalColumn).where(
                    (TerminalColumn.col_key == str(item.id).lower()) |
                    (TerminalColumn.name == str(item.id).upper())
                )
            )
            col = result.scalars().first()

        if not col:
            col = await _column_for_editor(db, item.id, current_user)

        if col:
            col.col_order = item.col_order

    await db.commit()
    return {"status": "ok", "updated": len(payload.orders)}


# ── Batch Switching & Presets ───────────────────────────────────────────────

class ApplyBatchRequest(BaseModel):
    batch: str = "Fibonacci Formula"
    book: str = "all"  # "equity", "option", "mcx", "algo", "both", or "all"


_user_batch_presets: dict[str, dict[str, str]] = {}


async def _get_batch_presets(user_id: UUID) -> dict[str, str]:
    defaults = {"equity": "fibonacci", "option": "fibonacci", "mcx": "fibonacci", "algo": "fibonacci"}
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        data = await r.hgetall(f"batch_presets:{user_id}")
        await r.aclose()
        if data:
            return {**defaults, **data}
    except Exception:
        pass
    return _user_batch_presets.get(str(user_id), defaults)


async def _save_batch_preset(user_id: UUID, book: str, batch: str):
    b_key = "fibonacci"
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        if book == "all":
            await r.hset(f"batch_presets:{user_id}", mapping={"equity": b_key, "option": b_key, "mcx": b_key})
        elif book == "both":
            await r.hset(f"batch_presets:{user_id}", mapping={"equity": b_key, "option": b_key})
        else:
            await r.hset(f"batch_presets:{user_id}", book, b_key)
        await r.aclose()
    except Exception:
        pass
    curr = _user_batch_presets.setdefault(str(user_id), {"equity": "fibonacci", "option": "fibonacci", "mcx": "fibonacci", "algo": "fibonacci"})
    if book == "all":
        curr["equity"] = b_key
        curr["option"] = b_key
        curr["mcx"] = b_key
    elif book == "both":
        curr["equity"] = b_key
        curr["option"] = b_key
    else:
        curr[book] = b_key


@router.get("/batch-presets")
async def get_batch_presets(
    current_user: User = Depends(get_current_user),
):
    """Return active formula batch for equity, option, and algo window."""
    return await _get_batch_presets(current_user.id)


@router.post("/columns/apply-batch")
async def apply_formula_batch(
    payload: ApplyBatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Apply Fibonacci Formula batch across terminal tables or algo window.
    """
    batch_key = "fibonacci"

    # If applying to algo window only, persist preference and return (available to all users)
    if payload.book == "algo":
        await _save_batch_preset(current_user.id, "algo", payload.batch)
        return {"status": "ok", "applied_batch": batch_key, "book": "algo"}

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from sqlalchemy import delete as sa_delete
    from app.models.terminal_column import (
        TerminalColumn,
        DEFAULT_COLUMNS,
        FIBONACCI_FORMULA_COLUMNS,
    )
    from app.strategy.excel_formula_engine import formula_for_book

    if payload.book == "all":
        books = ["equity", "option", "mcx"]
    elif payload.book == "both":
        books = ["equity", "option"]
    else:
        books = [payload.book]

    await _save_batch_preset(current_user.id, payload.book, payload.batch)

    # Clear existing columns strictly for target books to ensure watchlists stay independent
    for b in books:
        target_books = [b, "shared"] if payload.book in ("all", "both") else [b]
        await db.execute(
            sa_delete(TerminalColumn).where(
                TerminalColumn.user_id == current_user.id,
                TerminalColumn.book.in_(target_books),
            )
        )

    # Apply Fibonacci Formula batch: Default columns + Fibonacci strategy formulas
    for b in books:
        for d in DEFAULT_COLUMNS:
            db.add(TerminalColumn(
                user_id     = current_user.id,
                name        = d["name"],
                col_key     = d["col_key"],
                col_type    = d["col_type"],
                col_order   = d["col_order"],
                width       = d["width"],
                is_visible  = d.get("is_visible", True),
                color_rules = d.get("color_rules"),
                book        = b,
            ))
        for d in FIBONACCI_FORMULA_COLUMNS:
            formula_text = formula_for_book(d["name"], d["formula"], b)
            db.add(TerminalColumn(
                user_id     = current_user.id,
                name        = d["name"],
                col_key     = d.get("col_key") or d["name"].lower(),
                col_type    = "custom",
                formula     = formula_text,
                col_order   = d["col_order"],
                width       = d.get("width", 80),
                is_visible  = True,
                color_rules = d.get("color_rules"),
                book        = b,
            ))

    await db.commit()
    return {"status": "ok", "applied_batch": batch_key, "books": books}


# ── BSA Algo Window Routes ───────────────────────────────────────────────────

class BsaAlgoRowCreate(BaseModel):
    symbol:           str
    exchange:         str = "NSE"
    segment:          str = "NSE_EQ"
    token:            Optional[str] = None
    quantity:         int = 1
    number_of_trades: int = 1
    target_type:      str = "T1"
    custom_target:    Optional[float] = None
    trade_mode:       Optional[str] = "FULL"      # FULL, BUY_ONLY, SELL_ONLY
    entry_type:       Optional[str] = "FORMULA"   # FORMULA, CUSTOM
    custom_entry:     Optional[float] = None
    buy_price:        Optional[float] = None
    status:           Optional[str] = None


class BsaAlgoRowUpdate(BaseModel):
    is_algo_active:   Optional[bool] = None
    quantity:         Optional[int] = None
    number_of_trades: Optional[int] = None
    target_type:      Optional[str] = None
    custom_target:    Optional[float] = None
    sell_tgt:         Optional[float] = None
    trade_mode:       Optional[str] = None
    entry_type:       Optional[str] = None
    custom_entry:     Optional[float] = None
    buy_price:        Optional[float] = None
    status:           Optional[str] = None


class BsaManualOrderPayload(BaseModel):
    side:       str  # BUY or SELL
    quantity:   Optional[int] = None
    price:      Optional[float] = None


@router.get("/algo-rows")
async def list_algo_rows(
    batch: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all scripts in the Algo Trading Window for current user,
    enriched with live market data and Fibonacci formula calculations.
    """
    import math
    from app.models.algo_row import BsaAlgoRow
    from app.market.market_poller import get_poller
    from app.strategy.excel_formula_engine import evaluate_columns_in_order, formula_for_book
    from app.models.terminal_column import FIBONACCI_FORMULA_COLUMNS

    result = await db.execute(
        select(BsaAlgoRow)
        .where(BsaAlgoRow.user_id == current_user.id)
        .order_by(BsaAlgoRow.created_at)
    )
    rows = result.scalars().all()

    poller = get_poller()
    cached_quotes = {t["symbol"]: t for t in (poller._last_data or [])}

    out = []
    for r in rows:
        live = cached_quotes.get(r.symbol, {})
        ltp = float(live.get("ltp") or r.buy_price or 0)
        is_option = is_option_symbol(r.symbol, r.segment if r.segment != "NSE_EQ" else None)

        # Compute live formula outputs
        tick_data = {
            "symbol":  r.symbol,
            "ltp":     ltp,
            "open":    live.get("open"),
            "high":    live.get("high"),
            "low":     live.get("low"),
            "close":   live.get("close"),
            "volume":  live.get("volume"),
            "vwap":    live.get("vwap") or live.get("atp"),
            "p_close": live.get("p_close") or live.get("prev_close") or live.get("close"),
            "p_high":  live.get("p_high") or live.get("high"),
            "p_low":   live.get("p_low") or live.get("low"),
        }
        open_val = float(tick_data["open"] or ltp or 100.0)

        fib_cols = [
            {**c, "formula": formula_for_book(c["name"], c["formula"], "option" if is_option else "equity")}
            for c in FIBONACCI_FORMULA_COLUMNS
        ]

        fib_vals = evaluate_columns_in_order(fib_cols, tick_data)
        sig = str(fib_vals.get("signal") or fib_vals.get("ssig") or "BUY").upper()
        ent = fib_vals.get("entry") or round((math.sqrt(open_val) + (0.015 if sig == "BUY" else -0.015))**2, 2)
        sl_val = fib_vals.get("sl") or round(ent * (0.995 if sig == "BUY" else 1.005), 2)
        t1 = fib_vals.get("t11.8") or fib_vals.get("t11_8")
        t2 = fib_vals.get("t23.8") or fib_vals.get("t23_8")
        t3 = fib_vals.get("t38.2") or fib_vals.get("t38_2")
        t4 = fib_vals.get("t50")
        t5 = fib_vals.get("t61.8") or fib_vals.get("t61_8")
        t6 = fib_vals.get("t78.6") or fib_vals.get("t78_6")
        t7 = fib_vals.get("t100")
        t8 = fib_vals.get("t1.618") or fib_vals.get("t1_618")
        t9 = fib_vals.get("t2.618") or fib_vals.get("t2_618")

        target_map = {
            "T1":     t1,
            "T11.8":  t1,
            "T11_8":  t1,
            "TGT1":   t1,
            "T2":     t2,
            "T23.8":  t2,
            "T23_8":  t2,
            "TGT2":   t2,
            "T3":     t3,
            "T38.2":  t3,
            "T38_2":  t3,
            "TGT3":   t3,
            "T4":     t4,
            "T50":    t4,
            "T5":     t5,
            "T61.8":  t5,
            "T61_8":  t5,
            "T6":     t6,
            "T78.6":  t6,
            "T78_6":  t6,
            "T7":     t7,
            "T100":   t7,
            "T8":     t8,
            "T1.618": t8,
            "T1_618": t8,
            "T9":     t9,
            "T2.618": t9,
            "T2_618": t9,
        }
        if r.target_type == "CUSTOM" and r.custom_target and r.custom_target > 0:
            active_target = float(r.custom_target)
        else:
            active_target = target_map.get((r.target_type or "T1").upper(), t1)

        display_sell_tgt = r.sell_tgt if (r.status == "IN_POSITION" and r.sell_tgt) else active_target

        # Active buy entry price calculation (FORMULA, T1-T9, or CUSTOM)
        entry_type_upper = (r.entry_type or "FORMULA").upper().strip()
        if entry_type_upper == "CUSTOM" and r.custom_entry and r.custom_entry > 0:
            active_entry_price = float(r.custom_entry)
        elif entry_type_upper in target_map:
            active_entry_price = float(target_map.get(entry_type_upper) or ent)
        else:
            active_entry_price = ent

        # Current trade PnL
        live_pnl = r.pnl
        if r.status == "IN_POSITION" and r.buy_price and ltp > 0:
            live_pnl = round((ltp - r.buy_price) * r.quantity, 2)

        out.append({
            "id":               str(r.id),
            "symbol":           r.symbol,
            "exchange":         r.exchange,
            "segment":          r.segment,
            "token":            r.token,
            "is_algo_active":   r.is_algo_active,
            "quantity":         r.quantity,
            "number_of_trades": r.number_of_trades,
            "trades_completed": r.trades_completed,
            "status":           r.status,
            "buy_price":        r.buy_price,
            "sell_tgt":         display_sell_tgt,
            "stop_loss":        r.stop_loss,
            "entry_level":      r.entry_level,
            "target_type":      r.target_type or "T1",
            "custom_target":    r.custom_target,
            "trade_mode":       r.trade_mode or "FULL",
            "entry_type":       r.entry_type or "FORMULA",
            "custom_entry":     r.custom_entry,
            "buy_entry_price":  active_entry_price,
            "pnl":              live_pnl,
            "ltp":              ltp if ltp > 0 else None,
            "p_close":          tick_data.get("p_close"),
            "chg_pct":          round(((ltp - float(tick_data.get("p_close")))/float(tick_data.get("p_close")))*100, 2) if (tick_data.get("p_close") and ltp > 0) else None,
            "signal":           sig,
            "entry":            ent,
            "sl":               sl_val,
            "t1":               t1,
            "t2":               t2,
            "t3":               t3,
            "t4":               t4,
            "t5":               t5,
            "t6":               t6,
            "t7":               t7,
            "t8":               t8,
            "t9":               t9,
            "t11_8":            t1,
            "t23_8":            t2,
            "t38_2":            t3,
            "t50":              t4,
            "t61_8":            t5,
            "t78_6":            t6,
            "t100":             t7,
            "t1_618":           t8,
            "t2_618":           t9,
        })
    return out


@router.post("/algo-rows")
async def add_algo_row(
    payload: BsaAlgoRowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a symbol to the Algo Trading Window (e.g. from Equity/Options table '+ ALGO' button).
    """
    from app.models.algo_row import BsaAlgoRow
    from app.market.market_poller import get_poller

    sym = payload.symbol.upper().strip()
    is_opt = is_option_symbol(sym, payload.segment if payload.segment != "NSE_EQ" else None)
    target_seg = "NSE_FNO" if is_opt else (payload.segment or "NSE_EQ")
    target_exch = "NFO" if is_opt else (payload.exchange or "NSE")

    # Check existing row
    res = await db.execute(
        select(BsaAlgoRow).where(
            BsaAlgoRow.user_id == current_user.id,
            BsaAlgoRow.symbol == sym,
        )
    )
    existing = res.scalars().first()
    if existing:
        return {"status": "exists", "id": str(existing.id), "symbol": existing.symbol}

    # Ensure symbol is watched in market poller
    poller = get_poller()
    if payload.token:
        poller.add_symbol(sym, payload.token, target_seg)

    new_row = BsaAlgoRow(
        user_id           = current_user.id,
        symbol            = sym,
        exchange          = target_exch,
        segment           = target_seg,
        token             = payload.token,
        quantity          = max(1, payload.quantity),
        number_of_trades  = max(1, min(5, payload.number_of_trades)),
        is_algo_active    = False,  # Default to ALGO OFF (manual mode)
        status            = payload.status or ("IN_POSITION" if payload.trade_mode == "SELL_ONLY" else "IDLE"),
        target_type       = payload.target_type or "T1",
        custom_target     = payload.custom_target,
        trade_mode        = payload.trade_mode or "FULL",
        entry_type        = payload.entry_type or "FORMULA",
        custom_entry      = payload.custom_entry,
        buy_price         = payload.buy_price,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    return {"status": "created", "id": str(new_row.id), "symbol": new_row.symbol}


@router.patch("/algo-rows/{row_id}")
async def update_algo_row(
    row_id: UUID,
    payload: BsaAlgoRowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update settings for an algo row: toggle ALGO ON/OFF, quantity, trades (1-5), target type (acting as kill switch)."""
    from app.models.algo_row import BsaAlgoRow

    row = await db.get(BsaAlgoRow, row_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Algo row not found")

    if payload.is_algo_active is not None:
        row.is_algo_active = payload.is_algo_active
        if payload.is_algo_active and row.status in ("COMPLETED", "STOPPED_SL"):
            row.status = "IDLE"
            row.trades_completed = 0

    if payload.quantity is not None:
        row.quantity = max(1, payload.quantity)

    if payload.number_of_trades is not None:
        # Strictly enforce 1 to 5 only
        row.number_of_trades = max(1, min(5, payload.number_of_trades))

    if payload.target_type is not None:
        tt = payload.target_type.upper().strip()
        if tt in ("KILL", "EXIT_NOW", "STOP"):
            # Instant Kill Switch: exit position immediately and turn off automated trading
            row.is_algo_active = False
            if row.status == "IN_POSITION":
                from app.services.bsa_algo_engine import algo_engine
                from app.market.market_poller import get_poller
                poller = get_poller()
                live = next((t for t in (poller._last_data or []) if t.get("symbol") == row.symbol), {})
                ltp = float(live.get("ltp") or row.buy_price or 0.0)
                exit_fill = await algo_engine._execute_order(row, side="SELL", price=ltp, db=db)
                if exit_fill:
                    row.trades_completed += 1
                    if row.buy_price:
                        row.pnl = round((exit_fill - row.buy_price) * row.quantity, 2)
                    row.status = "COMPLETED"
            else:
                row.status = "IDLE"
        elif tt == "CUSTOM":
            row.target_type = "CUSTOM"
            if payload.custom_target is not None:
                row.custom_target = payload.custom_target
                row.sell_tgt = payload.custom_target
            elif payload.sell_tgt is not None:
                row.custom_target = payload.sell_tgt
                row.sell_tgt = payload.sell_tgt
        else:
            row.target_type = payload.target_type
            # Dynamically recalculate and update sell_tgt based on the new target selection
            from app.market.market_poller import get_poller
            from app.strategy.excel_formula_engine import evaluate_columns_in_order, formula_for_book
            from app.models.terminal_column import FIBONACCI_FORMULA_COLUMNS
            poller = get_poller()
            live = next((t for t in (poller._last_data or []) if t.get("symbol") == row.symbol), {})
            ltp = float(live.get("ltp") or row.buy_price or 0.0)
            tick_data = {
                "symbol": row.symbol, "ltp": ltp,
                "open": live.get("open") or ltp, "high": live.get("high") or ltp,
                "low": live.get("low") or ltp, "close": live.get("close") or ltp,
                "p_close": live.get("p_close") or live.get("close") or ltp,
                "p_high": live.get("p_high") or live.get("high") or ltp,
                "p_low": live.get("p_low") or live.get("low") or ltp,
            }
            is_opt = is_option_symbol(row.symbol, row.segment if row.segment != "NSE_EQ" else None)
            fib_cols = [
                {**c, "formula": formula_for_book(c["name"], c["formula"], "option" if is_opt else "equity")}
                for c in FIBONACCI_FORMULA_COLUMNS
            ]
            fib_vals = evaluate_columns_in_order(fib_cols, tick_data)
            t1 = float(fib_vals.get("t11.8") or fib_vals.get("t11_8") or 0)
            t2 = float(fib_vals.get("t23.8") or fib_vals.get("t23_8") or 0)
            t3 = float(fib_vals.get("t38.2") or fib_vals.get("t38_2") or 0)
            t4 = float(fib_vals.get("t50") or 0)
            t5 = float(fib_vals.get("t61.8") or fib_vals.get("t61_8") or 0)
            t6 = float(fib_vals.get("t78.6") or fib_vals.get("t78_6") or 0)
            t7 = float(fib_vals.get("t100") or 0)
            t8 = float(fib_vals.get("t1.618") or fib_vals.get("t1_618") or 0)
            t9 = float(fib_vals.get("t2.618") or fib_vals.get("t2_618") or 0)
            target_map = {
                "T1":     t1,
                "T11.8":  t1,
                "T11_8":  t1,
                "TGT1":   t1,
                "T2":     t2,
                "T23.8":  t2,
                "T23_8":  t2,
                "TGT2":   t2,
                "T3":     t3,
                "T38.2":  t3,
                "T38_2":  t3,
                "TGT3":   t3,
                "T4":     t4,
                "T50":    t4,
                "T5":     t5,
                "T61.8":  t5,
                "T61_8":  t5,
                "T6":     t6,
                "T78.6":  t6,
                "T78_6":  t6,
                "T7":     t7,
                "T100":   t7,
                "T8":     t8,
                "T1.618": t8,
                "T1_618": t8,
                "T9":     t9,
                "T2.618": t9,
                "T2_618": t9,
                "CUSTOM": float(row.custom_target or row.sell_tgt or 0),
            }
            new_tgt = target_map.get(payload.target_type.upper())
            if new_tgt and new_tgt > 0:
                row.sell_tgt = new_tgt

            # If in position and market price already exceeds the newly chosen target, exit immediately!
            if row.status == "IN_POSITION" and row.sell_tgt and ltp >= row.sell_tgt:
                from app.services.bsa_algo_engine import algo_engine
                exit_fill = await algo_engine._execute_order(row, side="SELL", price=ltp, db=db)
                if exit_fill:
                    row.trades_completed += 1
                    if row.buy_price:
                        row.pnl = round((exit_fill - row.buy_price) * row.quantity, 2)
                    if row.trades_completed >= row.number_of_trades:
                        row.status = "COMPLETED"
                        row.is_algo_active = False
                    else:
                        row.status = "WAITING_RETURN"

    if payload.custom_target is not None:
        row.custom_target = payload.custom_target
        if row.target_type == "CUSTOM":
            row.sell_tgt = payload.custom_target

    if payload.sell_tgt is not None:
        row.sell_tgt = payload.sell_tgt
        if row.target_type == "CUSTOM":
            row.custom_target = payload.sell_tgt

    if payload.trade_mode is not None:
        row.trade_mode = payload.trade_mode
        if payload.trade_mode == "SELL_ONLY" and row.status == "IDLE":
            row.status = "IN_POSITION"

    if payload.entry_type is not None:
        row.entry_type = payload.entry_type

    if payload.custom_entry is not None:
        row.custom_entry = payload.custom_entry

    if payload.buy_price is not None:
        row.buy_price = payload.buy_price

    if payload.status is not None:
        row.status = payload.status

    await db.commit()
    return {"status": "updated", "id": str(row.id), "is_algo_active": row.is_algo_active, "target_type": row.target_type, "sell_tgt": row.sell_tgt}


@router.post("/algo-rows/{row_id}/kill")
async def kill_algo_row(
    row_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Emergency Kill Switch: instantly exits any open position at market price
    and deactivates automated trading.
    """
    from app.models.algo_row import BsaAlgoRow
    from app.services.bsa_algo_engine import algo_engine
    from app.market.market_poller import get_poller

    row = await db.get(BsaAlgoRow, row_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Algo row not found")

    poller = get_poller()
    live = next((t for t in (poller._last_data or []) if t.get("symbol") == row.symbol), {})
    ltp = float(live.get("ltp") or row.buy_price or 0.0)

    row.is_algo_active = False

    if row.status == "IN_POSITION":
        exit_fill = await algo_engine._execute_order(row, side="SELL", price=ltp, db=db)
        if exit_fill:
            row.trades_completed += 1
            if row.buy_price:
                row.pnl = round((exit_fill - row.buy_price) * row.quantity, 2)
            row.status = "COMPLETED"
    else:
        row.status = "IDLE"

    await db.commit()
    return {"status": "killed", "id": str(row.id), "symbol": row.symbol, "is_algo_active": False}


@router.delete("/algo-rows/{row_id}")
async def delete_algo_row(
    row_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a script from the Algo Trading Window."""
    from app.models.algo_row import BsaAlgoRow

    row = await db.get(BsaAlgoRow, row_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Algo row not found")

    await db.delete(row)
    await db.commit()
    return {"status": "deleted", "id": str(row_id)}


@router.post("/algo-rows/{row_id}/reset")
async def reset_algo_row(
    row_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset trade cycle counter and levels for an algo script."""
    from app.models.algo_row import BsaAlgoRow

    row = await db.get(BsaAlgoRow, row_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Algo row not found")

    row.trades_completed = 0
    row.status           = "IDLE"
    row.buy_price        = None
    row.sell_tgt         = None
    row.stop_loss        = None
    row.pnl              = 0.0
    row.last_order_id    = None
    await db.commit()
    return {"status": "reset", "id": str(row.id)}


@router.post("/algo-rows/{row_id}/manual-order")
async def manual_algo_order(
    row_id: UUID,
    payload: BsaManualOrderPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a manual BUY or SELL order for an algo script row (when ALGO is OFF).
    """
    from app.models.algo_row import BsaAlgoRow
    from app.services.bsa_algo_engine import algo_engine

    row = await db.get(BsaAlgoRow, row_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Algo row not found")

    side = payload.side.upper().strip()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="Invalid order side")

    order_qty = payload.quantity or row.quantity
    order_price = payload.price or 0.0

    fill = await algo_engine._execute_order(row, side=side, price=order_price, db=db)
    if not fill:
        raise HTTPException(status_code=502, detail="Broker order execution failed")

    if side == "BUY":
        row.buy_price = fill
        row.status = "IN_POSITION"
        # Populate Fibonacci target and SL if not already calculated
        if not row.sell_tgt:
            from app.market.market_poller import get_poller
            from app.strategy.excel_formula_engine import evaluate_columns_in_order, formula_for_book
            from app.models.terminal_column import FIBONACCI_FORMULA_COLUMNS
            poller = get_poller()
            live = next((t for t in (poller._last_data or []) if t.get("symbol") == row.symbol), {})
            tick_data = {
                "symbol": row.symbol,
                "ltp": fill,
                "open": live.get("open") or fill,
                "high": live.get("high") or fill,
                "low": live.get("low") or fill,
                "close": live.get("close") or fill,
            }
            is_opt = is_option_symbol(row.symbol, row.segment if row.segment != "NSE_EQ" else None)
            fib_cols = [
                {**c, "formula": formula_for_book(c["name"], c["formula"], "option" if is_opt else "equity")}
                for c in FIBONACCI_FORMULA_COLUMNS
            ]
            fib_vals = evaluate_columns_in_order(fib_cols, tick_data)
            row.sell_tgt = float(fib_vals.get("t11.8") or fib_vals.get("t11_8") or (fill * (1.118 if is_opt else 1.00118)))
            row.stop_loss = float(fib_vals.get("sl") or (fill * 0.995))
            row.entry_level = float(fib_vals.get("entry") or fill)
    elif side == "SELL":
        row.trades_completed += 1
        if row.buy_price:
            row.pnl = round((fill - row.buy_price) * row.quantity, 2)
        row.status = "COMPLETED" if row.trades_completed >= row.number_of_trades else "WAITING_RETURN"

    await db.commit()
    return {
        "status": "executed",
        "side": side,
        "symbol": row.symbol,
        "quantity": order_qty,
        "fill_price": fill,
        "trades_completed": row.trades_completed,
    }


class ImportDhanPositionPayload(BaseModel):
    symbol: str
    exchange: Optional[str] = "NSE"
    segment: Optional[str] = "NSE_EQ"
    security_id: Optional[str] = None
    quantity: int = 1
    buy_price: float
    target_type: Optional[str] = "T1"
    custom_target: Optional[float] = None


@router.get("/dhan-positions")
async def get_dhan_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch open positions from the user's active Dhan account (or Paper simulation)
    to allow 1-click import into the Algo Trading Window for automated profit booking.
    """
    try:
        result = await db.execute(
            select(BrokerAccount).where(
                BrokerAccount.user_id == current_user.id,
                BrokerAccount.is_active == True,
            )
        )
        accounts = result.scalars().all()
        master = next((a for a in accounts if a.account_role == "MASTER" and a.is_active), None)
        if not master:
            master = next((a for a in accounts if a.is_active), None)

        if not master:
            return {"positions": [], "message": "No active broker account linked"}

        adapter = get_broker_adapter(master)
        raw_positions = await adapter.get_positions()
        parsed = []
        for pos in (raw_positions or []):
            net_qty = int(pos.get("netQty") or pos.get("quantity") or 0)
            if net_qty != 0:
                sym = pos.get("tradingSymbol") or pos.get("customSymbol") or pos.get("symbol") or str(pos.get("securityId") or "")
                seg = pos.get("exchangeSegment") or pos.get("segment") or ("NSE_FNO" if is_option_symbol(sym) else "NSE_EQ")
                exch = "MCX" if "MCX" in str(seg) else ("NFO" if seg in ("NSE_FNO", "NFO") else ("NSE" if "NSE" in str(seg) else "BSE"))
                sec_id = str(pos.get("securityId") or "")
                buy_avg = float(pos.get("buyAvg") or pos.get("costPrice") or pos.get("price") or 0.0)
                ltp = float(pos.get("ltp") or pos.get("lastPrice") or 0.0)
                pnl = float(pos.get("unrealizedProfit") or pos.get("realizedProfit") or 0.0)

                parsed.append({
                    "symbol": sym,
                    "exchange": exch,
                    "segment": seg,
                    "security_id": sec_id,
                    "net_qty": net_qty,
                    "quantity": abs(net_qty),
                    "side": "BUY" if net_qty > 0 else "SELL",
                    "buy_price": buy_avg,
                    "ltp": ltp,
                    "pnl": pnl,
                    "account_name": master.account_name or master.client_id,
                })

        return {"positions": parsed, "account_name": master.account_name or master.client_id, "is_paper": master.paper_trading}
    except Exception as e:
        logger.error(f"Error fetching Dhan positions: {e}", exc_info=True)
        return {"positions": [], "message": f"Failed to fetch positions: {str(e)}"}


@router.post("/algo-rows/import-position")
async def import_dhan_position_to_algo(
    payload: ImportDhanPositionPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Import an existing Dhan holding / position directly into the Algo Trading Window
    in SELL_ONLY mode with status IN_POSITION, ready for automated target exit / profit booking.
    """
    from app.models.algo_row import BsaAlgoRow
    from app.market.market_poller import get_poller

    sym = payload.symbol.upper().strip()
    is_opt = is_option_symbol(sym, payload.segment if payload.segment != "NSE_EQ" else None)
    target_seg = "NSE_FNO" if is_opt else (payload.segment or "NSE_EQ")
    target_exch = "NFO" if is_opt else (payload.exchange or "NSE")

    res = await db.execute(
        select(BsaAlgoRow).where(
            BsaAlgoRow.user_id == current_user.id,
            BsaAlgoRow.symbol == sym,
        )
    )
    row = res.scalars().first()
    if not row:
        row = BsaAlgoRow(
            user_id=current_user.id,
            symbol=sym,
            exchange=target_exch,
            segment=target_seg,
            token=payload.security_id,
        )
        db.add(row)

    row.quantity = max(1, payload.quantity)
    row.buy_price = payload.buy_price
    row.trade_mode = "SELL_ONLY"
    row.status = "IN_POSITION"
    row.is_algo_active = False  # Keep off until user clicks ALGO ON
    row.target_type = payload.target_type or "T1"
    row.custom_target = payload.custom_target

    poller = get_poller()
    if payload.security_id:
        poller.add_symbol(sym, payload.security_id, target_seg)

    await db.commit()
    await db.refresh(row)
    return {"status": "imported", "id": str(row.id), "symbol": row.symbol, "buy_price": row.buy_price, "quantity": row.quantity}



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
    """Place a manual BUY/SELL order via Dhan (live only — gated)."""
    from app.broker.factory import get_broker_adapter
    from app.broker.base import OrderRequest
    from app.models.broker import BrokerAccount, BrokerName
    from app.core.trading_mode import LiveTradingError, assert_live_allowed, require_not_killed
    from sqlalchemy import select

    try:
        assert_live_allowed()
        await require_not_killed()
    except LiveTradingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

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
        # If BSE segment, look up NSE equivalent for Dhan compatibility
        security_id = body.security_id
        exchange    = body.exchange_segment
        if exchange == "BSE_EQ":
            try:
                import pandas as pd, os
                csv_path = os.path.join(os.path.dirname(__file__),
                    "../../market/instruments.csv")
                df = pd.read_csv(csv_path, header=None, low_memory=False)
                # Find NSE row matching same ISIN
                bse_row = df[df.iloc[:,2].astype(str) == str(security_id)]
                if not bse_row.empty:
                    isin = bse_row.iloc[0, 3]
                    nse_row = df[(df.iloc[:,0] == "NSE") & (df.iloc[:,3] == isin)]
                    if not nse_row.empty:
                        security_id = str(nse_row.iloc[0, 2])
                        exchange    = "NSE_EQ"
            except Exception as e:
                logger.warning(f"NSE lookup failed: {e}")

        adapter = get_broker_adapter(account)
        from app.core.trading_mode import assert_feed_fresh
        await assert_feed_fresh(get_redis())
        # Dhan adapter uses order.symbol as securityId
        order = OrderRequest(
            symbol        = security_id,
            exchange      = exchange,
            direction     = body.transaction_type.upper(),
            quantity      = body.quantity,
            order_type    = body.order_type.upper(),
            product       = body.product_type.upper(),
            price         = body.price if body.order_type == "LIMIT" else 0,
            trigger_price = body.trigger_price,
        )
        from app.services.dhan_fanout_engine import fanout_engine
        fanout_res = await fanout_engine.execute_fanout_order(
            user_id=current_user.id,
            base_order=order,
            source="WATCHLIST_MANUAL",
            db=db,
        )
        master_info = fanout_res.get("master") or {}
        if master_info.get("status") == "REJECTED":
            raise HTTPException(status_code=502, detail=master_info.get("error_message") or "Master order failed")
        return {
            "status":           "placed",
            "order_id":         master_info.get("broker_order_id") or "DHAN-ORDER",
            "batch_id":         fanout_res.get("batch_id"),
            "symbol":           body.symbol,
            "transaction_type": body.transaction_type,
            "quantity":         body.quantity,
            "fanout":           fanout_res,
        }
    except HTTPException:
        raise
    except LiveTradingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Order failed: {str(e)}")


async def _dhan_get(path: str):
    """GET a Dhan v2 path. Uses the same IPv4 requests path as order placement."""
    import asyncio
    import requests
    from app.core.config import settings

    def _fetch():
        return requests.get(
            f"https://api.dhan.co/v2{path}",
            headers={
                "access-token": settings.DHAN_ACCESS_TOKEN,
                "dhanClientId": settings.DHAN_CLIENT_ID,
                "Accept":       "application/json",
            },
            timeout=20,
        )

    try:
        resp = await asyncio.to_thread(_fetch)
    except requests.RequestException as e:
        logger.warning(f"Dhan {path} unreachable: {e.__class__.__name__}")
        raise HTTPException(status_code=502, detail=f"Dhan did not respond ({e.__class__.__name__})")
    try:
        return resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Dhan returned a non-JSON response")


def _pair_dhan_fills(fills: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turn Dhan fills into closed round trips and leftover open lots."""
    from collections import defaultdict, deque

    books: dict = defaultdict(deque)
    closed: list[dict] = []
    for fill in sorted(fills, key=lambda row: row["time"] or ""):
        key = (fill["security_id"], fill["product"], fill["symbol"])
        qty = int(fill["qty"] or 0)
        book = books[key]
        while qty > 0 and book and book[0]["side"] != fill["side"]:
            lot = book[0]
            take = min(qty, lot["qty"])
            if lot["side"] == "BUY":
                entry, exit_price, direction = lot["price"], fill["price"], "BUY"
                pnl = (exit_price - entry) * take
            else:
                entry, exit_price, direction = lot["price"], fill["price"], "SELL"
                pnl = (entry - exit_price) * take
            pnl_pct = (pnl / (entry * take) * 100) if entry else 0
            closed.append({
                "id": f"{lot['order_id']}-{fill['order_id']}-{take}",
                "symbol": fill["symbol"],
                "exchange": fill["exchange"],
                "direction": direction,
                "quantity": take,
                "entry_price": entry,
                "exit_price": exit_price,
                "stop_loss": None,
                "target_price": None,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "exit_reason": "DHAN",
                "status": "CLOSED",
                "is_paper": False,
                "created_at": lot["time"],
                "closed_at": fill["time"],
            })
            lot["qty"] -= take
            qty -= take
            if lot["qty"] <= 0:
                book.popleft()
        if qty > 0:
            book.append({
                "side": fill["side"],
                "qty": qty,
                "price": fill["price"],
                "time": fill["time"],
                "order_id": fill["order_id"],
                "symbol": fill["symbol"],
                "exchange": fill["exchange"],
            })
    open_rows = []
    for book in books.values():
        for lot in book:
            open_rows.append({
                "id": f"open-{lot['order_id']}-{lot['qty']}",
                "symbol": lot["symbol"],
                "exchange": lot["exchange"],
                "direction": lot["side"],
                "quantity": lot["qty"],
                "entry_price": lot["price"],
                "exit_price": None,
                "stop_loss": None,
                "target_price": None,
                "pnl": None,
                "pnl_pct": None,
                "exit_reason": None,
                "status": "OPEN",
                "is_paper": False,
                "created_at": lot["time"],
                "closed_at": None,
            })
    closed.sort(key=lambda row: row["closed_at"] or "", reverse=True)
    return closed, open_rows


@router.get("/trade-history")
async def get_dhan_trade_history(
    current_user: User = Depends(get_current_user),
):
    """Live fills from Dhan, including trades placed on the Dhan app."""
    from datetime import date, timedelta
    from app.core.config import settings

    if not settings.DHAN_ACCESS_TOKEN or not settings.DHAN_CLIENT_ID:
        return {"connected": False, "trades": [], "summary": None, "weekly": []}

    end = date.today()
    start = end - timedelta(days=90)
    fills = []
    for page in range(5):
        data = await _dhan_get(f"/trades/{start.isoformat()}/{end.isoformat()}/{page}")
        rows = data if isinstance(data, list) else []
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            when = row.get("exchangeTime") or row.get("updateTime") or row.get("createTime")
            if when in (None, "NA"):
                when = None
            fills.append({
                "symbol": row.get("customSymbol") or row.get("tradingSymbol") or row.get("securityId"),
                "exchange": row.get("exchangeSegment"),
                "security_id": str(row.get("securityId") or ""),
                "product": row.get("productType") or "",
                "side": row.get("transactionType"),
                "qty": row.get("tradedQuantity") or 0,
                "price": float(row.get("tradedPrice") or 0),
                "time": when,
                "order_id": str(row.get("orderId") or row.get("exchangeTradeId") or ""),
            })
        if len(rows) < 100:
            break

    closed, open_rows = _pair_dhan_fills(fills)
    trades = closed + open_rows
    winners = [row for row in closed if (row["pnl"] or 0) > 0]
    losers = [row for row in closed if (row["pnl"] or 0) < 0]
    total_pnl = round(sum(row["pnl"] or 0 for row in closed), 2)
    today = date.today().isoformat()
    today_pnl = round(sum(
        row["pnl"] or 0 for row in closed
        if (row["closed_at"] or "").startswith(today)
    ), 2)
    weekly = []
    for offset in range(6, -1, -1):
        day = end - timedelta(days=offset)
        key = day.isoformat()
        pnl = sum(row["pnl"] or 0 for row in closed if (row["closed_at"] or "").startswith(key))
        weekly.append({"day": day.strftime("%a"), "date": key, "pnl": round(pnl, 2)})
    return {
        "connected": True,
        "trades": trades[:50],
        "summary": {
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "total_pnl": total_pnl,
            "today_pnl": today_pnl,
            "win_rate": round(len(winners) / len(closed) * 100, 1) if closed else 0,
            "winners": len(winners),
            "losers": len(losers),
        },
        "weekly": weekly,
    }


@router.get("/orderbook")
async def get_orderbook(
    current_user: User = Depends(get_current_user),
):
    """Fetch today's orders from Dhan broker API."""
    data = await _dhan_get("/orders")

    if isinstance(data, list):
        orders = data
    elif isinstance(data, dict):
        orders = data.get("data", data.get("orders", []))
    else:
        orders = []

    return [
        {
            "order_id":        o.get("orderId"),
            "symbol":          o.get("tradingSymbol") or o.get("securityId"),
            "exchange":        o.get("exchangeSegment"),
            "transaction_type":o.get("transactionType"),
            "order_type":      o.get("orderType"),
            "product_type":    o.get("productType"),
            "quantity":        o.get("quantity"),
            "price":           o.get("price"),
            "trigger_price":   o.get("triggerPrice"),
            "status":          o.get("orderStatus"),
            "created_at":      o.get("createTime"),
            "updated_at":      o.get("updateTime"),
            "filled_qty":      o.get("filledQty"),
            "avg_price":       o.get("averageTradedPrice"),
            "remarks":         o.get("omsErrorDescription") or o.get("remarks", ""),
        }
        for o in orders
        if isinstance(o, dict)
    ]


@router.get("/positions")
async def get_today_positions(
    current_user: User = Depends(get_current_user),
):
    """Fetch today's positions from Dhan. A flattened trade comes back with netQty 0."""
    data = await _dhan_get("/positions")
    rows = data if isinstance(data, list) else (data.get("data") or []) if isinstance(data, dict) else []
    return [
        {
            "symbol":        p.get("tradingSymbol") or p.get("securityId"),
            "exchange":      p.get("exchangeSegment"),
            "product_type":  p.get("productType"),
            "net_qty":       p.get("netQty"),
            "position_type": p.get("positionType"),
            "buy_qty":       p.get("dayBuyQty") or p.get("buyQty"),
            "sell_qty":      p.get("daySellQty") or p.get("sellQty"),
            "buy_avg":       p.get("buyAvg"),
            "sell_avg":      p.get("sellAvg"),
            "unrealized":    p.get("unrealizedProfit"),
            "realized":      p.get("realizedProfit"),
        }
        for p in rows
        if isinstance(p, dict)
    ]
