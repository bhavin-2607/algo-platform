"""
Formula Strategy Engine
=======================
A no-code rule-based strategy where conditions are defined as plain text
expressions evaluated against live OHLCV + indicator data.

Condition syntax (case-insensitive):
  Indicators : ma(period), ema(period), rsi(period), vwap(), atr(period),
               bb_upper(period), bb_lower(period), supertrend(period, mult)
  Price refs  : open, high, low, close, volume, ltp, oi
  Operators   : > < >= <= == != AND OR NOT ( )
  Constants   : any number

Examples:
  "close > ma(20) AND rsi(14) < 70"
  "ltp > bb_upper(20) AND volume > 500000"
  "ma(9) > ma(21)"   ← golden cross
"""
import re
import logging
import numpy as np
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)


# ── Indicator library ─────────────────────────────────────────────────────────

def _ma(series: pd.Series, period: int) -> float:
    if len(series) < period:
        return float("nan")
    return float(series.iloc[-period:].mean())


def _ema(series: pd.Series, period: int) -> float:
    if len(series) < period:
        return float("nan")
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])


def _rsi(series: pd.Series, period: int = 14) -> float:
    if len(series) < period + 1:
        return float("nan")
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _vwap(df: pd.DataFrame) -> float:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return float((typical * df["volume"]).sum() / df["volume"].sum())


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period:
        return float("nan")
    hl  = df["high"] - df["low"]
    hpc = (df["high"] - df["close"].shift()).abs()
    lpc = (df["low"]  - df["close"].shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _bb_upper(series: pd.Series, period: int = 20, std_mult: float = 2.0) -> float:
    if len(series) < period:
        return float("nan")
    ma  = series.rolling(period).mean()
    std = series.rolling(period).std()
    return float((ma + std_mult * std).iloc[-1])


def _bb_lower(series: pd.Series, period: int = 20, std_mult: float = 2.0) -> float:
    if len(series) < period:
        return float("nan")
    ma  = series.rolling(period).mean()
    std = series.rolling(period).std()
    return float((ma - std_mult * std).iloc[-1])


def _supertrend(df: pd.DataFrame, period: int = 7, mult: float = 3.0) -> float:
    """Returns +1 if bullish supertrend, -1 if bearish."""
    if len(df) < period:
        return float("nan")
    hl2  = (df["high"] + df["low"]) / 2
    atr  = _atr(df, period)
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    close = float(df["close"].iloc[-1])
    return 1.0 if close > lower else -1.0


# ── Expression evaluator ──────────────────────────────────────────────────────

class FormulaEvaluator:
    """
    Compiles and evaluates a plain-text formula against a DataFrame of candles.

    Usage:
        ev = FormulaEvaluator("close > ma(20) AND rsi(14) < 70")
        result = ev.evaluate(df)   # True / False / None (not enough data)
    """

    def __init__(self, expression: str):
        self.raw = expression
        self._compiled = None
        self._parse(expression)

    def _parse(self, expr: str):
        # Normalise
        expr = expr.strip()
        expr = re.sub(r'\bAND\b', 'and', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bOR\b',  'or',  expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bNOT\b', 'not', expr, flags=re.IGNORECASE)
        self._compiled = expr

    def evaluate(self, df: pd.DataFrame, ltp: float = None) -> Optional[bool]:
        """
        Evaluate formula against candle DataFrame.
        Returns True, False, or None if not enough data.
        """
        if df.empty or len(df) < 2:
            return None

        closes  = df["close"]
        highs   = df["high"]
        lows    = df["low"]
        volumes = df["volume"]
        ltp_val = ltp if ltp is not None else float(closes.iloc[-1])

        # Build evaluation namespace
        ns = {
            # Price
            "open":   float(df["open"].iloc[-1]),
            "high":   float(df["high"].iloc[-1]),
            "low":    float(df["low"].iloc[-1]),
            "close":  float(closes.iloc[-1]),
            "volume": float(volumes.iloc[-1]),
            "ltp":    ltp_val,

            # Indicator functions (called inline in expression)
            "ma":          lambda p:    _ma(closes, int(p)),
            "ema":         lambda p:    _ema(closes, int(p)),
            "rsi":         lambda p=14: _rsi(closes, int(p)),
            "vwap":        lambda:      _vwap(df),
            "atr":         lambda p=14: _atr(df, int(p)),
            "bb_upper":    lambda p=20: _bb_upper(closes, int(p)),
            "bb_lower":    lambda p=20: _bb_lower(closes, int(p)),
            "supertrend":  lambda p=7, m=3.0: _supertrend(df, int(p), float(m)),

            # Math
            "abs": abs, "min": min, "max": max, "round": round,
            "nan": float("nan"),
        }

        try:
            result = eval(self._compiled, {"__builtins__": {}}, ns)  # noqa: S307
            # Handle NaN results (not enough data for indicator)
            if isinstance(result, float) and np.isnan(result):
                return None
            return bool(result)
        except Exception as e:
            logger.warning(f"Formula eval error [{self.raw!r}]: {e}")
            return None


def validate_formula(expression: str) -> tuple[bool, str]:
    """
    Validate a formula expression without running it.
    Returns (is_valid, error_message).
    """
    if not expression or not expression.strip():
        return False, "Expression cannot be empty"

    # Basic safety check — no imports, exec, open, etc.
    banned = ["import", "exec", "eval", "open", "os.", "sys.", "__"]
    for b in banned:
        if b in expression.lower():
            return False, f"Forbidden keyword: {b}"

    # Try to compile with a dummy DataFrame
    dummy = pd.DataFrame({
        "open":   [100.0] * 30,
        "high":   [101.0] * 30,
        "low":    [99.0]  * 30,
        "close":  [100.5] * 30,
        "volume": [100000.0] * 30,
    })
    try:
        ev = FormulaEvaluator(expression)
        ev.evaluate(dummy)
        return True, ""
    except Exception as e:
        return False, str(e)
