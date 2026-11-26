"""
Market Data Routes — serves OHLCV candles, quotes and instrument search.
"""
import asyncio
import logging
import random
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

_SCRIP_CACHE: dict = {"mtime": None, "frame": None}


def _scrip_frame():
    """Scrip master has ~225k rows. Read it once per file change and prepare search indexes."""
    import os
    import pandas as pd
    csv_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "../../market/instruments.csv"
    ))
    mtime = os.path.getmtime(csv_path)
    if _SCRIP_CACHE["frame"] is not None and _SCRIP_CACHE["mtime"] == mtime:
        return _SCRIP_CACHE["frame"]
    frame = pd.read_csv(csv_path, header=0, low_memory=False)

    # Pre-clean string columns for fast search
    disp = frame["DISPLAY_NAME"].fillna("").astype(str).str.upper()
    sym = frame["SYMBOL_NAME"].fillna("").astype(str).str.upper()
    und = frame["UNDERLYING_SYMBOL"].fillna("").astype(str).str.upper()
    inst = frame["INSTRUMENT"].fillna("").astype(str).str.upper()
    opt = frame["OPTION_TYPE"].fillna("").astype(str).str.upper()
    exch = frame["EXCH_ID"].fillna("").astype(str).str.upper()
    srs = frame["SERIES"].fillna("").astype(str).str.upper()
    opt_aliases = opt.map({"CE": "CE CALL", "PE": "PE PUT"}).fillna("")

    frame["SEARCH_BLOB"] = (disp + " " + sym + " " + und + " " + inst + " " + opt_aliases + " " + exch + " " + srs).values
    _SCRIP_CACHE["mtime"] = mtime
    _SCRIP_CACHE["frame"] = frame
    return frame

INSTRUMENTS = {
    "RELIANCE":   {"name": "Reliance Industries",        "base": 2850,  "sector": "Energy"},
    "TCS":        {"name": "Tata Consultancy Services",  "base": 3920,  "sector": "IT"},
    "INFY":       {"name": "Infosys",                    "base": 1540,  "sector": "IT"},
    "HDFCBANK":   {"name": "HDFC Bank",                  "base": 1680,  "sector": "Banking"},
    "ICICIBANK":  {"name": "ICICI Bank",                 "base": 1120,  "sector": "Banking"},
    "WIPRO":      {"name": "Wipro",                      "base": 480,   "sector": "IT"},
    "SBIN":       {"name": "State Bank of India",        "base": 820,   "sector": "Banking"},
    "TATAMOTORS": {"name": "Tata Motors",                "base": 960,   "sector": "Auto"},
    "BAJFINANCE": {"name": "Bajaj Finance",              "base": 7200,  "sector": "Finance"},
    "NIFTY50":    {"name": "Nifty 50 Index",             "base": 24800, "sector": "Index"},
    "BANKNIFTY":  {"name": "Bank Nifty Index",           "base": 52000, "sector": "Index"},
    "SENSEX":     {"name": "BSE SENSEX Index",           "base": 79000, "sector": "Index"},
    "BANKEX":     {"name": "BSE BANKEX Index",           "base": 57000, "sector": "Index"},
    "AXISBANK":   {"name": "Axis Bank",                  "base": 1050,  "sector": "Banking"},
    "KOTAKBANK":  {"name": "Kotak Mahindra Bank",        "base": 1820,  "sector": "Banking"},
    "LT":         {"name": "Larsen & Toubro",            "base": 3500,  "sector": "Infra"},
    "HINDUNILVR": {"name": "Hindustan Unilever",         "base": 2350,  "sector": "FMCG"},
}


@router.get("/candles")
async def get_candles(
    symbol:    str = Query(...),
    exchange:  str = Query("NSE"),
    timeframe: str = Query("5"),
    bars:      int = Query(200, le=500),
    current_user: User = Depends(get_current_user),
):
    import asyncio
    from app.market.history import fetch_intraday_candles
    try:
        interval = int(timeframe)
    except ValueError:
        interval = 5
    try:
        candles = await asyncio.to_thread(
            fetch_intraday_candles, symbol.upper(), exchange, interval, bars,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"symbol": symbol.upper(), "exchange": exchange, "timeframe": str(interval), "candles": candles}


@router.get("/instruments")
async def search_instruments(
    q: str = Query(""),
    current_user: User = Depends(get_current_user),
):
    """Same search as /instruments/search, including options and indices."""
    if not q or len(q) < 2:
        return []
    return await search_instruments_csv(q=q, exch="NSE", current_user=current_user)


@router.get("/quote/{symbol}")
async def get_quote(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
    from app.core.trading_mode import synthetic_blocked
    if synthetic_blocked():
        raise HTTPException(
            status_code=409,
            detail="Synthetic quotes are disabled while live trading is enabled.",
        )
    symbol = symbol.upper()
    info   = INSTRUMENTS.get(symbol, {"base": 1000, "name": symbol, "sector": "Unknown"})
    base   = info["base"]
    pct    = random.uniform(-0.02, 0.02)
    ltp    = round(base * (1 + pct), 2)
    prev   = round(base, 2)
    return {
        "symbol":     symbol,
        "name":       info["name"],
        "ltp":        ltp,
        "prev_close": prev,
        "change":     round(ltp - prev, 2),
        "change_pct": round(pct * 100, 2),
        "open":       round(base * random.uniform(0.998, 1.002), 2),
        "high":       round(ltp * random.uniform(1.001, 1.015), 2),
        "low":        round(ltp * random.uniform(0.985, 0.999), 2),
        "volume":     random.randint(500_000, 5_000_000),
        "52w_high":   round(base * 1.35, 2),
        "52w_low":    round(base * 0.72, 2),
    }


@router.get("/fib-levels")
async def get_fib_levels(
    symbol:    str   = Query(...),
    day_open:  float = Query(..., description="9:15 AM opening price"),
    current_price: float = Query(..., description="Current LTP"),
    current_user: User = Depends(get_current_user),
):
    """
    Compute all Opening Range Fibonacci levels for a given symbol and day open.
    Used by the chart page to draw horizontal lines like TradingView.
    """
    import math

    is_buy  = current_price > day_open
    is_sell = current_price < day_open

    buy_entry  = round(math.pow(math.sqrt(day_open) + 0.025, 2))
    sell_entry = round(math.pow(math.sqrt(day_open) - 0.025, 2))
    buy_sl     = round(buy_entry  * 0.995, 2)
    sell_sl    = round(sell_entry * 1.005, 2)

    FIB = [
        ("T1", 0.118), ("T2", 0.238), ("T3", 0.382),
        ("T4", 0.500), ("T5", 0.618), ("T6", 0.786),
        ("T7", 1.000), ("T8", 1.618), ("T9", 2.618),
    ]

    buy_targets  = {lbl: round(day_open + day_open * pct / 100, 2) for lbl, pct in FIB}
    sell_targets = {lbl: round(day_open - day_open * pct / 100, 2) for lbl, pct in FIB}

    direction = "BUY" if is_buy else "SELL" if is_sell else "NEUTRAL"

    return {
        "symbol":       symbol,
        "day_open":     day_open,
        "current_price":current_price,
        "direction":    direction,
        "entry":        buy_entry  if is_buy  else sell_entry if is_sell else None,
        "sl":           buy_sl     if is_buy  else sell_sl    if is_sell else None,
        "buy_entry":    buy_entry,
        "sell_entry":   sell_entry,
        "buy_sl":       buy_sl,
        "sell_sl":      sell_sl,
        "buy_targets":  buy_targets  if is_buy  else {},
        "sell_targets": sell_targets if is_sell else {},
        "all_buy_targets":  buy_targets,
        "all_sell_targets": sell_targets,
        "fib_pcts": {lbl: pct for lbl, pct in FIB},
    }


# ── Dhan security ID map ──────────────────────────────────────────────────────
DHAN_SECURITY_IDS = {
    "NIFTY50":    {"security_id": "13",    "exchange_segment": "IDX_I"},
    "BANKNIFTY":  {"security_id": "25",    "exchange_segment": "IDX_I"},
    "SENSEX":     {"security_id": "51",    "exchange_segment": "IDX_I"},
    "BANKEX":     {"security_id": "83",    "exchange_segment": "IDX_I"},
    "RELIANCE":   {"security_id": "2885",  "exchange_segment": "NSE_EQ"},
    "TCS":        {"security_id": "11536", "exchange_segment": "NSE_EQ"},
    "INFY":       {"security_id": "1594",  "exchange_segment": "NSE_EQ"},
    "HDFCBANK":   {"security_id": "1333",  "exchange_segment": "NSE_EQ"},
    "ICICIBANK":  {"security_id": "4963",  "exchange_segment": "NSE_EQ"},
    "SBIN":       {"security_id": "3045",  "exchange_segment": "NSE_EQ"},
    "WIPRO":      {"security_id": "3787",  "exchange_segment": "NSE_EQ"},
    "TATAMOTORS": {"security_id": "3456",  "exchange_segment": "NSE_EQ"},
    "BAJFINANCE": {"security_id": "317",   "exchange_segment": "NSE_EQ"},
    "AXISBANK":   {"security_id": "5900",  "exchange_segment": "NSE_EQ"},
    "KOTAKBANK":  {"security_id": "1922",  "exchange_segment": "NSE_EQ"},
    "LT":         {"security_id": "11483", "exchange_segment": "NSE_EQ"},
    "HINDUNILVR": {"security_id": "1394",  "exchange_segment": "NSE_EQ"},
}


import time
import requests as _http

# Central in-memory quote cache and rate limiter
_QUOTE_CACHE: dict = {}
_LAST_DHAN_CALL_TIME: float = 0.0
_RATE_LIMITED_UNTIL: float = 0.0
_QUOTE_CACHE_TTL: float = 2.5
_MIN_REQUEST_GAP: float = 1.2


def _dhan_quote(securities: dict, client_id: str, access_token: str) -> dict:
    """
    Call Dhan /marketfeed/quote with rate limiting, TTL caching, and 805 backoff.
    Returns nested dict keyed by segment -> security_id.
    """
    global _LAST_DHAN_CALL_TIME, _RATE_LIMITED_UNTIL
    now = time.time()

    result = {}
    missing = {}

    # Check which securities can be satisfied from cache
    for seg, sids in securities.items():
        for sid in sids:
            sid_str = str(sid)
            cached_entry = _QUOTE_CACHE.get((seg, sid_str))
            if cached_entry and (now - cached_entry["time"]) < _QUOTE_CACHE_TTL:
                result.setdefault(seg, {})[sid_str] = cached_entry["data"]
            else:
                missing.setdefault(seg, []).append(int(sid))

    # If all requested instruments are fresh in cache, return immediately
    if not missing:
        return result

    # If currently rate-limited by Dhan, serve stale cached data to prevent ban
    if now < _RATE_LIMITED_UNTIL:
        for seg, sids in missing.items():
            for sid in sids:
                sid_str = str(sid)
                cached_entry = _QUOTE_CACHE.get((seg, sid_str))
                if cached_entry:
                    result.setdefault(seg, {})[sid_str] = cached_entry["data"]
        return result

    # Enforce minimum gap between consecutive calls to Dhan API
    elapsed = now - _LAST_DHAN_CALL_TIME
    if elapsed < _MIN_REQUEST_GAP:
        time.sleep(_MIN_REQUEST_GAP - elapsed)

    try:
        _LAST_DHAN_CALL_TIME = time.time()
        resp = _http.post(
            "https://api.dhan.co/v2/marketfeed/quote",
            headers={
                "access-token": access_token,
                "client-id":    client_id,
                "Content-Type": "application/json",
                "Accept":       "application/json",
            },
            json={seg: [int(sid) for sid in sids] for seg, sids in missing.items()},
            timeout=5,
        )
        data = resp.json()
        if data.get("status") == "success":
            raw_data = data.get("data", {})
            call_time = time.time()
            for seg, sids_data in raw_data.items():
                for sid_str, q in sids_data.items():
                    _QUOTE_CACHE[(seg, str(sid_str))] = {"time": call_time, "data": q}
                    result.setdefault(seg, {})[str(sid_str)] = q
            return result
        elif "805" in str(data):
            _RATE_LIMITED_UNTIL = time.time() + 8.0
            logger.warning("Dhan rate limit (805) encountered. Backing off for 8 seconds and serving cached data.")
            for seg, sids in missing.items():
                for sid in sids:
                    sid_str = str(sid)
                    cached_entry = _QUOTE_CACHE.get((seg, sid_str))
                    if cached_entry:
                        result.setdefault(seg, {})[sid_str] = cached_entry["data"]
            return result
        else:
            logger.warning(f"Dhan Quote API error: {data}")
            return result
    except Exception as e:
        logger.warning(f"Dhan quote request failed: {e}")
        return result


# Keep alias for backward compat
_dhan_ohlc = _dhan_quote


def _parse_ohlc(raw: dict, symbol: str, segment: str = "", security_id: str = "") -> dict:
    """Parse a /marketfeed/quote response row into a unified tick dict."""
    ltp   = float(raw.get("last_price", 0))
    ohlc  = raw.get("ohlc", {})
    open_ = float(ohlc.get("open",  ltp))
    high  = float(ohlc.get("high",  ltp))
    low   = float(ohlc.get("low",   ltp))
    close = float(ohlc.get("close", ltp))
    net_chg = float(raw.get("net_change", 0))

    from app.market.daily_ohlc import get_previous_day_ohlc, enqueue_daily_ohlc_fetch
    p_data = get_previous_day_ohlc(segment, security_id) if segment and security_id else None
    if p_data:
        p_close = float(p_data["p_close"])
        p_high  = float(p_data["p_high"])
        p_low   = float(p_data["p_low"])
        p_open  = float(p_data.get("p_open", p_close))
    else:
        if segment and security_id and str(security_id) != "0":
            enqueue_daily_ohlc_fetch(segment, security_id, symbol)
        if net_chg != 0:
            p_close = round(ltp - net_chg, 2)
        else:
            p_close = close
        p_high = p_close
        p_low  = p_close
        p_open = p_close

    chg   = round(ltp - p_close, 2)
    chgp  = round(chg / max(p_close, 1) * 100, 2)
    depth  = raw.get("depth", {})
    buy0   = depth.get("buy",  [{}])[0] if depth else {}
    sell0  = depth.get("sell", [{}])[0] if depth else {}
    return {
        "symbol":     symbol,
        "ltp":        ltp,
        "open":       open_,
        "high":       high,
        "low":        low,
        "close":      close,
        "p_close":    p_close,
        "p_high":     p_high,
        "p_low":      p_low,
        "p_open":     p_open,
        "volume":     int(raw.get("volume", 0)),
        "oi":         int(raw.get("oi", 0)),
        "atp":        float(raw.get("average_price", 0)),   # VWAP
        "vwap":       float(raw.get("average_price", 0)),
        "buy_qty":    int(raw.get("buy_quantity",  0)),
        "sell_qty":   int(raw.get("sell_quantity", 0)),
        "bp1":        float(buy0.get("price",  0)),
        "sp1":        float(sell0.get("price", 0)),
        "net_change": net_chg,
        "change":     chg,
        "change_pct": chgp,
        "source":     "dhan_live",
    }


def _sim_quote(symbol: str) -> dict:
    from app.core.trading_mode import synthetic_blocked
    if synthetic_blocked():
        raise HTTPException(
            status_code=409,
            detail=f"No live quote for {symbol}. Synthetic prices are disabled while live trading is enabled.",
        )
    info = INSTRUMENTS.get(symbol, {"base": 1000})
    base = info["base"]
    chg  = random.uniform(-0.015, 0.015)
    ltp  = round(base * (1 + chg), 2)
    return {
        "symbol": symbol, "ltp": ltp,
        "open": round(base * 0.999, 2),
        "high": round(ltp * 1.005, 2),
        "low":  round(ltp * 0.995, 2),
        "close": base,
        "p_close": base,
        "p_high": round(base * 1.015, 2),
        "p_low": round(base * 0.985, 2),
        "volume": random.randint(100000, 2000000),
        "change": round(ltp - base, 2),
        "change_pct": round(chg * 100, 2),
        "source": "simulated",
    }


@router.get("/live-quote/{symbol}")
async def get_live_quote(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
    """Real-time OHLC quote for a single symbol from Dhan."""
    from app.core.config import settings
    symbol = symbol.upper()

    if settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN:
        inst = DHAN_SECURITY_IDS.get(symbol)
        if inst:
            try:
                data = await asyncio.to_thread(
                    _dhan_ohlc,
                    {inst["exchange_segment"]: [inst["security_id"]]},
                    settings.DHAN_CLIENT_ID, settings.DHAN_ACCESS_TOKEN,
                )
                raw = data.get(inst["exchange_segment"], {}).get(
                    str(inst["security_id"]), {}
                )
                if raw:
                    return _parse_ohlc(
                        raw,
                        symbol,
                        segment=inst.get("exchange_segment", ""),
                        security_id=str(inst.get("security_id", "")),
                    )
            except Exception as e:
                logger.warning(f"Dhan live quote failed [{symbol}]: {e}")

    return _sim_quote(symbol)


@router.get("/live-quotes")
async def get_live_quotes(
    symbols: str = Query(..., description="Comma-separated e.g. NIFTY50,RELIANCE,TCS"),
    current_user: User = Depends(get_current_user),
):
    """Real-time OHLC for multiple symbols — uses shared poller cache if available."""
    from app.core.config import settings
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    # Use poller cache first (avoids extra Dhan API calls)
    from app.market.market_poller import get_poller
    poller = get_poller()
    if poller._last_data:
        cached = {t["symbol"]: t for t in poller._last_data}
        result = [cached[sym] for sym in symbol_list if sym in cached]
        missing = [sym for sym in symbol_list if sym not in cached]
        if not missing:
            return result
        # Fall through to fetch missing symbols
        symbol_list = missing

    # Direct Dhan call for uncached symbols
    if settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN:
        try:
            securities: dict = {}
            resolved: dict = {}
            for sym in symbol_list:
                inst = DHAN_SECURITY_IDS.get(sym) or poller._watchlist.get(sym)
                if inst:
                    resolved[sym] = inst
                    securities.setdefault(inst["exchange_segment"], []).append(inst["security_id"])

            if securities:
                data   = await asyncio.to_thread(_dhan_ohlc, securities, settings.DHAN_CLIENT_ID, settings.DHAN_ACCESS_TOKEN)
                result = []
                for sym in symbol_list:
                    inst = resolved.get(sym)
                    if not inst:
                        result.append(_sim_quote(sym))
                        continue
                    raw = data.get(inst["exchange_segment"], {}).get(str(inst["security_id"]), {})
                    if raw:
                        result.append(
                            _parse_ohlc(
                                raw,
                                sym,
                                segment=inst.get("exchange_segment", ""),
                                security_id=str(inst.get("security_id", "")),
                            )
                        )
                    else:
                        result.append(_sim_quote(sym))
                return result
        except Exception as e:
            logger.warning(f"Dhan bulk quote failed: {e}")

    return [_sim_quote(sym) for sym in symbol_list]


@router.get("/ticker")
async def get_ticker(current_user: User = Depends(get_current_user)):
    """Live ticker for NIFTY50 and BANKNIFTY — used by header bar."""
    from app.core.config import settings

    # Check shared poller cache first (avoids hitting Dhan API)
    from app.market.market_poller import get_poller
    poller = get_poller()
    if poller._last_data:
        cached = {t["symbol"]: t for t in poller._last_data}
        ticker = []
        for sym in ["NIFTY50", "BANKNIFTY", "SENSEX"]:
            if sym in cached:
                ticker.append({
                    "symbol":     sym,
                    "ltp":        cached[sym]["ltp"],
                    "change_pct": cached[sym].get("change_pct", 0),
                    "source":     "dhan_live",
                })
        if len(ticker) >= 2:
            return ticker

    if settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN:
        try:
            data = await asyncio.to_thread(
                _dhan_ohlc,
                {"IDX_I": ["13", "25", "51"]},
                settings.DHAN_CLIENT_ID, settings.DHAN_ACCESS_TOKEN,
            )
            ticker = []
            for sym, sid in [("NIFTY50", "13"), ("BANKNIFTY", "25"), ("SENSEX", "51")]:
                raw = data.get("IDX_I", {}).get(sid, {})
                if raw:
                    ltp   = float(raw.get("last_price", 0))
                    close = float(raw.get("ohlc", {}).get("close", ltp))
                    ticker.append({
                        "symbol":     sym,
                        "ltp":        ltp,
                        "change_pct": round((ltp - close) / max(close, 1) * 100, 2),
                        "source":     "dhan_live",
                    })
            if ticker:
                return ticker
        except Exception as e:
            logger.warning(f"Dhan ticker failed: {e}")

    from app.core.trading_mode import synthetic_blocked
    if synthetic_blocked():
        raise HTTPException(
            status_code=409,
            detail="Dhan ticker is unavailable and synthetic prices are disabled while live trading is enabled.",
        )

    return [
        {"symbol":"NIFTY50",  "ltp":round(24800*(1+random.uniform(-0.01,0.01)),2),
         "change_pct":round(random.uniform(-1,1),2),"source":"simulated"},
        {"symbol":"BANKNIFTY","ltp":round(52000*(1+random.uniform(-0.01,0.01)),2),
         "change_pct":round(random.uniform(-1,1),2),"source":"simulated"},
    ]

# ── Instrument Search ─────────────────────────────────────────────────────────

_instrument_cache: list = []
_cache_loaded_at: float = 0


async def _load_instruments() -> list:
    """
    Load instrument list from local CSV file.
    CSV is downloaded once manually and refreshed daily at 8 AM IST via Celery Beat.
    Never makes a network call during normal operation.
    Falls back to bundled list (55 symbols) if CSV not present.
    """
    global _instrument_cache, _cache_loaded_at
    import time, os

    now = time.time()
    if _instrument_cache and (now - _cache_loaded_at) < 86400:
        return _instrument_cache

    # CSV lives at: backend/app/market/instruments.csv
    csv_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "market", "instruments.csv")
    )

    if os.path.exists(csv_path):
        try:
            with open(csv_path, encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()

            if len(lines) < 10:
                raise ValueError("CSV too small — possibly corrupt")

            header  = [h.strip() for h in lines[0].split(",")]
            results = []

            for line in lines[1:]:
                cols = line.split(",")
                if len(cols) < len(header):
                    continue
                row    = dict(zip(header, cols))

                # Detailed CSV columns
                seg    = row.get("SEGMENT",  "").strip()
                exch   = row.get("EXCH_ID",  "").strip()
                series = row.get("SERIES",   "").strip()

                if seg != "E" or exch not in ("NSE", "BSE"):
                    continue
                if exch == "NSE" and series not in ("EQ", "BE", "SM", "ST"):
                    continue

                sym  = row.get("SYMBOL_NAME",  "").strip()
                name = row.get("DISPLAY_NAME", "").strip()
                sid  = row.get("SECURITY_ID",  "").strip()
                if not sym or not sid:
                    continue

                results.append({
                    "symbol":      sym,
                    "name":        name or sym,
                    "security_id": sid,
                    "exchange":    exch,
                    "segment":     "NSE_EQ" if exch == "NSE" else "BSE_EQ",
                    "series":      series,
                })

            if results:
                _instrument_cache = results
                _cache_loaded_at  = now
                logger.info(f"Loaded {len(results)} instruments from {csv_path}")
                return results

        except Exception as e:
            logger.error(f"Failed to read instrument CSV: {e}")
    else:
        logger.warning(
            f"Instrument CSV not found. Run once on your Pi:\n"
            f"  curl -L 'https://images.dhan.co/api-data/api-scrip-master.csv' -o {csv_path}"
        )

    # Fallback to bundled list
    logger.warning("Using bundled instrument list (55 symbols)")
    _instrument_cache = BUNDLED_INSTRUMENTS
    _cache_loaded_at  = now
    return _instrument_cache



def resolve_exchange_segment(row) -> tuple[str, str, str]:
    """
    Returns (exchange_segment, exchange, series) mapped to Dhan API specifications.
    Valid Dhan marketfeed quote segments:
    - IDX_I: Indices
    - NSE_EQ: NSE Cash Equity
    - BSE_EQ: BSE Cash Equity
    - NSE_FNO: NSE Derivatives (Futures & Options)
    - BSE_FNO: BSE Derivatives (Futures & Options)
    - MCX_COMM: MCX Commodities (Futures & Options)
    - NSE_CURR: NSE Currency Derivatives
    - BSE_CURR: BSE Currency Derivatives
    """
    exch = str(row.get("EXCH_ID") or "").strip().upper()
    seg  = str(row.get("SEGMENT") or "").strip().upper()
    inst = str(row.get("INSTRUMENT") or "").strip().upper()

    if seg == "I" or inst == "INDEX":
        return "IDX_I", exch, "INDEX"
    if exch == "MCX" or seg == "M":
        return "MCX_COMM", "MCX", inst or "COMM"
    if seg == "C" or inst in ("FUTCUR", "OPTCUR"):
        return f"{exch}_CURR" if exch in ("NSE", "BSE") else "NSE_CURR", exch, inst
    if seg == "D" or inst in ("FUTIDX", "FUTSTK", "OPTIDX", "OPTSTK", "OPTFUT"):
        opt = str(row.get("OPTION_TYPE") or "").strip()
        series = opt if opt and opt not in ("XX", "nan") else inst
        return f"{exch}_FNO" if exch in ("NSE", "BSE") else "NSE_FNO", exch, series
    if exch == "BSE":
        return "BSE_EQ", "BSE", str(row.get("SERIES") or "E")
    return "NSE_EQ", "NSE", str(row.get("SERIES") or "EQ")


def _search_instruments_sync(q: str, limit: int = 30) -> list[dict]:
    """
    Synchronous unrestricted search across all 225,137 instruments.
    Executed in a background thread via asyncio.to_thread to keep the event loop responsive.
    """
    q_clean = q.strip()
    if not q_clean:
        return []

    q_upper = q_clean.upper()
    raw_tokens = q_upper.split()
    tokens = []
    for t in raw_tokens:
        if t in ("CALL", "CALLS"):
            tokens.append("CALL")
        elif t in ("PUT", "PUTS"):
            tokens.append("PUT")
        elif t in ("FUTURE", "FUTURES"):
            tokens.append("FUT")
        else:
            tokens.append(t)

    try:
        df = _scrip_frame()
        if "SEARCH_BLOB" not in df.columns:
            return []

        # Multi-token boolean intersection
        mask = df["SEARCH_BLOB"].str.contains(tokens[0], regex=False, na=False)
        for tok in tokens[1:]:
            mask = mask & df["SEARCH_BLOB"].str.contains(tok, regex=False, na=False)

        hits = df[mask]
        if hits.empty:
            return []

        first_tok = tokens[0]

        def rank_score(r):
            sym = str(r.get("SYMBOL_NAME") or "").strip().upper()
            disp = str(r.get("DISPLAY_NAME") or "").strip().upper()
            und = str(r.get("UNDERLYING_SYMBOL") or "").strip().upper()
            inst = str(r.get("INSTRUMENT") or "").strip().upper()
            seg = str(r.get("SEGMENT") or "").strip().upper()
            exch = str(r.get("EXCH_ID") or "").strip().upper()
            series = str(r.get("SERIES") or "").strip().upper()
            expiry = str(r.get("SM_EXPIRY_DATE") or "9999-99-99").strip()
            if expiry in ("nan", "0001-01-01"):
                expiry = "9999-99-99"

            is_idx = seg == "I" or inst == "INDEX"
            is_fut = inst.startswith("FUT")
            is_opt = inst.startswith("OPT")
            is_eq  = inst == "EQUITY"

            # Tier 0: Exact match to the whole query string
            if disp == q_upper or sym == q_upper or und == q_upper:
                if is_idx:
                    return (0, 0, expiry)
                if is_eq and series == "EQ":
                    return (0, 1 if exch == "NSE" else 2, expiry)
                if is_eq:
                    return (0, 3, expiry)
                if is_fut:
                    return (0, 4, expiry)
                if is_opt:
                    return (0, 5, expiry)
                return (0, 6, expiry)

            # Tier 1: Single token search where underlying matches exactly
            if len(tokens) == 1:
                if und == q_upper or sym == q_upper:
                    if is_idx:
                        return (1, 0, expiry)
                    if is_eq and series == "EQ":
                        return (1, 1 if exch == "NSE" else 2, expiry)
                    if is_eq:
                        return (1, 3, expiry)
                    if is_fut:
                        return (1, 4, expiry)
                    if is_opt:
                        return (1, 5, expiry)
                    return (1, 6, expiry)

            # Tier 2: Futures matching the underlying / leading token
            if is_fut and (und == first_tok or sym.startswith(first_tok)):
                return (2, 0, expiry)

            # Tier 3: Starts with query
            if disp.startswith(q_upper) or sym.startswith(q_upper):
                if is_idx:
                    return (3, 0, expiry)
                if is_eq and series == "EQ":
                    return (3, 1 if exch == "NSE" else 2, expiry)
                if is_fut:
                    return (3, 3, expiry)
                if is_opt:
                    return (3, 4, expiry)
                return (3, 5, expiry)

            # Tier 4: Options matching the leading token
            if is_opt and (und == first_tok or sym.startswith(first_tok)):
                return (4, 0, expiry)

            # Tier 5: Everything else
            return (5, 0, expiry)

        scored_rows = []
        for _, row in hits.iterrows():
            scored_rows.append((rank_score(row), row))

        scored_rows.sort(key=lambda item: item[0])

        results = []
        seen_keys = set()

        for _, row in scored_rows:
            segment, exch, srs = resolve_exchange_segment(row)
            sec_id = str(int(float(row["SECURITY_ID"])))
            dedup_key = f"{segment}_{sec_id}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            disp_name = str(row.get("DISPLAY_NAME") or "").strip()
            sym_name = str(row.get("SYMBOL_NAME") or "").strip()
            und_sym = str(row.get("UNDERLYING_SYMBOL") or "").strip()
            isin = str(row.get("ISIN") or "")
            if isin == "nan":
                isin = ""

            if segment == "IDX_I":
                symbol = und_sym or sym_name or disp_name
                name = disp_name or sym_name
            elif segment in ("NSE_EQ", "BSE_EQ"):
                symbol = und_sym or sym_name or disp_name
                name = disp_name or sym_name
            else:
                symbol = disp_name or sym_name
                opt_type = str(row.get("OPTION_TYPE") or "").strip()
                expiry = str(row.get("SM_EXPIRY_DATE") or "").strip()
                strike = str(row.get("STRIKE_PRICE") or "").strip()
                if opt_type and opt_type not in ("XX", "nan"):
                    name = f"{und_sym} {strike} {opt_type} {expiry}".strip()
                elif expiry and expiry not in ("0001-01-01", "nan"):
                    name = f"{und_sym} {expiry} {srs}".strip()
                else:
                    name = sym_name or disp_name

            results.append({
                "symbol":           symbol,
                "name":             name,
                "security_id":      sec_id,
                "exchange_segment": segment,
                "exchange":         exch,
                "series":           srs,
                "isin":             isin if segment in ("NSE_EQ", "BSE_EQ") else "",
                "lot_size":         int(float(row.get("LOT_SIZE") or 1)),
            })

            if len(results) >= limit:
                break

        return results

    except Exception as e:
        logger.error(f"Unrestricted instrument search error: {e}")
        return []


_RESOLVED_INSTRUMENT_CACHE: dict[tuple[str, str, str], dict] = {}


def resolve_dhan_instrument(symbol: str, exchange: Optional[str] = None, segment: Optional[str] = None) -> Optional[dict]:
    """
    Robust resolver that maps any symbol (equity, option, futures, MCX commodity, index)
    to its Dhan security ID, exchange segment, exchange, and contract lot size.
    Uses in-memory cache, static fast maps, and instruments.csv scrip frame.
    """
    sym_u = (symbol or "").strip().upper()
    if not sym_u:
        return None

    ex_key = (exchange or "").upper().strip()
    seg_key = (segment or "").upper().strip()
    cache_key = (sym_u, ex_key, seg_key)
    if cache_key in _RESOLVED_INSTRUMENT_CACHE:
        return _RESOLVED_INSTRUMENT_CACHE[cache_key]

    from app.services.dhan_fanout_engine import resolve_lot_size

    # 1. Fast path: static high-speed dictionary
    if sym_u in DHAN_SECURITY_IDS:
        val = DHAN_SECURITY_IDS[sym_u]
        seg = val.get("exchange_segment") or val.get("segment") or "NSE_EQ"
        exch = "MCX" if "MCX" in seg else ("BSE" if "BSE" in seg or seg in ("BSE_EQ", "BSE_FNO") else "NSE")
        sec_id = str(val["security_id"])
        lot = resolve_lot_size(sym_u, sec_id)
        res = {
            "symbol": sym_u,
            "security_id": sec_id,
            "segment": seg,
            "exchange": exch,
            "lot_size": lot,
        }
        _RESOLVED_INSTRUMENT_CACHE[cache_key] = res
        return res

    # 2. Scrip master search
    try:
        df = _scrip_frame()
        # Direct column matches
        match = df[df["DISPLAY_NAME"].str.upper() == sym_u]
        if match.empty:
            match = df[df["SYMBOL_NAME"].str.upper() == sym_u]
        if match.empty:
            match = df[(df["UNDERLYING_SYMBOL"].str.upper() == sym_u) & (df["SERIES"] == "EQ")]

        # Normalized option naming: CE <-> CALL, PE <-> PUT
        if match.empty and any(k in sym_u for k in (" CE", " PE", " CALL", " PUT")):
            alt = sym_u.replace(" CE", " CALL").replace(" PE", " PUT")
            if alt != sym_u:
                match = df[df["DISPLAY_NAME"].str.upper() == alt]
                if match.empty:
                    match = df[df["SYMBOL_NAME"].str.upper() == alt]
            if match.empty:
                alt2 = sym_u.replace(" CALL", " CE").replace(" PUT", " PE")
                if alt2 != sym_u:
                    match = df[df["DISPLAY_NAME"].str.upper() == alt2]
                    if match.empty:
                        match = df[df["SYMBOL_NAME"].str.upper() == alt2]

        # Prioritize matching exchange / segment if provided
        if not match.empty:
            if exchange:
                ex_match = match[match["EXCH_ID"].str.upper() == ex_key]
                if not ex_match.empty:
                    match = ex_match
            if segment:
                seg_char = {"MCX_COMM": "M", "NSE_FNO": "D", "BSE_FNO": "D", "NSE_EQ": "E", "BSE_EQ": "E", "IDX_I": "I"}.get(seg_key)
                if seg_char:
                    seg_match = match[match["SEGMENT"].str.upper() == seg_char]
                    if not seg_match.empty:
                        match = seg_match

        if not match.empty:
            row = match.iloc[0]
            seg_id, exch_id, _ = resolve_exchange_segment(row)
            sec_id = str(int(float(row["SECURITY_ID"])))
            lot_val = row.get("LOT_SIZE")
            try:
                lot = int(float(lot_val)) if lot_val and str(lot_val) != "nan" else 1
            except Exception:
                lot = 1
            if lot <= 1:
                lot = resolve_lot_size(sym_u, sec_id)
            res = {
                "symbol": sym_u,
                "security_id": sec_id,
                "segment": seg_id,
                "exchange": exch_id,
                "lot_size": max(1, lot),
            }
            _RESOLVED_INSTRUMENT_CACHE[cache_key] = res
            return res

        # 3. Fallback to token search if exact name didn't match (e.g. symbol without expiry)
        search_res = _search_instruments_sync(sym_u, limit=1)
        if search_res:
            first = search_res[0]
            sec_id = str(first["security_id"])
            seg_id = str(first["exchange_segment"])
            exch_id = str(first["exchange"])
            lot = resolve_lot_size(sym_u, sec_id)
            res = {
                "symbol": sym_u,
                "security_id": sec_id,
                "segment": seg_id,
                "exchange": exch_id,
                "lot_size": max(1, lot),
            }
            _RESOLVED_INSTRUMENT_CACHE[cache_key] = res
            return res
    except Exception as e:
        logger.warning(f"resolve_dhan_instrument failed for {symbol}: {e}")

    return None


@router.get("/instruments/search")
async def search_instruments_csv(
    q:    str = Query(..., min_length=1),
    exch: str = Query("NSE"),
    current_user: User = Depends(get_current_user),
):
    """
    Unrestricted full-market instrument search across all 225,137 instruments:
    Equities (NSE & BSE all series), Indices, Stock Futures, Index Futures,
    Index Options, Stock Options, Commodity Futures & Options (MCX),
    and Currency Futures & Options.
    """
    return await asyncio.to_thread(_search_instruments_sync, q, 30)


BUNDLED_INSTRUMENTS = [
    {"symbol":"RELIANCE",    "name":"Reliance Industries",         "security_id":"2885",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"TCS",         "name":"Tata Consultancy Services",   "security_id":"11536", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"HDFCBANK",    "name":"HDFC Bank",                   "security_id":"1333",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"INFY",        "name":"Infosys",                     "security_id":"1594",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"ICICIBANK",   "name":"ICICI Bank",                  "security_id":"4963",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"HINDUNILVR",  "name":"Hindustan Unilever",          "security_id":"1394",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"SBIN",        "name":"State Bank of India",         "security_id":"3045",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"BHARTIARTL",  "name":"Bharti Airtel",               "security_id":"10604", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"BAJFINANCE",  "name":"Bajaj Finance",               "security_id":"317",   "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"WIPRO",       "name":"Wipro",                       "security_id":"3787",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"LT",          "name":"Larsen & Toubro",             "security_id":"11483", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"KOTAKBANK",   "name":"Kotak Mahindra Bank",         "security_id":"1922",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"AXISBANK",    "name":"Axis Bank",                   "security_id":"5900",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"TATAMOTORS",  "name":"Tata Motors",                 "security_id":"3456",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"MARUTI",      "name":"Maruti Suzuki India",         "security_id":"10999", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"SUNPHARMA",   "name":"Sun Pharmaceutical",          "security_id":"3351",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"TITAN",       "name":"Titan Company",               "security_id":"3506",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"ASIANPAINT",  "name":"Asian Paints",                "security_id":"236",   "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"NTPC",        "name":"NTPC",                        "security_id":"11630", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"POWERGRID",   "name":"Power Grid Corporation",      "security_id":"14977", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"ULTRACEMCO",  "name":"UltraTech Cement",            "security_id":"11532", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"NESTLEIND",   "name":"Nestle India",                "security_id":"17963", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"HCLTECH",     "name":"HCL Technologies",            "security_id":"7229",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"TECHM",       "name":"Tech Mahindra",               "security_id":"13538", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"BAJAJFINSV",  "name":"Bajaj Finserv",               "security_id":"16675", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"ONGC",        "name":"Oil & Natural Gas Corporation","security_id":"2475",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"INDUSINDBK",  "name":"IndusInd Bank",               "security_id":"5258",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"TATACONSUM",  "name":"Tata Consumer Products",      "security_id":"3432",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"COALINDIA",   "name":"Coal India",                  "security_id":"20374", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"ADANIENT",    "name":"Adani Enterprises",           "security_id":"25",    "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"ADANIPORTS",  "name":"Adani Ports & SEZ",           "security_id":"15083", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"GRASIM",      "name":"Grasim Industries",           "security_id":"1232",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"DIVISLAB",    "name":"Divi's Laboratories",         "security_id":"10940", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"DRREDDY",     "name":"Dr. Reddy's Laboratories",    "security_id":"881",   "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"CIPLA",       "name":"Cipla",                       "security_id":"694",   "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"EICHERMOT",   "name":"Eicher Motors",               "security_id":"910",   "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"HEROMOTOCO",  "name":"Hero MotoCorp",               "security_id":"1348",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"APOLLOHOSP",  "name":"Apollo Hospitals Enterprise", "security_id":"157",   "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"TATAPOWER",   "name":"Tata Power Company",          "security_id":"3426",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"JSWSTEEL",    "name":"JSW Steel",                   "security_id":"11723", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"TATASTEEL",   "name":"Tata Steel",                  "security_id":"3412",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"HINDALCO",    "name":"Hindalco Industries",         "security_id":"1363",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"BPCL",        "name":"Bharat Petroleum Corporation","security_id":"526",   "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"IOC",         "name":"Indian Oil Corporation",      "security_id":"1624",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"ZOMATO",      "name":"Zomato",                      "security_id":"21176", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"PAYTM",       "name":"One97 Communications",        "security_id":"21209", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"NYKAA",       "name":"FSN E-Commerce Ventures",     "security_id":"21333", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"DMART",       "name":"Avenue Supermarts",           "security_id":"19916", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"PIDILITIND",  "name":"Pidilite Industries",         "security_id":"2664",  "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"HAVELLS",     "name":"Havells India",               "security_id":"11080", "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    {"symbol":"BERGEPAINT",  "name":"Berger Paints India",         "security_id":"394",   "exchange":"NSE","segment":"NSE_EQ","series":"EQ"},
    # Indices
    {"symbol":"NIFTY50",     "name":"Nifty 50 Index",              "security_id":"13",    "exchange":"NSE","segment":"IDX_I","series":"IDX"},
    {"symbol":"BANKNIFTY",   "name":"Nifty Bank Index",            "security_id":"25",    "exchange":"NSE","segment":"IDX_I","series":"IDX"},
    {"symbol":"FINNIFTY",    "name":"Nifty Financial Services",    "security_id":"27",    "exchange":"NSE","segment":"IDX_I","series":"IDX"},
    {"symbol":"MIDCPNIFTY",  "name":"Nifty Midcap Select",         "security_id":"11",    "exchange":"NSE","segment":"IDX_I","series":"IDX"},
    {"symbol":"SENSEX",      "name":"BSE SENSEX Index",            "security_id":"51",    "exchange":"BSE","segment":"IDX_I","series":"IDX"},
    {"symbol":"BANKEX",      "name":"BSE BANKEX Index",            "security_id":"83",    "exchange":"BSE","segment":"IDX_I","series":"IDX"},
]


# ── Watchlist Management (DB-backed, persists across restarts) ───────────────

DEFAULT_WATCHLIST = []  # No default symbols — users add their own  # No default symbols — users add their own


@router.get("/watchlist")
async def get_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's persisted watchlist. Seeds defaults on first visit."""
    from sqlalchemy import select
    from app.models.watchlist import UserWatchlist
    from app.market.market_poller import get_poller

    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == current_user.id)
        .order_by(UserWatchlist.added_at)
    )
    rows = result.scalars().all()

    # First visit — seed defaults
    if not rows:
        for item in DEFAULT_WATCHLIST:
            db.add(UserWatchlist(
                user_id          = current_user.id,
                symbol           = item["symbol"],
                security_id      = item["security_id"],
                exchange_segment = item["exchange_segment"],
            ))
        await db.commit()
        rows = (await db.execute(
            select(UserWatchlist).where(UserWatchlist.user_id == current_user.id)
        )).scalars().all()

    poller = get_poller()
    for row in rows:
        poller.add_symbol(row.symbol, row.security_id, row.exchange_segment)

    return {
        "symbols": [r.symbol for r in rows],
        "instruments": [
            {
                "symbol":           r.symbol,
                "security_id":      r.security_id,
                "exchange_segment": r.exchange_segment,
            }
            for r in rows
        ],
    }


@router.post("/watchlist")
async def add_to_watchlist(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # If BSE cash equity, try to find NSE equivalent before saving
    if body.get("exchange_segment") == "BSE_EQ":
        try:
            df = _scrip_frame()
            sid = str(body.get("security_id", "")).replace(".0", "")
            bse_row = df[(df["EXCH_ID"] == "BSE") & (df["SECURITY_ID"].astype(str) == sid)]
            if not bse_row.empty:
                isin = bse_row.iloc[0]["ISIN"]
                if isin and str(isin) != "nan":
                    nse_row = df[(df["EXCH_ID"] == "NSE") & (df["ISIN"] == isin) & (df["SERIES"] == "EQ")]
                    if not nse_row.empty:
                        body["security_id"] = str(int(float(nse_row.iloc[0]["SECURITY_ID"])))
                        body["exchange_segment"] = "NSE_EQ"
                        ticker = str(nse_row.iloc[0]["UNDERLYING_SYMBOL"] or "").strip()
                        if ticker:
                            body["symbol"] = ticker
                        logger.info(f"Watchlist: BSE→NSE for {body.get('symbol')}")
        except Exception as e:
            logger.warning(f"Watchlist BSE→NSE lookup failed: {e}")

    """Add a symbol to user's watchlist — persisted to DB."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from app.models.watchlist import UserWatchlist
    from app.market.market_poller import get_poller

    symbol   = body.get("symbol", "").upper()
    sec_id   = str(body.get("security_id", ""))
    segment  = body.get("exchange_segment", "NSE_EQ")

    if not symbol or not sec_id:
        raise HTTPException(status_code=400, detail="symbol and security_id required")

    try:
        db.add(UserWatchlist(
            user_id          = current_user.id,
            symbol           = symbol,
            security_id      = sec_id,
            exchange_segment = segment,
        ))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Already exists — that's fine

    # Add to live poller immediately
    get_poller().add_symbol(symbol, sec_id, segment)

    result = await db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(UserWatchlist)
        .where(UserWatchlist.user_id == current_user.id)
        .order_by(UserWatchlist.added_at)
    )
    rows = result.scalars().all()
    return {"status": "added", "symbol": symbol, "symbols": [r.symbol for r in rows]}


@router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a symbol from user's watchlist — persisted to DB."""
    from sqlalchemy import select, delete
    from app.models.watchlist import UserWatchlist
    from app.market.market_poller import get_poller

    symbol = symbol.upper()
    await db.execute(
        delete(UserWatchlist).where(
            UserWatchlist.user_id == current_user.id,
            UserWatchlist.symbol  == symbol,
        )
    )
    await db.commit()

    # Remove from live poller
    get_poller().remove_symbol(symbol)

    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == current_user.id)
        .order_by(UserWatchlist.added_at)
    )
    rows = result.scalars().all()
    return {"status": "removed", "symbol": symbol, "symbols": [r.symbol for r in rows]}


@router.get("/funds")
async def get_funds(current_user: User = Depends(get_current_user)):
    """Fetch Dhan fund limits for account summary bar."""
    from app.core.config import settings
    from app.models.broker import BrokerAccount, BrokerName
    from sqlalchemy import select as sa_select
    from app.core.database import AsyncSessionLocal

    client_id = settings.DHAN_CLIENT_ID
    token = settings.DHAN_ACCESS_TOKEN
    acct_id = None

    try:
        async with AsyncSessionLocal() as _db:
            _res = await _db.execute(
                sa_select(BrokerAccount).where(
                    BrokerAccount.user_id == current_user.id,
                    BrokerAccount.broker == BrokerName.dhan,
                )
            )
            _acct = _res.scalar_one_or_none()
            if _acct:
                if _acct.client_id:
                    client_id = _acct.client_id
                acct_id = _acct.id
    except Exception:
        pass

    if client_id and token:
        try:
            from dhanhq import DhanContext, dhanhq
            ctx = DhanContext(client_id, token)
            dhan = dhanhq(ctx)
            resp = dhan.get_fund_limits()
            if resp and resp.get("status") == "success":
                data = resp.get("data", {})
                # Auto-activate user's broker account in DB if inactive
                if acct_id:
                    try:
                        async with AsyncSessionLocal() as _db:
                            acct = await _db.get(BrokerAccount, acct_id)
                            if acct and not acct.is_active:
                                acct.is_active = True
                                await _db.commit()
                    except Exception:
                        pass
                return data
        except Exception as e:
            logger.warning(f"Dhan funds error: {e}")
    return {"availabelBalance": 0, "utilizedAmount": 0, "sodLimit": 0}


@router.get("/vwap/{symbol}")
async def get_vwap(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
    """
    Calculate real VWAP for a symbol using intraday candle data.
    VWAP = Cumulative(Typical_Price * Volume) / Cumulative(Volume)
    where Typical_Price = (High + Low + Close) / 3
    """
    from app.market.candle_builder import build_ohlcv
    import pandas as pd

    symbol = symbol.upper()
    inst   = DHAN_SECURITY_IDS.get(symbol)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in instrument list")

    df = build_ohlcv(
        exchange          = inst["exchange_segment"].split("_")[0],
        token             = inst["security_id"],
        timeframe_minutes = 1,   # 1-min candles for accurate VWAP
    )

    if df.empty or len(df) < 2:
        return {"symbol": symbol, "vwap": None, "candles": 0}

    # Calculate VWAP per the provided formula
    df = df.copy()
    df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3
    df["tp_vol"]        = df["typical_price"] * df["volume"]
    df["cum_tp_vol"]    = df["tp_vol"].cumsum()
    df["cum_volume"]    = df["volume"].cumsum()
    df["vwap"]          = df["cum_tp_vol"] / df["cum_volume"]

    vwap = float(df["vwap"].iloc[-1])
    return {
        "symbol":  symbol,
        "vwap":    round(vwap, 2),
        "candles": len(df),
    }
