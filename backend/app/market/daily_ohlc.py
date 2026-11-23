"""
Daily OHLC & Previous Day Market Data Service
============================================
Fetches, caches, and provides accurate previous day market data:
  - Previous High  (p_high)
  - Previous Low   (p_low)
  - Previous Close (p_close)
  - Previous Open  (p_open)

Directly from DhanHQ v2 /charts/historical daily candles.
Cached in memory and Redis for 24 hours to strictly respect rate limits.
"""
from __future__ import annotations

import os
import csv
import time
import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import requests
from app.core.config import settings

logger = logging.getLogger(__name__)

DHAN_HISTORICAL_URL = "https://api.dhan.co/v2/charts/historical"

# In-memory cache: (segment, security_id) -> dict
_MEMORY_CACHE: Dict[tuple[str, str], Dict[str, Any]] = {}

# Fast mapping of (segment, security_id) -> instrument type
_INSTRUMENT_MAP: Dict[tuple[str, str], str] = {}
_INSTRUMENT_MAP_LOADED = False

# Background fetch queue
_FETCH_QUEUE: asyncio.Queue = asyncio.Queue()
_QUEUED_KEYS: set = set()
_WORKER_TASK: Optional[asyncio.Task] = None

# IST timezone helper
IST = timezone(timedelta(hours=5, minutes=30))


def _load_instrument_map():
    global _INSTRUMENT_MAP, _INSTRUMENT_MAP_LOADED
    if _INSTRUMENT_MAP_LOADED:
        return
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "instruments.csv"))
    if not os.path.isfile(csv_path):
        _INSTRUMENT_MAP_LOADED = True
        return
    try:
        mapping = {}
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) > 4:
                    exch, seg, sid, inst = row[0], row[1], row[2], row[4]
                    dhan_seg = None
                    if exch == "NSE" and seg == "E":
                        dhan_seg = "NSE_EQ"
                    elif exch == "NSE" and seg == "D":
                        dhan_seg = "NSE_FNO"
                    elif exch == "BSE" and seg == "E":
                        dhan_seg = "BSE_EQ"
                    elif exch == "BSE" and seg == "D":
                        dhan_seg = "BSE_FNO"
                    elif exch == "MCX" and seg == "M":
                        dhan_seg = "MCX_COMM"
                    elif seg in ("I", "IDX") or exch in ("IDX", "INDEX"):
                        dhan_seg = "IDX_I"
                    if dhan_seg and sid:
                        mapping[(dhan_seg, sid)] = inst
        _INSTRUMENT_MAP = mapping
        _INSTRUMENT_MAP_LOADED = True
        logger.info(f"Loaded {len(_INSTRUMENT_MAP)} instrument mappings for daily OHLC")
    except Exception as e:
        logger.warning(f"Failed to load instrument map: {e}")
        _INSTRUMENT_MAP_LOADED = True


def resolve_instrument_type(segment: str, security_id: str, symbol: str = "") -> str:
    """Resolve the Dhan instrument string needed for /charts/historical."""
    _load_instrument_map()
    inst = _INSTRUMENT_MAP.get((segment, str(security_id)))
    if inst:
        return inst

    seg = str(segment).upper()
    sym = str(symbol).upper()
    if seg == "IDX_I" or ("NIFTY" in sym or "SENSEX" in sym and ":" not in sym and not any(k in sym for k in ("CALL", "PUT", "CE", "PE", "FUT"))):
        return "INDEX"
    if seg in ("NSE_EQ", "BSE_EQ"):
        return "EQUITY"
    if seg in ("MCX_COMM", "NSE_COMM"):
        if any(k in sym for k in ("CALL", "PUT", "CE", "PE", "OPT")):
            return "OPTFUT"
        return "FUTCOM"
    if seg in ("NSE_FNO", "BSE_FNO"):
        is_index = any(k in sym for k in ("NIFTY", "BANKNIFTY", "SENSEX", "BANKEX", "FINNIFTY", "MIDCPNIFTY"))
        is_opt = any(k in sym for k in ("CALL", "PUT", "CE", "PE", "OPT"))
        if is_index:
            return "OPTIDX" if is_opt else "FUTIDX"
        return "OPTSTK" if is_opt else "FUTSTK"
    return "EQUITY"


def get_previous_day_ohlc(segment: str, security_id: str) -> Optional[Dict[str, Any]]:
    """Instant lookup from memory cache."""
    return _MEMORY_CACHE.get((str(segment), str(security_id)))


def set_cached_previous_day_ohlc(segment: str, security_id: str, data: Dict[str, Any]):
    """Store in memory cache."""
    _MEMORY_CACHE[(str(segment), str(security_id))] = data


async def _get_from_redis(seg: str, sid: str) -> Optional[dict]:
    """Retrieve daily OHLC from Redis."""
    try:
        from app.core.redis_client import get_redis
        r = get_redis()
        raw = await r.get(f"daily_ohlc:{seg}:{sid}")
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.debug(f"Redis get daily_ohlc failed: {e}")
    return None


async def _save_to_redis(seg: str, sid: str, data: dict):
    """Store daily OHLC in Redis for 24 hours."""
    try:
        from app.core.redis_client import get_redis
        r = get_redis()
        await r.set(f"daily_ohlc:{seg}:{sid}", json.dumps(data), ex=86400)
    except Exception as e:
        logger.debug(f"Redis set daily_ohlc failed: {e}")


def fetch_previous_day_ohlc_sync(segment: str, security_id: str, symbol: str = "") -> Optional[Dict[str, Any]]:
    """
    Fetch exact previous trading session OHLC from Dhan /charts/historical.
    Returns dict with keys: symbol, segment, security_id, p_open, p_high, p_low, p_close, date.
    """
    token = getattr(settings, "DHAN_ACCESS_TOKEN", None)
    client_id = getattr(settings, "DHAN_CLIENT_ID", None)
    if not token or not client_id:
        return None

    sid = str(security_id)
    seg = str(segment)
    inst = resolve_instrument_type(seg, sid, symbol)

    today = datetime.now()
    from_date = (today - timedelta(days=12)).strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")

    payload = {
        "securityId": sid,
        "exchangeSegment": seg,
        "instrument": inst,
        "expiryCode": 0,
        "fromDate": from_date,
        "toDate": to_date,
    }
    headers = {
        "access-token": token,
        "client-id": client_id,
        "dhanClientId": client_id,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        resp = requests.post(DHAN_HISTORICAL_URL, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            ts_list = data.get("timestamp", [])
            candles = len(ts_list)
            if candles > 0:
                # Find previous trading session (strictly before today in IST)
                today_ist = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
                cand_idx = candles - 1
                last_dt = datetime.fromtimestamp(ts_list[cand_idx], tz=timezone.utc).strftime("%Y-%m-%d")
                if last_dt >= today_ist and cand_idx > 0:
                    cand_idx -= 1

                p_high = float(data["high"][cand_idx])
                p_low = float(data["low"][cand_idx])
                p_close = float(data["close"][cand_idx])
                p_open = float(data["open"][cand_idx])
                ts = ts_list[cand_idx]
                dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

                res = {
                    "symbol": symbol,
                    "segment": seg,
                    "security_id": sid,
                    "p_open": p_open,
                    "p_high": p_high,
                    "p_low": p_low,
                    "p_close": p_close,
                    "date": dt_str,
                }
                set_cached_previous_day_ohlc(seg, sid, res)
                logger.info(f"Loaded real previous day OHLC for {symbol or sid} ({seg}): High={p_high}, Low={p_low}, Close={p_close} (Date: {dt_str})")
                return res
        else:
            logger.debug(f"charts/historical returned {resp.status_code} for {seg}:{sid}: {resp.text[:100]}")
    except Exception as e:
        logger.debug(f"charts/historical fetch error for {seg}:{sid}: {e}")
    return None


def enqueue_daily_ohlc_fetch(segment: str, security_id: str, symbol: str = ""):
    """Enqueue a symbol to be fetched in background at a safe rate."""
    key = (str(segment), str(security_id))
    if key in _MEMORY_CACHE or key in _QUEUED_KEYS:
        return
    _QUEUED_KEYS.add(key)
    try:
        _FETCH_QUEUE.put_nowait((str(segment), str(security_id), str(symbol)))
    except Exception:
        pass


async def _worker_loop():
    """Background rate-limited worker fetching 1 chart per 1.1 seconds."""
    while True:
        try:
            seg, sid, sym = await _FETCH_QUEUE.get()
            key = (seg, sid)
            if key not in _MEMORY_CACHE:
                # Check Redis first
                redis_data = await _get_from_redis(seg, sid)
                if redis_data:
                    _MEMORY_CACHE[key] = redis_data
                else:
                    loop = asyncio.get_event_loop()
                    res = await loop.run_in_executor(None, fetch_previous_day_ohlc_sync, seg, sid, sym)
                    if res:
                        await _save_to_redis(seg, sid, res)
                    await asyncio.sleep(1.1)
            _QUEUED_KEYS.discard(key)
            _FETCH_QUEUE.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Daily OHLC worker loop exception: {e}")
            await asyncio.sleep(1.0)


def start_daily_ohlc_worker():
    """Ensure the background worker is running."""
    global _WORKER_TASK
    if _WORKER_TASK is None or _WORKER_TASK.done():
        try:
            _WORKER_TASK = asyncio.create_task(_worker_loop())
            logger.info("Daily OHLC background worker started")
        except RuntimeError:
            pass


async def preload_daily_ohlc():
    """Pre-warm cache on application startup for all watchlist and algo symbols."""
    start_daily_ohlc_worker()
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.watchlist import UserWatchlist
        from app.models.algo_row import BsaAlgoRow
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            wl = (await db.execute(select(UserWatchlist))).scalars().all()
            for item in wl:
                if item.security_id and str(item.security_id) != "0":
                    seg = item.exchange_segment or "NSE_EQ"
                    sid = str(item.security_id)
                    cached = await _get_from_redis(seg, sid)
                    if cached:
                        set_cached_previous_day_ohlc(seg, sid, cached)
                    else:
                        enqueue_daily_ohlc_fetch(seg, sid, item.symbol)

            rows = (await db.execute(select(BsaAlgoRow))).scalars().all()
            for row in rows:
                if row.token and str(row.token) != "0":
                    seg = row.segment or "NSE_EQ"
                    sid = str(row.token)
                    cached = await _get_from_redis(seg, sid)
                    if cached:
                        set_cached_previous_day_ohlc(seg, sid, cached)
                    else:
                        enqueue_daily_ohlc_fetch(seg, sid, row.symbol)
        logger.info("Preloaded daily OHLC items from database into queue/cache")
    except Exception as e:
        logger.warning(f"preload_daily_ohlc failed: {e}")
