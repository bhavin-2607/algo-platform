"""
Options API routes — expiry list, option chain, per-user options watchlist.
"""
import asyncio
import csv
import logging
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.core.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Underlying config
UNDERLYINGS = {
    "NIFTY50":    {"scrip": 13,  "seg": "IDX_I", "lot_size": 75},
    "BANKNIFTY":  {"scrip": 25,  "seg": "IDX_I", "lot_size": 30},
    "FINNIFTY":   {"scrip": 27,  "seg": "IDX_I", "lot_size": 40},
    "MIDCPNIFTY": {"scrip": 11,  "seg": "IDX_I", "lot_size": 75},
}

def _dhan_headers():
    return {
        "access-token": settings.DHAN_ACCESS_TOKEN,
        "client-id":    settings.DHAN_CLIENT_ID,
        "Content-Type": "application/json",
        "Accept":       "application/json",
    }


_OPTION_ROWS: list[dict] | None = None


def _load_option_rows() -> list[dict]:
    """NSE option contracts from the scrip master, cached for search."""
    global _OPTION_ROWS
    if _OPTION_ROWS is not None:
        return _OPTION_ROWS
    csv_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "market", "instruments.csv"
    ))
    rows: list[dict] = []
    if not os.path.exists(csv_path):
        _OPTION_ROWS = rows
        return rows
    with open(csv_path, newline="", encoding="utf-8", errors="ignore") as handle:
        for row in csv.DictReader(handle):
            if row.get("EXCH_ID") != "NSE":
                continue
            if row.get("INSTRUMENT") not in ("OPTIDX", "OPTSTK"):
                continue
            opt = (row.get("OPTION_TYPE") or "").strip()
            if opt not in ("CE", "PE"):
                continue
            sid = (row.get("SECURITY_ID") or "").strip()
            if not sid:
                continue
            display = (row.get("DISPLAY_NAME") or "").strip()
            underlying = (row.get("UNDERLYING_SYMBOL") or "").strip()
            try:
                strike = float(row.get("STRIKE_PRICE") or 0)
                lot = int(float(row.get("LOT_SIZE") or 1))
            except ValueError:
                continue
            expiry = (row.get("SM_EXPIRY_DATE") or "").strip()
            blob = f"{display} {underlying} {strike:g} {opt} {expiry}".upper()
            rows.append({
                "symbol":           display or f"{underlying} {strike:g} {opt}",
                "underlying":       underlying,
                "security_id":      str(int(float(sid))),
                "strike":           strike,
                "option_type":      opt,
                "expiry":           expiry,
                "lot_size":         lot,
                "exchange_segment": "NSE_FNO",
                "blob":             blob,
            })
    _OPTION_ROWS = rows
    logger.info("Loaded %s NSE option contracts for search", len(rows))
    return rows


def _token_matches(token: str, row: dict, padded: str) -> bool:
    if any(ch.isdigit() for ch in token):
        return token in row["blob"]
    if row["underlying"].upper() == token:
        return True
    return f" {token} " in padded


def _quote_fields(quote: dict) -> dict:
    """Same quote fields the terminal watchlist renders."""
    ltp = float(quote.get("last_price") or quote.get("ltp") or 0)
    ohlc = quote.get("ohlc") or {}
    close = float(ohlc.get("close") or quote.get("close") or 0)
    depth = quote.get("depth") or {}
    buy = (depth.get("buy") or [{}])[0] or {}
    sell = (depth.get("sell") or [{}])[0] or {}
    vwap = float(quote.get("average_price") or 0)
    return {
        "ltp":        ltp,
        "open":       float(ohlc.get("open") or quote.get("open") or 0),
        "high":       float(ohlc.get("high") or quote.get("high") or 0),
        "low":        float(ohlc.get("low") or quote.get("low") or 0),
        "close":      close,
        "vwap":       vwap,
        "volume":     int(quote.get("volume") or 0),
        "oi":         int(quote.get("oi") or 0),
        "bp1":        float(buy.get("price") or quote.get("top_bid_price") or 0),
        "sp1":        float(sell.get("price") or quote.get("top_ask_price") or 0),
        "change_pct": round(((ltp - close) / close) * 100, 2) if close else 0,
    }

# ── Expiry List ───────────────────────────────────────────────────────────────
@router.get("/expiry")
async def get_expiry_list(
    underlying: str = Query("NIFTY50"),
    current_user: User = Depends(get_current_user),
):
    """Fetch all expiry dates for a given underlying from Dhan."""
    cfg = UNDERLYINGS.get(underlying.upper())
    if not cfg:
        raise HTTPException(status_code=400, detail=f"Unknown underlying: {underlying}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.dhan.co/v2/optionchain/expirylist",
            headers=_dhan_headers(),
            json={"UnderlyingScrip": cfg["scrip"], "UnderlyingSeg": cfg["seg"]},
            timeout=10,
        )
    data = resp.json()
    if data.get("status") != "success":
        raise HTTPException(status_code=502, detail=str(data))

    from datetime import date, timedelta
    expiries = data.get("data", [])

    # Tag each expiry as weekly or monthly
    result = []
    for exp in expiries:
        d = date.fromisoformat(exp)
        # Monthly = last Thursday of the month
        # Weekly  = all other Thursdays
        # Simple check: if next expiry is within 8 days, it's weekly
        is_monthly = d.day > 24  # last week of month
        result.append({
            "date":    exp,
            "display": d.strftime("%d %b %Y"),
            "type":    "monthly" if is_monthly else "weekly",
            "days_to_expiry": (d - date.today()).days,
        })

    return {"underlying": underlying, "expiries": result, "lot_size": cfg["lot_size"]}

# ── Option Chain ──────────────────────────────────────────────────────────────
@router.get("/chain")
async def get_option_chain(
    underlying: str = Query("NIFTY50"),
    expiry:     str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Fetch full option chain with Greeks from Dhan."""
    cfg = UNDERLYINGS.get(underlying.upper())
    if not cfg:
        raise HTTPException(status_code=400, detail=f"Unknown underlying: {underlying}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.dhan.co/v2/optionchain",
            headers=_dhan_headers(),
            json={
                "UnderlyingScrip": cfg["scrip"],
                "UnderlyingSeg":   cfg["seg"],
                "Expiry":          expiry,
            },
            timeout=15,
        )
    data = resp.json()
    if data.get("status") != "success":
        raise HTTPException(status_code=502, detail=str(data))

    underlying_ltp = data["data"]["last_price"]
    oc             = data["data"]["oc"]

    # Build sorted strike list
    strikes = []
    for strike_str, sides in oc.items():
        strike = float(strike_str)
        ce     = sides.get("ce", {})
        pe     = sides.get("pe", {})
        strikes.append({
            "strike": strike,
            "ce": {
                "ltp":      ce.get("last_price"),
                "oi":       ce.get("oi"),
                "volume":   ce.get("volume"),
                "iv":       round(ce.get("implied_volatility", 0), 2),
                "delta":    ce.get("greeks", {}).get("delta"),
                "theta":    ce.get("greeks", {}).get("theta"),
                "gamma":    ce.get("greeks", {}).get("gamma"),
                "vega":     ce.get("greeks", {}).get("vega"),
                "bid":      ce.get("top_bid_price"),
                "ask":      ce.get("top_ask_price"),
                "security_id": str(ce.get("security_id", "")),
                "prev_oi":  ce.get("previous_oi"),
            } if ce else None,
            "pe": {
                "ltp":      pe.get("last_price"),
                "oi":       pe.get("oi"),
                "volume":   pe.get("volume"),
                "iv":       round(pe.get("implied_volatility", 0), 2),
                "delta":    pe.get("greeks", {}).get("delta"),
                "theta":    pe.get("greeks", {}).get("theta"),
                "gamma":    pe.get("greeks", {}).get("gamma"),
                "vega":     pe.get("greeks", {}).get("vega"),
                "bid":      pe.get("top_bid_price"),
                "ask":      pe.get("top_ask_price"),
                "security_id": str(pe.get("security_id", "")),
                "prev_oi":  pe.get("previous_oi"),
            } if pe else None,
        })

    strikes.sort(key=lambda x: x["strike"])

    # Find ATM strike
    atm = min(strikes, key=lambda x: abs(x["strike"] - underlying_ltp))

    return {
        "underlying":     underlying,
        "underlying_ltp": underlying_ltp,
        "expiry":         expiry,
        "lot_size":       cfg["lot_size"],
        "atm_strike":     atm["strike"],
        "strikes":        strikes,
    }

def match_option_contracts(q: str, limit: int = 20) -> list[dict]:
    """NSE option matches for the options page and the terminal symbol search."""
    text = (
        q.upper().strip()
        .replace("CALL", "CE")
        .replace("PUT", "PE")
        .replace("NIFTY50", "NIFTY")
    )
    tokens = text.split()
    opt = tokens.pop() if tokens and tokens[-1] in ("CE", "PE") else None
    if not tokens:
        return []
    hits = []
    for row in _load_option_rows():
        if opt and row["option_type"] != opt:
            continue
        padded = f" {row['blob']} "
        if not all(_token_matches(token, row, padded) for token in tokens):
            continue
        hits.append(row)

    def rank(row: dict) -> tuple:
        name = row["symbol"].upper()
        underlying = row["underlying"].upper()
        lead = tokens[0] if tokens else ""
        if name.startswith(text) or (lead and underlying == lead):
            return (0, row["expiry"], row["strike"])
        if lead and underlying.startswith(lead):
            return (1, row["expiry"], row["strike"])
        return (2, row["expiry"], row["strike"])

    hits.sort(key=rank)
    return [{k: v for k, v in row.items() if k != "blob"} for row in hits[:limit]]


# ── Option search ─────────────────────────────────────────────────────────────
@router.get("/search")
async def search_options(
    q: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
):
    """Search NSE option contracts by underlying, strike, or display name."""
    return await asyncio.to_thread(match_option_contracts, q, 20)


# ── Options Watchlist ─────────────────────────────────────────────────────────
@router.get("/watchlist")
async def get_options_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT * FROM user_options_watchlist WHERE user_id = :uid ORDER BY added_at DESC"),
        {"uid": str(current_user.id)}
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]

@router.post("/watchlist", status_code=201)
async def add_to_options_watchlist(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    try:
        await db.execute(
            text("""INSERT INTO user_options_watchlist
                (user_id, underlying, symbol, security_id, strike, option_type, expiry, exchange_segment, lot_size)
                VALUES (:uid, :underlying, :symbol, :security_id, :strike, :option_type, :expiry, :exchange_segment, :lot_size)
                ON CONFLICT (user_id, security_id) DO NOTHING"""),
            {
                "uid":              str(current_user.id),
                "underlying":       body.get("underlying", "NIFTY50"),
                "symbol":           body.get("symbol", ""),
                "security_id":      str(body.get("security_id", "")),
                "strike":           float(body.get("strike", 0)),
                "option_type":      body.get("option_type", "CE"),
                "expiry":           __import__("datetime").date.fromisoformat(str(body.get("expiry", "2099-01-01"))),
                "exchange_segment": body.get("exchange_segment", "NSE_FNO"),
                "lot_size":         int(body.get("lot_size", 75)),
            }
        )
        await db.commit()
        return {"status": "added"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/watchlist/{security_id}")
async def remove_from_options_watchlist(
    security_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    await db.execute(
        text("DELETE FROM user_options_watchlist WHERE user_id=:uid AND security_id=:sid"),
        {"uid": str(current_user.id), "sid": security_id}
    )
    await db.commit()
    return {"status": "removed"}

@router.patch("/watchlist/{security_id}")
async def update_option_lot(
    security_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the quantity that counts as one lot for this saved contract."""
    from sqlalchemy import text
    try:
        lot = int(body.get("lot_size"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Lot size must be a whole number")
    if lot < 1:
        raise HTTPException(status_code=400, detail="Lot size must be at least 1")
    result = await db.execute(
        text("""UPDATE user_options_watchlist
                SET lot_size = :lot
                WHERE user_id = :uid AND security_id = :sid"""),
        {"lot": lot, "uid": str(current_user.id), "sid": security_id},
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Option is not on the watchlist")
    return {"status": "updated", "security_id": security_id, "lot_size": lot}

@router.get("/underlyings")
async def get_underlyings(current_user: User = Depends(get_current_user)):
    return [
        {"symbol": k, "lot_size": v["lot_size"], "scrip": v["scrip"]}
        for k, v in UNDERLYINGS.items()
    ]


@router.get("/watchlist/live")
async def get_options_live(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch live quotes for all options in user watchlist via Dhan marketfeed."""
    from sqlalchemy import text
    import httpx

    result = await db.execute(
        text("SELECT security_id, symbol, option_type, strike, lot_size FROM user_options_watchlist WHERE user_id=:uid"),
        {"uid": str(current_user.id)}
    )
    rows = result.mappings().all()
    if not rows:
        return {}

    # Build securities dict for Dhan quote API
    securities = {"NSE_FNO": [int(r["security_id"]) for r in rows]}
    logger.info(f"Options live request: {securities}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.dhan.co/v2/marketfeed/quote",
            headers=_dhan_headers(),
            json=securities,
            timeout=10,
        )
    data = resp.json()
    logger.info(f"Options live raw response: {str(data)[:500]}")

    result_map = {}
    if data.get("status") == "success" and "data" in data:
        raw = data["data"].get("NSE_FNO", {})
        for sid_str, quote in raw.items():
            if isinstance(quote, dict):
                result_map[str(sid_str)] = _quote_fields(quote)
    return result_map
