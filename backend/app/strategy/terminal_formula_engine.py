"""
Terminal Formula Engine
=======================
Evaluates per-row formulas for the trade terminal.
Formulas are stored encrypted in DB, never exposed via API to non-admin users.
Users only see the OUTPUT: signal, entry_price, target, sl.

Built-in strategies available as formula shortcuts:
  @ORFib          — Opening Range Fibonacci (dad's Pine Script strategy)
  @MACross(9,21)  — Moving Average Crossover
  @RSI(14,30,70)  — RSI oversold/overbought

Custom formula syntax (same as FormulaEvaluator):
  entry_long:  "ltp > ma(20) AND rsi(14) < 70"
  exit_long:   "ltp < ma(20)"
  target:      "entry * 1.02"       ← 2% above entry
  sl:          "entry * 0.99"       ← 1% below entry
  trail_pct:   "0.5"                ← trail 0.5% from peak
"""
import math
import logging
import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Optional
import pytz

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class TerminalFormulaResult:
    """Output of evaluating a terminal row formula."""
    def __init__(self):
        self.signal:      str | None   = None   # "BUY" / "SELL" / "EXIT" / None
        self.entry_price: float | None = None
        self.target:      float | None = None
        self.sl:          float | None = None
        self.trail_pct:   float | None = None
        self.reason:      str          = ""


class TerminalFormulaEngine:
    """
    Evaluates a terminal row's formula against live market data.
    Each row can have one of:
      1. A built-in strategy shortcut (@ORFib, @MACross, @RSI)
      2. A custom formula expression
      3. No formula (manual mode — user sets values themselves)
    """

    def __init__(self, row_config: dict):
        """
        row_config keys:
          entry_formula  — expression or @strategy shortcut
          exit_formula   — expression for exit signal
          target_formula — expression for target price (can reference 'entry')
          sl_formula     — expression for stop loss (can reference 'entry')
          trail_pct      — fixed trail % (optional)
        """
        self.entry_formula  = row_config.get("entry_formula", "")
        self.exit_formula   = row_config.get("exit_formula", "")
        self.target_formula = row_config.get("target_formula", "")
        self.sl_formula     = row_config.get("sl_formula", "")
        self.trail_pct      = row_config.get("trail_pct")
        self._day_open:    float | None = None
        self._last_date:   str   | None = None

    def evaluate(
        self,
        df: pd.DataFrame,
        ltp: float,
        entry_price: float | None = None,  # current entry if in position
    ) -> TerminalFormulaResult:
        result = TerminalFormulaResult()
        if df.empty or ltp == 0:
            return result

        # Reset state at new day
        today = datetime.now(IST).strftime("%Y-%m-%d")
        if today != self._last_date:
            self._day_open  = None
            self._last_date = today

        # Capture day open
        if self._day_open is None and len(df) > 0:
            now_ist = datetime.now(IST).time()
            if now_ist >= time(9, 15):
                self._day_open = float(df["open"].iloc[0])

        # ── Built-in strategy shortcuts ───────────────────────────────────────
        if self.entry_formula.startswith("@"):
            return self._eval_builtin(df, ltp, entry_price)

        # ── Custom formula expressions ────────────────────────────────────────
        return self._eval_custom(df, ltp, entry_price)

    def _eval_builtin(
        self, df: pd.DataFrame, ltp: float, entry_price: float | None
    ) -> TerminalFormulaResult:
        result = TerminalFormulaResult()
        formula = self.entry_formula.strip()

        # @ORFib — Opening Range Fibonacci (dad's strategy)
        if formula.startswith("@ORFib"):
            return self._eval_orfib(df, ltp, entry_price)

        # @MACross(fast, slow)
        if formula.startswith("@MACross"):
            params = self._parse_params(formula, defaults=[9, 21])
            return self._eval_macross(df, ltp, entry_price, int(params[0]), int(params[1]))

        # @RSI(period, oversold, overbought)
        if formula.startswith("@RSI"):
            params = self._parse_params(formula, defaults=[14, 30, 70])
            return self._eval_rsi(df, ltp, entry_price,
                                   int(params[0]), float(params[1]), float(params[2]))

        # @VWAP — trade above/below VWAP
        if formula.startswith("@VWAP"):
            return self._eval_vwap(df, ltp, entry_price)

        result.reason = f"Unknown built-in: {formula}"
        return result

    def _eval_orfib(
        self, df: pd.DataFrame, ltp: float, entry_price: float | None
    ) -> TerminalFormulaResult:
        """Opening Range Fibonacci — dad's proprietary strategy."""
        result = TerminalFormulaResult()
        day_open = self._day_open
        if not day_open:
            result.reason = "Waiting for 9:15 AM open"
            return result

        # Direction
        is_buy  = ltp > day_open
        is_sell = ltp < day_open

        if not is_buy and not is_sell:
            return result

        # Square root entry formula (proprietary)
        if is_buy:
            entry = round(math.pow(math.sqrt(day_open) + 0.025, 2))
            sl    = round(entry * 0.995, 2)
            # Fibonacci targets from day_open
            t1 = round(day_open + day_open * 0.382 / 100, 2)  # T3 default
            t2 = round(day_open + day_open * 1.0   / 100, 2)  # T7
            result.signal      = "BUY"
            result.entry_price = entry
            result.sl          = sl
            result.target      = t1
            result.reason      = f"ORFib BUY | Open=₹{day_open} Entry=₹{entry} T=₹{t1} SL=₹{sl}"
        else:
            entry = round(math.pow(math.sqrt(day_open) - 0.025, 2))
            sl    = round(entry * 1.005, 2)
            t1 = round(day_open - day_open * 0.382 / 100, 2)
            result.signal      = "SELL"
            result.entry_price = entry
            result.sl          = sl
            result.target      = t1
            result.reason      = f"ORFib SELL | Open=₹{day_open} Entry=₹{entry} T=₹{t1} SL=₹{sl}"

        # Parse trail_pct from formula e.g. @ORFib(trail=0.3)
        if "trail=" in self.entry_formula:
            try:
                trail = float(self.entry_formula.split("trail=")[1].split(")")[0])
                result.trail_pct = trail
            except Exception:
                result.trail_pct = 0.3

        return result

    def _eval_macross(
        self, df: pd.DataFrame, ltp: float, entry_price: float | None,
        fast: int, slow: int
    ) -> TerminalFormulaResult:
        result = TerminalFormulaResult()
        if len(df) < slow + 2:
            return result
        closes = df["close"]
        ma_fast = float(closes.rolling(fast).mean().iloc[-1])
        ma_slow = float(closes.rolling(slow).mean().iloc[-1])
        ma_fast_prev = float(closes.rolling(fast).mean().iloc[-2])
        ma_slow_prev = float(closes.rolling(slow).mean().iloc[-2])

        # Golden cross
        if ma_fast_prev <= ma_slow_prev and ma_fast > ma_slow:
            result.signal      = "BUY"
            result.entry_price = round(ltp, 2)
            result.target      = round(ltp * 1.02, 2)
            result.sl          = round(ltp * 0.99, 2)
            result.reason = f'MA{fast}>MA{slow} Golden Cross'
        # Death cross
        elif ma_fast_prev >= ma_slow_prev and ma_fast < ma_slow:
            result.signal      = "SELL"
            result.entry_price = round(ltp, 2)
            result.target      = round(ltp * 0.98, 2)
            result.sl          = round(ltp * 1.01, 2)
            result.reason      = f"MA{fast}<MA{slow} Death Cross"
        # Exit
        elif entry_price and abs(ma_fast - ma_slow) / ma_slow < 0.001:
            result.signal = "EXIT"
            result.reason = "MA converging — exit"
        return result

    def _eval_rsi(
        self, df: pd.DataFrame, ltp: float, entry_price: float | None,
        period: int, oversold: float, overbought: float
    ) -> TerminalFormulaResult:
        result = TerminalFormulaResult()
        if len(df) < period + 2:
            return result
        closes = df["close"]
        delta  = closes.diff()
        gain   = delta.clip(lower=0).rolling(period).mean()
        loss   = (-delta.clip(upper=0)).rolling(period).mean()
        rs     = gain / loss.replace(0, np.nan)
        rsi    = float((100 - 100 / (1 + rs)).iloc[-1])

        if rsi < oversold:
            result.signal      = "BUY"
            result.entry_price = round(ltp, 2)
            result.target      = round(ltp * 1.015, 2)
            result.sl          = round(ltp * 0.99,  2)
            result.reason      = f"RSI({period})={rsi:.1f} oversold"
        elif rsi > overbought:
            result.signal      = "SELL"
            result.entry_price = round(ltp, 2)
            result.target      = round(ltp * 0.985, 2)
            result.sl          = round(ltp * 1.01,  2)
            result.reason      = f"RSI({period})={rsi:.1f} overbought"
        elif entry_price and 45 < rsi < 55:
            result.signal = "EXIT"
            result.reason = f"RSI neutral ({rsi:.1f})"
        return result

    def _eval_vwap(
        self, df: pd.DataFrame, ltp: float, entry_price: float | None
    ) -> TerminalFormulaResult:
        result = TerminalFormulaResult()
        if len(df) < 5:
            return result
        typical = (df["high"] + df["low"] + df["close"]) / 3
        vwap    = float((typical * df["volume"]).sum() / df["volume"].replace(0, np.nan).sum())

        if ltp > vwap * 1.001:
            result.signal      = "BUY"
            result.entry_price = round(ltp, 2)
            result.target      = round(vwap * 1.01, 2)
            result.sl          = round(vwap * 0.999, 2)
            result.reason      = f"LTP ₹{ltp} > VWAP ₹{vwap:.2f}"
        elif ltp < vwap * 0.999:
            result.signal      = "SELL"
            result.entry_price = round(ltp, 2)
            result.target      = round(vwap * 0.99, 2)
            result.sl          = round(vwap * 1.001, 2)
            result.reason      = f"LTP ₹{ltp} < VWAP ₹{vwap:.2f}"
        return result

    def _eval_custom(
        self, df: pd.DataFrame, ltp: float, entry_price: float | None
    ) -> TerminalFormulaResult:
        """Evaluate free-form expression formulas."""
        from app.strategy.formula_engine import FormulaEvaluator
        result = TerminalFormulaResult()

        try:
            # Entry signal
            if self.entry_formula:
                ev     = FormulaEvaluator(self.entry_formula)
                signal = ev.evaluate(df, ltp)
                if signal is True:
                    result.signal      = "BUY"
                    result.entry_price = self._eval_price_expr(
                        self.target_formula, ltp, ltp, df
                    ) or round(ltp, 2)

            # Exit signal (if in position)
            if self.exit_formula and entry_price:
                ev_exit = FormulaEvaluator(self.exit_formula)
                if ev_exit.evaluate(df, ltp):
                    result.signal = "EXIT"

            # Target and SL from price expressions
            ep = result.entry_price or entry_price or ltp
            if self.target_formula:
                result.target = self._eval_price_expr(self.target_formula, ep, ltp, df)
            if self.sl_formula:
                result.sl = self._eval_price_expr(self.sl_formula, ep, ltp, df)
            if self.trail_pct:
                result.trail_pct = float(self.trail_pct)

        except Exception as e:
            logger.warning(f"Custom formula eval error: {e}")

        return result

    def _eval_price_expr(
        self, expr: str, entry: float, ltp: float, df: pd.DataFrame
    ) -> float | None:
        """Evaluate a price expression like 'entry * 1.02' or 'ma(20) * 0.99'."""
        if not expr:
            return None
        try:
            closes = df["close"]
            ns = {
                "entry": entry, "ltp": ltp,
                "ma":  lambda p: float(closes.rolling(int(p)).mean().iloc[-1]),
                "ema": lambda p: float(closes.ewm(span=int(p), adjust=False).mean().iloc[-1]),
                "abs": abs, "round": round, "min": min, "max": max,
            }
            return round(float(eval(expr, {"__builtins__": {}}, ns)), 2)
        except Exception as e:
            logger.warning(f"Price expr error [{expr}]: {e}")
            return None

    @staticmethod
    def _parse_params(formula: str, defaults: list) -> list:
        """Parse @StratName(p1,p2) → [p1, p2]."""
        try:
            inner = formula.split("(")[1].rstrip(")")
            return [float(x.strip()) for x in inner.split(",")]
        except Exception:
            return defaults
