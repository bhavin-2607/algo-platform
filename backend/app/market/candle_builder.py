"""
Candle Builder
==============
Aggregates raw ticks from an in-memory buffer into OHLCV candles
of any timeframe and returns a pandas DataFrame ready for strategy use.
"""
import logging
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

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


def _ticks_to_ohlcv(
    exchange: str,
    token: str,
    timeframe_minutes: int = 5,
) -> pd.DataFrame:
    """Resample buffered ticks into OHLCV (includes the incomplete current bucket)."""
    key = f"{exchange}:{token}"
    ticks = _tick_buffer.get(key, [])

    if not ticks:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(ticks)
    df["ts"]  = pd.to_numeric(df["ts"], errors="coerce")
    df["ltp"] = pd.to_numeric(df["ltp"], errors="coerce")
    if "volume" not in df.columns:
        df["volume"] = 0
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = df.dropna(subset=["ts", "ltp"])
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df["datetime"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    df = df.set_index("datetime").sort_index()

    freq = f"{timeframe_minutes}min"
    ohlcv = df["ltp"].resample(freq).ohlc()
    ohlcv["volume"] = df["volume"].resample(freq).sum()
    ohlcv = ohlcv.dropna(subset=["open", "high", "low", "close"])
    return ohlcv.rename(columns={
        "open": "open", "high": "high", "low": "low", "close": "close"
    })


def build_ohlcv(
    exchange: str,
    token: str,
    timeframe_minutes: int = 5,
    num_candles: int = 100,
) -> pd.DataFrame:
    """
    Build OHLCV DataFrame from the in-memory tick buffer.

    Includes the incomplete in-progress bucket (last row may still be forming).
    Prefer build_ohlcv_closed() for strategy signal evaluation.

    Returns DataFrame with columns: [open, high, low, close, volume]
    indexed by candle timestamp.
    """
    ohlcv = _ticks_to_ohlcv(exchange, token, timeframe_minutes)
    if ohlcv.empty:
        return ohlcv
    return ohlcv.tail(num_candles)


def build_ohlcv_closed(
    exchange: str,
    token: str,
    timeframe_minutes: int = 5,
    num_candles: int = 100,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Build OHLCV using only fully closed bars.

    Drops the incomplete current time bucket so strategies evaluate on bar close,
    not mid-candle noise.
    """
    ohlcv = _ticks_to_ohlcv(exchange, token, timeframe_minutes)
    if ohlcv.empty:
        return ohlcv

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Bucket start for the in-progress candle
    # Floor now to timeframe
    epoch = int(now.timestamp())
    bucket_secs = timeframe_minutes * 60
    current_bucket_start = pd.Timestamp(epoch - (epoch % bucket_secs), unit="s", tz="UTC")

    # Keep bars whose index (bucket start) is strictly before the current bucket
    closed = ohlcv[ohlcv.index < current_bucket_start]
    return closed.tail(num_candles)


def latest_closed_bar_ts(df: pd.DataFrame):
    """Return the timestamp of the last closed bar, or None if empty."""
    if df is None or df.empty:
        return None
    return df.index[-1]
