"""
Market Data Routes — serves OHLCV candles, quotes and instrument search.
"""
import logging
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

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
    symbol = symbol.upper()
    info   = INSTRUMENTS.get(symbol, {"base": 1000, "name": symbol, "sector": "Unknown"})
    candles = _generate_candles(info["base"], bars, int(timeframe))
    return {"symbol": symbol, "exchange": exchange, "timeframe": timeframe, "candles": candles}


@router.get("/instruments")
async def search_instruments(
    q: str = Query(""),
    current_user: User = Depends(get_current_user),
):
    """Search instruments from CSV — NSE first, BSE as fallback."""
    if not q or len(q) < 2:
        return []

    import pandas as pd, os
    q = q.upper().strip()

    try:
        csv_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "../../market/instruments.csv"))
        df = pd.read_csv(csv_path, header=0, low_memory=False)

        # Filter equity only (EQ series for NSE, E series for BSE)
        eq_df = df[
            ((df["EXCH_ID"] == "NSE") & (df["SERIES"] == "EQ")) |
            ((df["EXCH_ID"] == "BSE") & (df["SERIES"] == "E"))
        ]

        # Search by symbol name or display name
        mask = (
            eq_df["SYMBOL_NAME"].str.upper().str.contains(q, na=False) |
            eq_df["DISPLAY_NAME"].str.upper().str.contains(q, na=False)
        )
        matches = eq_df[mask].head(40)

        # Build results — deduplicate by ISIN, prefer NSE
        seen_isin = {}
        results   = []

        # Process NSE first
        for _, row in matches[matches["EXCH_ID"] == "NSE"].iterrows():
            isin = str(row["ISIN"])
            entry = {
                "symbol":           str(row["DISPLAY_NAME"]),
                "security_id":      str(int(row["SECURITY_ID"])),
                "exchange_segment": "NSE_EQ",
                "exchange":         "NSE",
                "series":           str(row["SERIES"]),
                "isin":             isin,
            }
            seen_isin[isin] = len(results)
            results.append(entry)

        # Add BSE only if no NSE equivalent
        for _, row in matches[matches["EXCH_ID"] == "BSE"].iterrows():
            isin = str(row["ISIN"])
            if isin not in seen_isin:
                results.append({
                    "symbol":           str(row["DISPLAY_NAME"]),
                    "security_id":      str(int(row["SECURITY_ID"])),
                    "exchange_segment": "BSE_EQ",
                    "exchange":         "BSE",
                    "series":           str(row["SERIES"]),
                    "isin":             isin,
                })

        return results[:20]

    except Exception as e:
        logger.error(f"Instrument search error: {e}")
        return []


@router.get("/quote/{symbol}")
async def get_quote(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
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


@router.get("/ticker")
async def get_ticker(current_user: User = Depends(get_current_user)):
    """Returns live ticker data for all instruments — used by the top ticker bar."""
    tickers = []
    for sym, info in INSTRUMENTS.items():
        base = info["base"]
        pct  = random.uniform(-0.03, 0.03)
        tickers.append({
            "symbol":     sym,
            "ltp":        round(base * (1 + pct), 2),
            "change_pct": round(pct * 100, 2),
        })
    return tickers


def _generate_candles(base_price: float, num_bars: int, interval_min: int) -> list:
    candles = []
    price   = base_price
    now     = datetime.now().replace(second=0, microsecond=0)
    minutes = (now.minute // interval_min) * interval_min
    now     = now.replace(minute=minutes)
    rng     = random.Random(int(base_price * 1000))

    for i in range(num_bars, 0, -1):
        ts  = now - timedelta(minutes=i * interval_min)
        if ts.hour < 9 or (ts.hour == 9 and ts.minute < 15): continue
        if ts.hour > 15 or (ts.hour == 15 and ts.minute > 30): continue

        vol    = base_price * rng.uniform(0.001, 0.004)
        chg    = rng.gauss(0, vol / base_price)
        open_  = round(price, 2)
        close  = round(price * (1 + chg), 2)
        spread = abs(close - open_)
        high   = round(max(open_, close) + rng.uniform(0, spread * 1.5), 2)
        low    = round(min(open_, close) - rng.uniform(0, spread * 1.5), 2)
        candles.append({
            "time": int(ts.timestamp()), "open": open_,
            "high": high, "low": low, "close": close,
            "volume": max(rng.randint(100_000, 500_000), 10_000),
        })
        price = close
    return candles


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


import requests as _http


def _dhan_quote(securities: dict, client_id: str, access_token: str) -> dict:
    """
    Call Dhan /marketfeed/quote — returns full market data per instrument.
    Includes: LTP, OHLC, Volume, OI, average_price (VWAP), market depth (buy/sell).
    securities: {"NSE_EQ": ["2885", "1333"], "IDX_I": ["13"]}
    Returns nested dict keyed by segment → security_id.
    """
    resp = _http.post(
        "https://api.dhan.co/v2/marketfeed/quote",
        headers={
            "access-token": access_token,
            "client-id":    client_id,
            "Content-Type": "application/json",
            "Accept":       "application/json",
        },
        json={seg: [int(sid) for sid in sids] for seg, sids in securities.items()},
        timeout=5,
    )
    data = resp.json()
    if data.get("status") == "success":
        return data.get("data", {})
    logger.warning(f"Dhan Quote API error: {data}")
    return {}


# Keep alias for backward compat
_dhan_ohlc = _dhan_quote


def _parse_ohlc(raw: dict, symbol: str) -> dict:
    """Parse a /marketfeed/quote response row into a unified tick dict."""
    ltp   = float(raw.get("last_price", 0))
    ohlc  = raw.get("ohlc", {})
    open_ = float(ohlc.get("open",  ltp))
    high  = float(ohlc.get("high",  ltp))
    low   = float(ohlc.get("low",   ltp))
    close = float(ohlc.get("close", ltp))
    chg   = round(ltp - close, 2)
    chgp  = round(chg / max(close, 1) * 100, 2)
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
        "volume":     int(raw.get("volume", 0)),
        "oi":         int(raw.get("oi", 0)),
        "atp":        float(raw.get("average_price", 0)),   # VWAP
        "vwap":       float(raw.get("average_price", 0)),
        "buy_qty":    int(raw.get("buy_quantity",  0)),
        "sell_qty":   int(raw.get("sell_quantity", 0)),
        "bp1":        float(buy0.get("price",  0)),
        "sp1":        float(sell0.get("price", 0)),
        "net_change": float(raw.get("net_change", 0)),
        "change":     chg,
        "change_pct": chgp,
        "source":     "dhan_live",
    }


def _sim_quote(symbol: str) -> dict:
    info = INSTRUMENTS.get(symbol, {"base": 1000})
    base = info["base"]
    chg  = random.uniform(-0.015, 0.015)
    ltp  = round(base * (1 + chg), 2)
    return {
        "symbol": symbol, "ltp": ltp,
        "open": round(base * 0.999, 2),
        "high": round(ltp * 1.005, 2),
        "low":  round(ltp * 0.995, 2),
        "close": base, "volume": random.randint(100000, 2000000),
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
                data = _dhan_ohlc(
                    {inst["exchange_segment"]: [inst["security_id"]]},
                    settings.DHAN_CLIENT_ID, settings.DHAN_ACCESS_TOKEN,
                )
                raw = data.get(inst["exchange_segment"], {}).get(
                    str(inst["security_id"]), {}
                )
                if raw:
                    return _parse_ohlc(raw, symbol)
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
            for sym in symbol_list:
                inst = DHAN_SECURITY_IDS.get(sym)
                if inst:
                    securities.setdefault(inst["exchange_segment"], []).append(inst["security_id"])

            if securities:
                data   = _dhan_ohlc(securities, settings.DHAN_CLIENT_ID, settings.DHAN_ACCESS_TOKEN)
                result = []
                for sym in symbol_list:
                    inst = DHAN_SECURITY_IDS.get(sym)
                    if not inst:
                        result.append(_sim_quote(sym))
                        continue
                    raw = data.get(inst["exchange_segment"], {}).get(str(inst["security_id"]), {})
                    result.append(_parse_ohlc(raw, sym) if raw else _sim_quote(sym))
                return result
        except Exception as e:
            logger.warning(f"Dhan bulk quote failed: {e}")

    return [_sim_quote(sym) for sym in symbol_list]


@router.get("/ticker")
async def get_ticker(current_user: User = Depends(get_current_user)):
    """Live ticker for NIFTY50 and BANKNIFTY — used by header bar."""
    from app.core.config import settings

    if settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN:
        try:
            data = _dhan_ohlc(
                {"IDX_I": ["13", "25"]},
                settings.DHAN_CLIENT_ID, settings.DHAN_ACCESS_TOKEN,
            )
            ticker = []
            for sym, sid in [("NIFTY50", "13"), ("BANKNIFTY", "25")]:
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
                logger.info(f"✅ Loaded {len(results)} instruments from {csv_path}")
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



@router.get("/instruments/search")
async def search_instruments_csv(
    q:    str = Query(..., min_length=1),
    exch: str = Query("NSE"),
    current_user: User = Depends(get_current_user),
):
    """Search instruments from CSV — NSE first, BSE as fallback."""
    import pandas as pd, os, re
    q_upper = q.upper().strip()

    try:
        csv_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "../../market/instruments.csv"))
        df = pd.read_csv(csv_path, header=0, low_memory=False)

        # Equity + Indices
        eq_df = df[
            ((df["EXCH_ID"] == "NSE") & (df["SERIES"] == "EQ")) |
            ((df["EXCH_ID"] == "BSE") & (df["SERIES"] == "E"))  |
            ((df["EXCH_ID"] == "NSE") & (df["SEGMENT"] == "I"))
        ]

        mask = (
            eq_df["SYMBOL_NAME"].str.upper().str.contains(q_upper, na=False, regex=False) |
            eq_df["DISPLAY_NAME"].str.upper().str.contains(q_upper, na=False, regex=False)
        )
        matches = eq_df[mask].head(60)

        # Deduplicate by ISIN — NSE first
        seen_isin = {}
        results   = []

        for _, row in matches[matches["EXCH_ID"] == "NSE"].iterrows():
            isin = str(row["ISIN"])
            entry = {
                "symbol":           str(row["DISPLAY_NAME"]),
                "name":             str(row["SYMBOL_NAME"]),
                "security_id":      str(int(float(row["SECURITY_ID"]))),
                "exchange_segment": "NSE_EQ",
                "exchange":         "NSE",
                "series":           "EQ",
                "isin":             isin,
            }
            seen_isin[isin] = len(results)
            results.append(entry)

        for _, row in matches[matches["EXCH_ID"] == "BSE"].iterrows():
            isin = str(row["ISIN"])
            if isin not in seen_isin:
                results.append({
                    "symbol":           str(row["DISPLAY_NAME"]),
                    "name":             str(row["SYMBOL_NAME"]),
                    "security_id":      str(int(float(row["SECURITY_ID"]))),
                    "exchange_segment": "BSE_EQ",
                    "exchange":         "BSE",
                    "series":           "E",
                    "isin":             isin,
                })

        # Sort: exact match first, then starts-with, then contains
        def sort_key(r):
            s = r["symbol"].upper()
            n = r["name"].upper()
            if s == q_upper or n == q_upper:          return 0
            if s.startswith(q_upper) or n.startswith(q_upper): return 1
            return 2

        results.sort(key=sort_key)
        return results[:20]

    except Exception as e:
        logger.error(f"Instrument search error: {e}")
        return []


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

    # Sync poller with user's saved watchlist
    poller = get_poller()
    for row in rows:
        poller.add_symbol(row.symbol, row.security_id, row.exchange_segment)

    # Sync poller
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
    # If BSE symbol, try to find NSE equivalent before saving
    if body.get("exchange_segment", "").startswith("BSE"):
        try:
            import pandas as pd, os
            csv_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "../../market/instruments.csv"))
            df = pd.read_csv(csv_path, header=None, low_memory=False)
            bse_row = df[df.iloc[:, 2].astype(str) == str(body.get("security_id", ""))]
            if not bse_row.empty:
                isin = bse_row.iloc[0, 3]
                nse_row = df[(df.iloc[:, 0] == "NSE") & (df.iloc[:, 3] == isin) & (df.iloc[:, 10] == "EQ")]
                if not nse_row.empty:
                    body["security_id"]      = str(int(nse_row.iloc[0, 2]))
                    body["exchange_segment"] = "NSE_EQ"
                    logger.info(f"Watchlist: BSE→NSE for {body.get('symbol')}")
        except Exception as e:
            logger.warning(f"Watchlist BSE→NSE lookup failed: {e}")

    # If BSE symbol, try to find NSE equivalent before saving
    if body.get("exchange_segment", "").startswith("BSE"):
        try:
            import pandas as pd, os
            csv_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "../../market/instruments.csv"))
            df = pd.read_csv(csv_path, header=None, low_memory=False)
            bse_row = df[df.iloc[:, 2].astype(str) == str(body.get("security_id", ""))]
            if not bse_row.empty:
                isin = bse_row.iloc[0, 3]
                nse_row = df[(df.iloc[:, 0] == "NSE") & (df.iloc[:, 3] == isin) & (df.iloc[:, 10] == "EQ")]
                if not nse_row.empty:
                    body["security_id"]      = str(int(nse_row.iloc[0, 2]))
                    body["exchange_segment"] = "NSE_EQ"
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
    # Use requesting user's broker credentials for isolation
    from app.models.broker import BrokerAccount, BrokerName
    from sqlalchemy import select as sa_select
    from app.core.database import AsyncSessionLocal
    user_client_id    = None
    user_access_token = None
    try:
        async with AsyncSessionLocal() as _db:
            _res = await _db.execute(
                sa_select(BrokerAccount).where(
                    BrokerAccount.user_id       == current_user.id,
                    BrokerAccount.broker        == BrokerName.dhan,
                    BrokerAccount.paper_trading == False,
                    BrokerAccount.is_active     == True,
                )
            )
            _acct = _res.scalar_one_or_none()
            if _acct:
                user_client_id    = _acct.client_id
                user_access_token = settings.DHAN_ACCESS_TOKEN  # token from env
    except Exception:
        pass

    # Only fetch balance if THIS user has an active live broker
    if user_client_id and settings.DHAN_ACCESS_TOKEN:
        try:
            from dhanhq import DhanContext, dhanhq
            ctx  = DhanContext(
                user_client_id or settings.DHAN_CLIENT_ID,
                settings.DHAN_ACCESS_TOKEN
            )
            dhan = dhanhq(ctx)
            resp = dhan.get_fund_limits()
            if resp and resp.get("status") == "success":
                return resp.get("data", {})
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
