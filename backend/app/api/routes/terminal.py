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


@router.get("/column-presets")
async def list_column_presets(
    book: str = "equity",
    current_user: User = Depends(require_admin),
):
    """House column templates. Admin only, so the expressions stay out of the trader bundle."""
    from app.strategy.excel_formula_engine import formula_for_book

    if book not in ("equity", "option"):
        raise HTTPException(status_code=400, detail="book must be equity or option")
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
    book:        str   = "equity"       # equity or option; market columns are shared


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


class ColumnValueRequest(BaseModel):
    ticks: list[ColumnValueTick] = []
    book: str = "equity"


async def _column_for_editor(db: AsyncSession, col_id: UUID, current_user: User):
    """Admins share one column set, so any admin can edit a column owned by another admin."""
    from app.models.terminal_column import TerminalColumn

    result = await db.execute(select(TerminalColumn).where(TerminalColumn.id == col_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Column not found")
    if col.user_id == current_user.id:
        return col
    if current_user.role == UserRole.admin:
        owner = await db.get(User, col.user_id)
        if owner and owner.role == UserRole.admin:
            return col
    raise HTTPException(status_code=404, detail="Column not found")


async def _shared_columns(db: AsyncSession, current_user: User):
    """Column definitions belong to admin accounts so every terminal shows the same set."""
    from app.models.terminal_column import TerminalColumn, DEFAULT_COLUMNS

    admins = await db.execute(
        select(User.id).where(User.role == UserRole.admin).order_by(User.created_at)
    )
    admin_ids = [row[0] for row in admins.all()]
    cols = []
    if admin_ids:
        result = await db.execute(
            select(TerminalColumn)
            .where(TerminalColumn.user_id.in_(admin_ids))
            .order_by(TerminalColumn.col_order)
        )
        cols = list(result.scalars().all())
    if not cols and current_user.role == UserRole.admin:
        for d in DEFAULT_COLUMNS:
            db.add(TerminalColumn(
                user_id=current_user.id,
                name=d["name"],
                col_key=d["col_key"],
                col_type=d["col_type"],
                formula=d.get("formula"),
                col_order=d["col_order"],
                width=d["width"],
                is_visible=True,
                color_rules=d["color_rules"],
                book="shared",
            ))
        await db.commit()
        result = await db.execute(
            select(TerminalColumn)
            .where(TerminalColumn.user_id == current_user.id)
            .order_by(TerminalColumn.col_order)
        )
        cols = list(result.scalars().all())
    cols = await _ensure_option_formulas(db, cols)
    return cols


async def _ensure_option_formulas(db: AsyncSession, cols: list):
    """Copy equity formulas into the options book once. Later edits stay on the book that was saved."""
    from app.models.terminal_column import TerminalColumn
    from app.strategy.excel_formula_engine import formula_for_book

    equity = [col for col in cols if col.formula and (col.book or "equity") == "equity"]
    if not equity or any(col.book == "option" for col in cols):
        return cols
    for src in equity:
        db.add(TerminalColumn(
            user_id=src.user_id,
            name=src.name,
            col_key=src.col_key,
            col_type=src.col_type,
            formula=formula_for_book(src.name, src.formula, "option"),
            col_order=src.col_order,
            width=src.width,
            is_visible=src.is_visible,
            color_rules=src.color_rules,
            book="option",
        ))
    await db.commit()
    owner_ids = {col.user_id for col in cols}
    result = await db.execute(
        select(TerminalColumn)
        .where(TerminalColumn.user_id.in_(owner_ids))
        .order_by(TerminalColumn.col_order)
    )
    return list(result.scalars().all())


@router.post("/column-values")
async def column_values(
    payload: ColumnValueRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate the saved formulas for one book. Equity and options are stored separately."""
    from app.strategy.excel_formula_engine import evaluate_columns_in_order

    book = "option" if payload.book == "option" else "equity"
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
    if payload.book not in ("equity", "option"):
        raise HTTPException(status_code=400, detail="book must be equity or option")

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
    col_id: UUID,
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
    if (col.book or "equity") in ("equity", "option") and payload.book in ("equity", "option"):
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
            is_visible  = True,
            color_rules = d["color_rules"],
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
async def get_dhan_positions(
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
