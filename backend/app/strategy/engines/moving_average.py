"""
Example strategy: Simple Moving Average Crossover.
This file is server-side only — never exposed to users.
"""
import pandas as pd
from typing import Optional
from app.strategy.base import BaseStrategy, Signal


class MovingAverageCrossover(BaseStrategy):
    """
    Generates a BUY signal when fast MA crosses above slow MA,
    and a SELL signal when it crosses below.

    params:
        symbol    (str)  — trading symbol, e.g. "RELIANCE"
        exchange  (str)  — e.g. "NSE"
        fast      (int)  — fast MA period (default 9)
        slow      (int)  — slow MA period (default 21)
        quantity  (int)  — order quantity
    """

    def __init__(self, params: dict):
        super().__init__(params)
        self.fast = int(params.get("fast", 9))
        self.slow = int(params.get("slow", 21))
        self.symbol = params["symbol"]
        self.exchange = params["exchange"]
        self.quantity = int(params.get("quantity", 1))
        self._position = 0  # 1 = long, -1 = short, 0 = flat

    def validate_params(self) -> bool:
        return self.fast < self.slow and self.quantity > 0

    def generate_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        if len(df) < self.slow + 1:
            return None

        df = df.copy()
        df["fast_ma"] = df["close"].rolling(self.fast).mean()
        df["slow_ma"] = df["close"].rolling(self.slow).mean()

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        # Bullish crossover
        if prev["fast_ma"] <= prev["slow_ma"] and curr["fast_ma"] > curr["slow_ma"]:
            if self._position != 1:
                return Signal(
                    symbol=self.symbol,
                    exchange=self.exchange,
                    direction="BUY",
                    quantity=self.quantity,
                    reason=f"MA crossover: {self.fast}>{self.slow}",
                )

        # Bearish crossover
        if prev["fast_ma"] >= prev["slow_ma"] and curr["fast_ma"] < curr["slow_ma"]:
            if self._position == 1:
                return Signal(
                    symbol=self.symbol,
                    exchange=self.exchange,
                    direction="SELL",
                    quantity=self.quantity,
                    reason=f"MA crossunder: {self.fast}<{self.slow}",
                )

        return None

    def on_order_filled(self, signal: Signal, fill_price: float) -> None:
        if signal.direction == "BUY":
            self._position = 1
        elif signal.direction == "SELL":
            self._position = 0
