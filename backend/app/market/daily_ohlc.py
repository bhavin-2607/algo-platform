"""
Daily OHLC & Previous Day Market Data Service
============================================
Fetches, caches, and provides accurate previous day market data:
  - Previous High  (p_high)
  - Previous Low   (p_low)
  - Previous Close (p_close)
  - Previous Open  (p_open)

Directly from DhanHQ v2 /charts/historical daily candles.
Cache is strictly date-aware (for_date == today_ist) so it always serves
the true previous trading session and automatically invalidates at midnight.
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

# In-memory cache: (segment, security_id) -> dict with 'for_date'
_MEMORY_CACHE: Dict[tuple[str, str], Dict[str, Any]] = {}

# Fast mapping of (segment, security_id) -> instrument type
_INSTRUMENT_MAP: Dict[tuple[str, str], str] = {}
_INSTRUMENT_MAP_LOADED = False

# Background fetch queue
_FETCH_QUEUE: asyncio.Queue = asyncio.Queue()
_QUEUED_KEYS: set = set()
_WORKER_TASK: Optional[asyncio.Task] = None

# Indian Standard Time (IST) timezone
IST = timezone(timedelta(hours=5, minutes=30))


def get_today_ist() -> str:
    """Return current date string in IST (YYYY-MM-DD)."""
    return datetime.now(tz=IST).strftime("%Y-%m-%d")


def clear_daily_ohlc_cache():
    """Clear memory cache and queued keys."""
    global _MEMORY_CACHE, _QUEUED_KEYS
    _MEMORY_CACHE.clear()
    _QUEUED_KEYS.clear()
    logger.info("Cleared daily OHLC memory cache")


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
    """
    Instant lookup from memory cache.
    Ensures that the cached candle is valid for today's trading day (for_date == today_ist).
    """
    today_ist = get_today_ist()
    key = (str(segment), str(security_id))
    cached = _MEMORY_CACHE.get(key)
    if cached:
        if cached.get("for_date") == today_ist:
            return cached
        # Stale cache from a previous day - remove it so worker re-fetches
        _MEMORY_CACHE.pop(key, None)
    return None


def set_cached_previous_day_ohlc(segment: str, security_id: str, data: Dict[str, Any]):
    """Store in memory cache with today's date stamp."""
    data["for_date"] = get_today_ist()
    _MEMORY_CACHE[(str(segment), str(security_id))] = data


async def _get_from_redis(seg: str, sid: str) -> Optional[dict]:
    """Retrieve daily OHLC from Redis strictly for today_ist."""
    today_ist = get_today_ist()
    try:
        from app.core.redis_client import get_redis
        r = get_redis()
        raw = await r.get(f"daily_ohlc:{today_ist}:{seg}:{sid}")
        if raw:
            data = json.loads(raw)
            if data.get("for_date") == today_ist:
                return data
    except Exception as e:
        logger.debug(f"Redis get daily_ohlc failed: {e}")
    return None


async def _save_to_redis(seg: str, sid: str, data: dict):
    """Store daily OHLC in Redis for 24 hours under today_ist key."""
    today_ist = get_today_ist()
    try:
        from app.core.redis_client import get_redis
        r = get_redis()
        await r.set(f"daily_ohlc:{today_ist}:{seg}:{sid}", json.dumps(data), ex=86400)
    except Exception as e:
        logger.debug(f"Redis set daily_ohlc failed: {e}")


def fetch_previous_day_ohlc_sync(segment: str, security_id: str, symbol: str = "") -> Optional[Dict[str, Any]]:
    """
    Fetch exact previous trading session OHLC from Dhan /charts/historical.
    Iterates candles in reverse to find the latest candle strictly before today (IST).
    Returns dict with keys: symbol, segment, security_id, p_open, p_high, p_low, p_close, candle_date, for_date.
    """
    token = getattr(settings, "DHAN_ACCESS_TOKEN", None)
    client_id = getattr(settings, "DHAN_CLIENT_ID", None)
    if not token or not client_id:
        return None

    sid = str(security_id)
    seg = str(segment)
    inst = resolve_instrument_type(seg, sid, symbol)

    today_now = datetime.now(tz=IST)
    today_ist = today_now.strftime("%Y-%m-%d")
    from_date = (today_now - timedelta(days=12)).strftime("%Y-%m-%d")
    to_date = (today_now + timedelta(days=1)).strftime("%Y-%m-%d")

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
                # Find the most recent candle whose IST date is strictly before today_ist
                target_idx = None
                for i in range(candles - 1, -1, -1):
                    c_date_ist = datetime.fromtimestamp(ts_list[i], tz=IST).strftime("%Y-%m-%d")
                    if c_date_ist < today_ist:
                        target_idx = i
                        break

                if target_idx is None:
                    target_idx = max(0, candles - 2) if candles > 1 else candles - 1

                p_high = float(data["high"][target_idx])
                p_low = float(data["low"][target_idx])
                p_close = float(data["close"][target_idx])
                p_open = float(data["open"][target_idx])
                candle_ts = ts_list[target_idx]
                candle_date_str = datetime.fromtimestamp(candle_ts, tz=IST).strftime("%Y-%m-%d")

                res = {
                    "symbol": symbol,
                    "segment": seg,
                    "security_id": sid,
                    "p_open": p_open,
                    "p_high": p_high,
                    "p_low": p_low,
                    "p_close": p_close,
                    "candle_date": candle_date_str,
                    "for_date": today_ist,
                    "date": candle_date_str,
                }
                set_cached_previous_day_ohlc(seg, sid, res)
                logger.info(
                    f"Loaded real previous day OHLC for {symbol or sid} ({seg}): "
                    f"High={p_high}, Low={p_low}, Close={p_close} (Candle Date: {candle_date_str}, For: {today_ist})"
                )
                return res
        else:
            logger.debug(f"charts/historical returned {resp.status_code} for {seg}:{sid}: {resp.text[:100]}")
    except Exception as e:
        logger.debug(f"charts/historical fetch error for {seg}:{sid}: {e}")
    return None


def enqueue_daily_ohlc_fetch(segment: str, security_id: str, symbol: str = ""):
    """Enqueue a symbol to be fetched in background at a safe rate."""
    today_ist = get_today_ist()
    key = (str(segment), str(security_id))
    cached = _MEMORY_CACHE.get(key)
    if cached and cached.get("for_date") == today_ist:
        return
    if key in _QUEUED_KEYS:
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
            today_ist = get_today_ist()
            cached = _MEMORY_CACHE.get(key)

            if not cached or cached.get("for_date") != today_ist:
                # Check Redis first for today's date
                redis_data = await _get_from_redis(seg, sid)
                if redis_data and redis_data.get("for_date") == today_ist:
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
    today_ist = get_today_ist()
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
                    if cached and cached.get("for_date") == today_ist:
                        set_cached_previous_day_ohlc(seg, sid, cached)
                    else:
                        enqueue_daily_ohlc_fetch(seg, sid, item.symbol)

            from app.market.market_poller import get_poller
            poller = get_poller()
            rows = (await db.execute(select(BsaAlgoRow))).scalars().all()
            has_active_algo = False
            for row in rows:
                if row.token and str(row.token) != "0":
                    seg = row.segment or "NSE_EQ"
                    sid = str(row.token)
                    poller.add_symbol(row.symbol, sid, seg)
                    if row.is_algo_active:
                        has_active_algo = True
                    cached = await _get_from_redis(seg, sid)
                    if cached and cached.get("for_date") == today_ist:
                        set_cached_previous_day_ohlc(seg, sid, cached)
                    else:
                        enqueue_daily_ohlc_fetch(seg, sid, row.symbol)
            if has_active_algo:
                poller.ensure_started()
        logger.info(f"Preloaded daily OHLC items from database for {today_ist}")
    except Exception as e:
        logger.warning(f"preload_daily_ohlc failed: {e}")
