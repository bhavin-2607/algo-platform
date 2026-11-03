from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    symbol: str
    exchange: str
    direction: str              # "BUY" | "SELL" | "HOLD"
    quantity: int
    order_type: str = "MARKET"
    price: Optional[float] = None
    sl: Optional[float] = None       # stop loss price
    target: Optional[float] = None   # target price
    reason: str = ""


class BaseStrategy(ABC):
    """
    All trading strategies extend this class.
    Strategy logic is kept entirely server-side and is never
    serialised or returned via any API endpoint.
    """

    engine_id: str = ""
    version: str = "1"
    warmup_bars: int = 1
    max_positions: int = 1

    def __init__(self, params: dict):
        self.params = params

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        """
        Receive a DataFrame of OHLCV market data.
        Return a Signal to trade or None to hold.
        """
        ...

    @abstractmethod
    def on_order_filled(self, signal: Signal, fill_price: float) -> None:
        """Called by the engine when a placed order is confirmed filled."""
        ...

    def validate_params(self) -> bool:
        """Override to validate strategy-specific params."""
        return True

    def restore_position(self, direction: str, quantity: int) -> None:
        """Rebuild in-memory position after a restart. Default: no open position."""
        return
