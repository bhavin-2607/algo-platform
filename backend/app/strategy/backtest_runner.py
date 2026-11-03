"""Bar-by-bar backtest. Signals come only from generate_signal."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.strategy.base import BaseStrategy, Signal
from app.strategy.formula_engine import FormulaEvaluator


class FormulaStrategy(BaseStrategy):
    """A formula string evaluated with the same engine the live formula path uses."""

    engine_id = "formula"
    version = "1"

    def __init__(self, params: dict):
        super().__init__(params)
        self.symbol = params.get("symbol", "")
        self.exchange = params.get("exchange", "NSE")
        self.quantity = int(params.get("quantity", 1))
        self._evaluator = FormulaEvaluator(params["formula"])
        self._in_position = False

    def generate_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        result = self._evaluator.evaluate(df)
        if result is True and not self._in_position:
            return Signal(self.symbol, self.exchange, "BUY", self.quantity, reason="formula true")
        if result is False and self._in_position:
            return Signal(self.symbol, self.exchange, "SELL", self.quantity, reason="formula false")
        return None

    def on_order_filled(self, signal: Signal, fill_price: float) -> None:
        self._in_position = signal.direction == "BUY"


def run_backtest(
    df: pd.DataFrame,
    strategy: BaseStrategy,
    *,
    quantity: int,
    initial_capital: float,
    slippage_pct: float = 0.05,
    fee_per_order: float = 20.0,
) -> dict:
    """Walk closed bars. Buy fills slip up, sell fills slip down, and each side pays a fee."""
    capital = float(initial_capital)
    peak = capital
    max_dd = 0.0
    position = 0
    entry_fill = 0.0
    entry_time = None
    trades = []
    equity = []
    warmup = max(int(getattr(strategy, "warmup_bars", 2)), 2)

    for i in range(warmup, len(df) + 1):
        window = df.iloc[:i]
        price = float(window["close"].iloc[-1])
        when = window.index[-1]
        signal = strategy.generate_signal(window)
        if signal and signal.direction == "BUY" and position == 0:
            entry_fill = round(price * (1 + slippage_pct / 100), 2)
            entry_time = str(when)
            position = 1
            capital -= fee_per_order
            strategy.on_order_filled(signal, entry_fill)
        elif signal and signal.direction == "SELL" and position == 1:
            exit_fill = round(price * (1 - slippage_pct / 100), 2)
            capital -= fee_per_order
            pnl = (exit_fill - entry_fill) * quantity
            capital += pnl
            position = 0
            strategy.on_order_filled(signal, exit_fill)
            trades.append({
                "entry_time": entry_time,
                "exit_time": str(when),
                "direction": "BUY",
                "entry_price": entry_fill,
                "exit_price": exit_fill,
                "quantity": quantity,
                "pnl": round(pnl - 2 * fee_per_order, 2),
                "capital": round(capital, 2),
            })

        mark = price * (1 - slippage_pct / 100) if position else price
        unrealised = (mark - entry_fill) * quantity * position
        equity_now = capital + unrealised
        peak = max(peak, equity_now)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity_now) / peak * 100)
        if i % 10 == 0 or i == len(df):
            stamp = int(when.timestamp()) if hasattr(when, "timestamp") else i
            equity.append({"time": stamp, "equity": round(equity_now, 2)})

    closed_pnl = round(sum(t["pnl"] for t in trades), 2)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    if len(trades) > 1:
        returns = [t["pnl"] / initial_capital for t in trades]
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = var ** 0.5
        sharpe = round((mean_r / std_r) * (252 ** 0.5), 2) if std_r > 0 else 0.0
    else:
        sharpe = 0.0
    passed = bool(trades) and closed_pnl >= 0
    return {
        "bars_tested": len(df),
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "total_pnl": closed_pnl,
        "max_drawdown": round(max_dd, 2),
        "sharpe_ratio": sharpe,
        "passed": passed,
        "trades": trades,
        "equity_curve": equity,
    }


def backtest_block_reason(latest_passed: bool | None) -> str | None:
    """A missing run does not block. A failed latest run does."""
    if latest_passed is False:
        return "The latest backtest for this version lost money after fees. Run a passing backtest before going live."
    return None
