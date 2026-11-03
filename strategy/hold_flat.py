"""Drop-in engine. Paper-test it, then an admin enables that version for live."""
from app.strategy.base import BaseStrategy


class HoldFlat(BaseStrategy):
    engine_id = "hold_flat"
    version = "1"
    warmup_bars = 1
    max_positions = 0

    def generate_signal(self, df):
        return None

    def on_order_filled(self, signal, fill_price: float) -> None:
        return
