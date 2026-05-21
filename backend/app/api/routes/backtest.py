"""
Backtesting Routes
==================
Runs a strategy against historical (simulated) OHLCV data
and returns detailed trade-by-trade results + equity curve.
"""
import logging
import random
import pandas as pd
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.deps import get_current_user
from app.models.user import User
from app.strategy.registry import get_strategy_class, STRATEGY_REGISTRY

logger = logging.getLogger(__name__)
router = APIRouter()


class BacktestRequest(BaseModel):
    engine_class:      str
    symbol:            str   = "RELIANCE"
    exchange:          str   = "NSE"
    params:            dict  = {}
    bars:              int   = 500
    timeframe_minutes: int   = 5
    initial_capital:   float = 100000.0


class BacktestResult(BaseModel):
    engine_class:    str
    symbol:          str
    timeframe:       int
    bars_tested:     int
    total_trades:    int
    winning_trades:  int
    losing_trades:   int
    win_rate:        float
    total_pnl:       float
    max_drawdown:    float
    sharpe_ratio:    float
    trades:          list
    equity_curve:    list


@router.get("/strategies")
async def list_backtestable(current_user: User = Depends(get_current_user)):
    """List strategies available for backtesting."""
    return [{"engine_class": k} for k in STRATEGY_REGISTRY.keys()]


@router.post("/run", response_model=BacktestResult)
async def run_backtest(
    payload: BacktestRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Run a strategy backtest against historical candle data.
    Returns full trade log + equity curve for charting.
    """
    # Validate strategy exists
    try:
        strategy_cls = get_strategy_class(payload.engine_class)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {payload.engine_class}")

    # Build params with symbol/exchange injected
    params = {
        **payload.params,
        "symbol":   payload.symbol,
        "exchange":  payload.exchange,
        "quantity": int(payload.params.get("quantity", 1)),
        "fast":     int(payload.params.get("fast", 9)),
        "slow":     int(payload.params.get("slow", 21)),
    }

    strategy = strategy_cls(params)

    # Generate historical candles
    candles = _generate_historical_candles(
        symbol        = payload.symbol,
        num_bars      = payload.bars,
        interval_min  = payload.timeframe_minutes,
    )

    if len(candles) < params["slow"] + 5:
        raise HTTPException(status_code=400, detail="Not enough historical bars for this strategy")

    # Build DataFrame
    df = pd.DataFrame(candles)
    df["datetime"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("datetime")[["open","high","low","close","volume"]]

    # Run strategy bar by bar
    trades       = []
    equity_curve = []
    capital      = payload.initial_capital
    position     = 0       # 0 = flat, 1 = long
    entry_price  = 0.0
    entry_time   = None
    peak_capital = capital

    for i in range(params["slow"] + 1, len(df)):
        window = df.iloc[:i]
        signal = strategy.generate_signal(window)

        current_price = float(df["close"].iloc[i - 1])
        current_time  = str(df.index[i - 1])

        if signal and signal.direction == "BUY" and position == 0:
            position    = 1
            entry_price = current_price
            entry_time  = current_time

        elif signal and signal.direction == "SELL" and position == 1:
            exit_price = current_price
            pnl        = (exit_price - entry_price) * params["quantity"]
            capital   += pnl
            position   = 0
            strategy.on_order_filled(signal, exit_price)

            trades.append({
                "entry_time":  entry_time,
                "exit_time":   current_time,
                "direction":   "BUY",
                "entry_price": round(entry_price, 2),
                "exit_price":  round(exit_price, 2),
                "quantity":    params["quantity"],
                "pnl":         round(pnl, 2),
                "capital":     round(capital, 2),
            })

        # Track equity curve every 10 bars
        if i % 10 == 0:
            unrealised = (current_price - entry_price) * params["quantity"] * position
            equity_curve.append({
                "time":   int(df.index[i - 1].timestamp()),
                "equity": round(capital + unrealised, 2),
            })

        peak_capital = max(peak_capital, capital)

    # Compute stats
    winning   = [t for t in trades if t["pnl"] > 0]
    losing    = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)

    # Max drawdown
    peak = payload.initial_capital
    max_dd = 0.0
    running = payload.initial_capital
    for t in trades:
        running += t["pnl"]
        peak     = max(peak, running)
        dd       = (peak - running) / peak * 100
        max_dd   = max(max_dd, dd)

    # Sharpe (simplified: daily returns)
    if len(trades) > 1:
        returns = [t["pnl"] / payload.initial_capital for t in trades]
        mean_r  = sum(returns) / len(returns)
        std_r   = (sum((r - mean_r) ** 2 for r in returns) / len(returns)) ** 0.5
        sharpe  = round((mean_r / std_r) * (252 ** 0.5), 2) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    return BacktestResult(
        engine_class   = payload.engine_class,
        symbol         = payload.symbol,
        timeframe      = payload.timeframe_minutes,
        bars_tested    = len(df),
        total_trades   = len(trades),
        winning_trades = len(winning),
        losing_trades  = len(losing),
        win_rate       = round(len(winning) / len(trades) * 100, 1) if trades else 0,
        total_pnl      = round(total_pnl, 2),
        max_drawdown   = round(max_dd, 2),
        sharpe_ratio   = sharpe,
        trades         = trades[-50:],    # last 50 trades
        equity_curve   = equity_curve,
    )


# ── Shared candle generator (same as market route but deterministic for BT) ──

INSTRUMENT_BASES = {
    "RELIANCE": 2850, "TCS": 3920, "INFY": 1540, "HDFCBANK": 1680,
    "ICICIBANK": 1120, "WIPRO": 480, "SBIN": 820, "NIFTY50": 24800,
}

def _generate_historical_candles(symbol: str, num_bars: int, interval_min: int) -> list:
    base  = INSTRUMENT_BASES.get(symbol.upper(), 1000)
    price = base
    now   = datetime.now().replace(second=0, microsecond=0)
    bars  = []
    rng   = random.Random(hash(symbol) % 999983)  # deterministic seed per symbol

    for i in range(num_bars, 0, -1):
        ts    = now - timedelta(minutes=i * interval_min)
        vol   = base * rng.uniform(0.001, 0.004)
        chg   = rng.gauss(0, vol / base)
        open_ = round(price, 2)
        close = round(price * (1 + chg), 2)
        high  = round(max(open_, close) * rng.uniform(1.0, 1.008), 2)
        low   = round(min(open_, close) * rng.uniform(0.992, 1.0), 2)
        bars.append({
            "time": int(ts.timestamp()),
            "open": open_, "high": high, "low": low, "close": close,
            "volume": rng.randint(100000, 500000),
        })
        price = close

    return bars
