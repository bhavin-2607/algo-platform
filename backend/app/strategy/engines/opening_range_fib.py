"""
Opening Range with Fibonacci Targets
=====================================
Exact Python translation of the Pine Script:
  "OPENING RANGE WITH FIBONACY 5"

Strategy Logic:
  - Anchors to the 9:15 AM opening price (dayOpen)
  - BUY  if LTP > dayOpen  →  entry = round((√dayOpen + 0.025)²)
  - SELL if LTP < dayOpen  →  entry = round((√dayOpen - 0.025)²)
  - SL   = entry ± 0.5%
  - Targets at Fibonacci % levels from dayOpen (T1–T9)

This file is SERVER-SIDE ONLY and is never exposed via any API.
"""
import math
import logging
from datetime import datetime, time
import pytz
import pandas as pd
from typing import Optional

from app.strategy.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# Fibonacci target levels (% above/below dayOpen)
FIB_LEVELS = [
    ("T1", 0.118),
    ("T2", 0.238),
    ("T3", 0.382),
    ("T4", 0.500),
    ("T5", 0.618),
    ("T6", 0.786),
    ("T7", 1.000),
    ("T8", 1.618),
    ("T9", 2.618),
]


class OpeningRangeFibonacci(BaseStrategy):
    """
    Opening Range with Fibonacci targets.
    Translates dad's Pine Script exactly into Python.

    params:
        symbol      (str)   — trading symbol
        exchange    (str)   — NSE / BSE / NFO
        quantity    (int)   — order quantity
        target_level(str)   — which Fibonacci level to use as exit target
                              e.g. "T3" (0.382%) or "T5" (0.618%)
        sl_pct      (float) — stop loss % (default 0.5)
    """

    def __init__(self, params: dict):
        super().__init__(params)
        self.symbol        = params.get("symbol", "NIFTY50")
        self.exchange      = params.get("exchange", "NSE")
        self.quantity      = int(params.get("quantity", 1))
        self.target_level  = params.get("target_level", "T3")   # default T3 = 0.382%
        self.sl_pct        = float(params.get("sl_pct", 0.5))

        # Runtime state
        self._day_open:   float | None = None
        self._direction:  str | None   = None   # "BUY" or "SELL"
        self._entry:      float | None = None
        self._sl:         float | None = None
        self._targets:    dict         = {}
        self._in_position: bool        = False
        self._signal_fired: bool       = False  # only fire once per day
        self._last_date:  str | None   = None

    def validate_params(self) -> bool:
        return self.quantity > 0

    def generate_signal(self, df: pd.DataFrame, ltp: float = None) -> Optional[Signal]:
        """
        Called on each candle close. Returns Signal or None.
        Accepts optional ltp for tick-level evaluation.
        """
        if df.empty:
            return None

        current_price = ltp if ltp is not None else float(df["close"].iloc[-1])
        now_ist       = datetime.now(IST)
        today_str     = now_ist.strftime("%Y-%m-%d")

        # ── Reset at new trading day ──────────────────────────────────────────
        if today_str != self._last_date:
            self._day_open     = None
            self._direction    = None
            self._entry        = None
            self._sl           = None
            self._targets      = {}
            self._in_position  = False
            self._signal_fired = False
            self._last_date    = today_str
            logger.info(f"[{self.symbol}] New day — reset state")

        # ── Capture 9:15 AM open ──────────────────────────────────────────────
        if self._day_open is None:
            market_open = time(9, 15)
            current_time = now_ist.time()
            if current_time >= market_open:
                # Use first candle's open as dayOpen
                self._day_open = float(df["open"].iloc[0])
                logger.info(f"[{self.symbol}] Day open captured: ₹{self._day_open}")
                self._compute_levels()

        if self._day_open is None:
            return None   # Market hasn't opened yet

        # ── Already in a position — wait for exit signal ──────────────────────
        if self._in_position:
            return None   # Managed by OrderManager (T/SL)

        # ── Only fire one signal per day ──────────────────────────────────────
        if self._signal_fired:
            return None

        # ── Determine direction ───────────────────────────────────────────────
        if current_price > self._day_open:
            direction = "BUY"
        elif current_price < self._day_open:
            direction = "SELL"
        else:
            return None

        # Direction change since last check?
        if direction == self._direction:
            return None  # Already evaluated this direction
        self._direction = direction

        # ── Recompute for current direction ───────────────────────────────────
        self._compute_levels()

        # ── Generate entry signal ─────────────────────────────────────────────
        entry  = self._entry
        sl     = self._sl
        target = self._targets.get(self.target_level)

        if entry is None:
            return None

        logger.info(
            f"[{self.symbol}] {direction} signal | "
            f"Entry=₹{entry} SL=₹{sl} {self.target_level}=₹{target}"
        )

        self._signal_fired = True

        return Signal(
            symbol     = self.symbol,
            exchange   = self.exchange,
            direction  = direction,
            quantity   = self.quantity,
            order_type = "LIMIT",
            price      = entry,
            sl         = sl,
            target     = target,
            reason     = (
                f"ORFib {direction} | Open=₹{self._day_open} "
                f"Entry=₹{entry} SL=₹{sl} {self.target_level}=₹{target}"
            ),
        )

    def on_order_filled(self, signal: Signal, fill_price: float):
        self._in_position = True
        logger.info(f"[{self.symbol}] Order filled @ ₹{fill_price}")

    def get_levels(self, day_open: float | None = None) -> dict:
        """
        Returns all computed levels for display in the terminal.
        Optionally recompute for a given dayOpen (for UI preview).
        """
        if day_open is not None:
            self._day_open = day_open
            self._compute_levels()

        return {
            "day_open":   self._day_open,
            "direction":  self._direction,
            "buy_entry":  self._buy_entry(),
            "sell_entry": self._sell_entry(),
            "buy_sl":     self._buy_sl(),
            "sell_sl":    self._sell_sl(),
            "buy_targets": {
                label: round(self._day_open + self._day_open * pct / 100, 2)
                for label, pct in FIB_LEVELS
                if self._day_open
            },
            "sell_targets": {
                label: round(self._day_open - self._day_open * pct / 100, 2)
                for label, pct in FIB_LEVELS
                if self._day_open
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _compute_levels(self):
        if not self._day_open:
            return

        if self._direction == "BUY" or self._direction is None:
            self._entry = self._buy_entry()
            self._sl    = self._buy_sl()
            self._targets = {
                label: round(self._day_open + self._day_open * pct / 100, 2)
                for label, pct in FIB_LEVELS
            }
        else:
            self._entry = self._sell_entry()
            self._sl    = self._sell_sl()
            self._targets = {
                label: round(self._day_open - self._day_open * pct / 100, 2)
                for label, pct in FIB_LEVELS
            }

    def _buy_entry(self) -> float | None:
        if not self._day_open:
            return None
        return round(math.pow(math.sqrt(self._day_open) + 0.025, 2))

    def _sell_entry(self) -> float | None:
        if not self._day_open:
            return None
        return round(math.pow(math.sqrt(self._day_open) - 0.025, 2))

    def _buy_sl(self) -> float | None:
        e = self._buy_entry()
        return round(e * (1 - self.sl_pct / 100), 2) if e else None

    def _sell_sl(self) -> float | None:
        e = self._sell_entry()
        return round(e * (1 + self.sl_pct / 100), 2) if e else None
