"""
Candle Builder
==============
Aggregates raw 1-second ticks from Redis into OHLCV candles
of any timeframe and returns a pandas DataFrame ready for strategy use.
"""
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from app.core.redis_client import get_redis, tick_channel

logger = logging.getLogger(__name__)

# In-memory tick buffer: key → list of tick dicts
_tick_buffer: dict[str, list[dict]] = {}
MAX_BUFFER = 5000  # max ticks per instrument


def record_tick(exchange: str, token: str, tick: dict):
    """Called by the subscriber to add a tick to the in-memory buffer."""
    key = f"{exchange}:{token}"
    buf = _tick_buffer.setdefault(key, [])
    buf.append(tick)
    if len(buf) > MAX_BUFFER:
        _tick_buffer[key] = buf[-MAX_BUFFER:]


def build_ohlcv(
    exchange: str,
    token: str,
    timeframe_minutes: int = 5,
    num_candles: int = 100,
) -> pd.DataFrame:
    """
    Build OHLCV DataFrame from the in-memory tick buffer.

    Returns DataFrame with columns: [open, high, low, close, volume]
    indexed by candle timestamp. Suitable for passing to BaseStrategy.generate_signal().
    """
    key = f"{exchange}:{token}"
    ticks = _tick_buffer.get(key, [])

    if not ticks:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    # Convert to DataFrame
    df = pd.DataFrame(ticks)
    df["ts"]  = pd.to_numeric(df["ts"], errors="coerce")
    df["ltp"] = pd.to_numeric(df["ltp"], errors="coerce")
    df = df.dropna(subset=["ts", "ltp"])
    df["datetime"] = pd.to_datetime(df["ts"], unit="s")
    df = df.set_index("datetime").sort_index()

    # Resample into OHLCV candles
    freq = f"{timeframe_minutes}min"
    ohlcv = df["ltp"].resample(freq).ohlc()
    ohlcv["volume"] = df["volume"].resample(freq).sum()
    ohlcv = ohlcv.dropna()

    return ohlcv.tail(num_candles).rename(columns={
        "open": "open", "high": "high", "low": "low", "close": "close"
    })
