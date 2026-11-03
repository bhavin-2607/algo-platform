"""Dhan intraday history. No synthetic fallback."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import pandas as pd
import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

DHAN_CHARTS = "https://api.dhan.co/v2/charts/intraday"
_ALLOWED_INTERVALS = {"1", "5", "15", "25", "60"}


def _csv_path() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "instruments.csv"))


def resolve_security(symbol: str, exchange: str) -> dict:
    """Map a symbol to a Dhan security id using the local instrument file."""
    path = _csv_path()
    if not os.path.isfile(path):
        raise FileNotFoundError("Instrument file is missing")
    df = pd.read_csv(
        path,
        usecols=["EXCH_ID", "SECURITY_ID", "SYMBOL_NAME", "UNDERLYING_SYMBOL", "SERIES", "INSTRUMENT"],
        low_memory=False,
    )
    sym = symbol.upper().strip()
    exch = exchange.upper().strip()
    exch = {"NSE_EQ": "NSE", "BSE_EQ": "BSE"}.get(exch, exch)
    frame = df[df["EXCH_ID"] == exch]
    names = frame["SYMBOL_NAME"].astype(str).str.upper()
    exact = frame[names == sym]
    eq = exact[exact["SERIES"] == "EQ"]
    row = eq.iloc[0] if not eq.empty else (exact.iloc[0] if not exact.empty else None)
    if row is None:
        # Dhan's equity master stores the trading symbol on UNDERLYING_SYMBOL
        # and the company name on SYMBOL_NAME ("RELIANCE" vs "RELIANCE INDUSTRIES LTD").
        underlying = frame["UNDERLYING_SYMBOL"].astype(str).str.upper()
        cash = frame[(underlying == sym) & (frame["INSTRUMENT"].astype(str).str.upper() == "EQUITY")]
        cash_eq = cash[cash["SERIES"] == "EQ"]
        picked = cash_eq if not cash_eq.empty else cash
        row = picked.iloc[0] if not picked.empty else None
    if row is None:
        raise LookupError(f"No instrument for {exch}:{sym}")
    instrument = str(row["INSTRUMENT"]).upper()
    if instrument in {"INDEX", "IDX"}:
        segment, kind = "IDX_I", "INDEX"
    elif exch == "BSE":
        segment, kind = "BSE_EQ", "EQUITY"
    else:
        segment, kind = "NSE_EQ", "EQUITY"
    sid = row["SECURITY_ID"]
    try:
        security_id = str(int(float(sid)))
    except (TypeError, ValueError):
        security_id = str(sid)
    return {
        "security_id": security_id,
        "exchange_segment": segment,
        "instrument": kind,
    }


def fetch_intraday_candles(symbol: str, exchange: str, interval_min: int, bars: int) -> list[dict]:
    """Return oldest-first OHLCV dicts from Dhan. Raises if the broker has no data."""
    if not settings.DHAN_CLIENT_ID or not settings.DHAN_ACCESS_TOKEN:
        raise RuntimeError("Historical candles require DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN")

    security = resolve_security(symbol, exchange)
    interval = str(interval_min) if str(interval_min) in _ALLOWED_INTERVALS else "5"
    # Intraday history is requested as a window wide enough for the bar count.
    minutes = int(interval) * max(int(bars), 1)
    days = max(5, min(90, minutes // (6 * 60) + 3))
    end = datetime.now()
    start = end - timedelta(days=days)
    body = {
        "securityId": security["security_id"],
        "exchangeSegment": security["exchange_segment"],
        "instrument": security["instrument"],
        "interval": interval,
        "fromDate": start.strftime("%Y-%m-%d %H:%M:%S"),
        "toDate": end.strftime("%Y-%m-%d %H:%M:%S"),
    }
    resp = requests.post(
        DHAN_CHARTS,
        json=body,
        headers={
            "access-token": settings.DHAN_ACCESS_TOKEN,
            "dhanClientId": settings.DHAN_CLIENT_ID,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Dhan history HTTP {resp.status_code}")
    payload = resp.json()
    if isinstance(payload, dict) and payload.get("errorCode"):
        raise RuntimeError(payload.get("errorMessage") or payload.get("errorCode"))

    opens = payload.get("open") or []
    highs = payload.get("high") or []
    lows = payload.get("low") or []
    closes = payload.get("close") or []
    volumes = payload.get("volume") or []
    stamps = payload.get("timestamp") or payload.get("start_Time") or []
    count = min(len(opens), len(highs), len(lows), len(closes), len(stamps))
    candles = []
    for i in range(count):
        raw_ts = stamps[i]
        ts = int(raw_ts) if not isinstance(raw_ts, str) else int(datetime.fromisoformat(raw_ts).timestamp())
        candles.append({
            "time": ts,
            "open": float(opens[i]),
            "high": float(highs[i]),
            "low": float(lows[i]),
            "close": float(closes[i]),
            "volume": float(volumes[i]) if i < len(volumes) else 0.0,
        })
    candles.sort(key=lambda bar: bar["time"])
    if bars and len(candles) > bars:
        candles = candles[-bars:]
    if not candles:
        raise RuntimeError(f"Dhan returned no candles for {symbol}")
    return candles
