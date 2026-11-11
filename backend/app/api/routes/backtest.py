"""
Backtesting routes.

Candles come from Dhan history. Signals come from generate_signal.
A losing run is stored and blocks the next live start of that version and symbol.
"""
import logging
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.backtest import BacktestRun
from app.models.user import User
from app.strategy.backtest_runner import FormulaStrategy, run_backtest
from app.strategy.registry import STRATEGY_REGISTRY, get_strategy_class

logger = logging.getLogger(__name__)
router = APIRouter()


class BacktestRequest(BaseModel):
    engine_class: str
    symbol: str = "RELIANCE"
    exchange: str = "NSE"
    params: dict = {}
    formula: str | None = None
    bars: int = 500
    timeframe_minutes: int = 5
    initial_capital: float = 100000.0
    slippage_pct: float = 0.05
    fee_per_order: float = 20.0


class BacktestResult(BaseModel):
    engine_class: str
    version: str
    symbol: str
    timeframe: int
    bars_tested: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    passed: bool
    trades: list
    equity_curve: list


@router.get("/strategies")
async def list_backtestable(current_user: User = Depends(require_admin)):
    return [{"engine_class": key, "version": cls.version} for key, cls in STRATEGY_REGISTRY.items()]


@router.post("/run", response_model=BacktestResult)
async def run_backtest_route(
    payload: BacktestRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        strategy_cls = get_strategy_class(payload.engine_class)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {payload.engine_class}")

    params = {
        **payload.params,
        "symbol": payload.symbol,
        "exchange": payload.exchange,
        "quantity": int(payload.params.get("quantity", 1)),
    }
    if payload.formula:
        params["formula"] = payload.formula
        strategy = FormulaStrategy(params)
        version = strategy_cls.version
    else:
        strategy = strategy_cls(params)
        version = strategy_cls.version
        if not strategy.validate_params():
            raise HTTPException(status_code=400, detail="Strategy parameters failed validation")

    import asyncio
    from app.market.history import fetch_intraday_candles

    try:
        candles = await asyncio.to_thread(
            fetch_intraday_candles,
            payload.symbol,
            payload.exchange,
            payload.timeframe_minutes,
            payload.bars,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.warning("Historical candles failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Historical candles unavailable: {exc}")

    frame = pd.DataFrame(candles)
    frame["datetime"] = pd.to_datetime(frame["time"], unit="s")
    frame = frame.set_index("datetime")[["open", "high", "low", "close", "volume"]]
    if len(frame) < int(getattr(strategy, "warmup_bars", 2)) + 1:
        raise HTTPException(status_code=400, detail="Not enough historical bars for this strategy")

    result = run_backtest(
        frame,
        strategy,
        quantity=params["quantity"],
        initial_capital=payload.initial_capital,
        slippage_pct=payload.slippage_pct,
        fee_per_order=payload.fee_per_order,
    )
    db.add(BacktestRun(
        user_id=current_user.id,
        engine_class=payload.engine_class,
        version=version,
        symbol=payload.symbol.upper(),
        timeframe=payload.timeframe_minutes,
        passed=result["passed"],
        total_pnl=result["total_pnl"],
        max_drawdown=result["max_drawdown"],
        trade_count=result["total_trades"],
        created_at=datetime.utcnow(),
    ))
    await db.commit()

    return BacktestResult(
        engine_class=payload.engine_class,
        version=version,
        symbol=payload.symbol.upper(),
        timeframe=payload.timeframe_minutes,
        bars_tested=result["bars_tested"],
        total_trades=result["total_trades"],
        winning_trades=result["winning_trades"],
        losing_trades=result["losing_trades"],
        win_rate=result["win_rate"],
        total_pnl=result["total_pnl"],
        max_drawdown=result["max_drawdown"],
        sharpe_ratio=result["sharpe_ratio"],
        passed=result["passed"],
        trades=result["trades"][-50:],
        equity_curve=result["equity_curve"],
    )


@router.get("/compare")
async def compare_backtests(
    symbol: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Latest stored backtest per registered engine for one symbol. Does not call Dhan."""
    from app.strategy.registry import refresh_plugins

    refresh_plugins()
    symbol = symbol.upper()
    engines = []
    seen = set()
    for engine_id, cls in STRATEGY_REGISTRY.items():
        version = str(getattr(cls, "version", "1"))
        seen.add(engine_id)
        row = await _latest_run(db, engine_id, version, symbol)
        engines.append(_compare_row(engine_id, version, symbol, row))

    extra = await db.execute(
        select(BacktestRun.engine_class, BacktestRun.version)
        .where(BacktestRun.symbol == symbol)
        .distinct()
    )
    for engine_class, version in extra.all():
        if engine_class in seen:
            continue
        seen.add(engine_class)
        row = await _latest_run(db, engine_class, version, symbol)
        engines.append(_compare_row(engine_class, version, symbol, row))

    engines.sort(key=lambda item: (item["total_pnl"] is None, -(item["total_pnl"] or 0)))
    return {"symbol": symbol, "engines": engines}


async def _latest_run(db: AsyncSession, engine_class: str, version: str, symbol: str):
    result = await db.execute(
        select(BacktestRun)
        .where(
            BacktestRun.engine_class == engine_class,
            BacktestRun.version == version,
            BacktestRun.symbol == symbol,
        )
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _compare_row(engine_class: str, version: str, symbol: str, row) -> dict:
    return {
        "engine_class": engine_class,
        "version": version,
        "symbol": symbol,
        "has_run": row is not None,
        "passed": None if row is None else row.passed,
        "total_pnl": None if row is None else row.total_pnl,
        "max_drawdown": None if row is None else row.max_drawdown,
        "trade_count": None if row is None else row.trade_count,
        "created_at": None if row is None or row.created_at is None else row.created_at.isoformat(),
    }


@router.get("/latest")
async def latest_backtest(
    engine_class: str,
    symbol: str,
    version: str = "1",
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BacktestRun)
        .where(
            BacktestRun.engine_class == engine_class,
            BacktestRun.version == version,
            BacktestRun.symbol == symbol.upper(),
        )
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return {"found": False}
    return {
        "found": True,
        "passed": row.passed,
        "total_pnl": row.total_pnl,
        "max_drawdown": row.max_drawdown,
        "trade_count": row.trade_count,
        "version": row.version,
        "symbol": row.symbol,
    }
